from boto import connect_s3
from boto.s3.key import Key
from otpsetup import settings
from otpsetup.shortcuts import get_instance_id
from kombu import Exchange

import base64, urllib2, socket, os, sys, subprocess

tomcat_home = '/var/lib/tomcat6'
deployer_resources_dir = '/var/otp/OTPSetup/deployer_resources'

exchange = Exchange("amq.direct", type="direct", durable=True)

def deploy_graph_multi(conn, body):
    print "received deploy message"
    
    # check that this host is the target
    if get_instance_id() != body['instance_id']:
        return False
    
    request_id = body['request_id']
    deployment_name = 'req-%s' % request_id
    subprocess.call(['mkdir', '/var/otp/graphs/%s' % deployment_name])
    
    # download graph
    connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    bucket = connection.get_bucket(settings.GRAPH_S3_BUCKET)

    key = Key(bucket)
    key.key = body['graph_key']
    key.get_contents_to_filename('/var/otp/graphs/%s/Graph.obj' % deployment_name)    


    # deploy war
    encodedstring = base64.encodestring("admin:%s" % settings.TOMCAT_ADMIN_PASSWORD)[:-1]
    auth = "Basic %s" % encodedstring
    url = 'http://localhost:8080/manager/deploy?path=/otp-webapp-%s&war=/var/otp/wars/opentripplanner-webapp.war' % deployment_name
    req = urllib2.Request(url, None, {"Authorization": auth })
    url_handle = urllib2.urlopen(req)    
    
    
    # update config.js
    configtemplate = open(os.path.join(deployer_resources_dir, 'config.js'), 'r')
    configjs = configtemplate.read()
    configtemplate.close()
    configjs = configjs.format(routerid=deployment_name)
    configjsfilepath = os.path.join(tomcat_home, 'webapps/otp-webapp-%s/js/otp/config.js' % deployment_name)
    configjsfile = open(configjsfilepath, 'w')
    configjsfile.write(configjs)
    configjsfile.close()    

    # publish multideployment_done message
    
    publisher = conn.Producer(routing_key="multideployment_done", exchange=exchange)
    publisher.publish({'request_id' : request_id})
    
    return True

def undeploy_graph_multi(conn, body):
    print "received undeploy message"
    # TODO: handle undeployment
    
    return True

