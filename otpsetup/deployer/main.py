from boto import connect_s3, connect_ec2
from boto.s3.key import Key
from otpsetup import settings
from django.core.mail import send_mail
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.shortcuts import stop_current_instance
from otpsetup import settings

import base64
import urllib2
import socket
import sys, traceback
import time
import os
import subprocess
import string

from datetime import datetime
from random import choice

deployer_resources_dir = '/var/otp/OTPSetup/deployer_resources'
tomcat_home = '/var/lib/tomcat6'

exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("deploy_instance", exchange=exchange, routing_key="deploy_instance")

def wait_for_tomcat():
    
    attempt = 0
    max_attempts = 10
    success = False
    
    while (attempt < max_attempts):
        try: 
            url ='http://localhost:8080/'
            req = urllib2.Request(url, None, { })
            urllib2.urlopen(req)
            success = True; # only reached if page loads successfully
            break
        except: 
            attempt = attempt + 1
            time.sleep(10)
    
    return success


def handle(conn, body, message):

    try:
        request_id = body['request_id']
        s3_id = body['key']

        # download the graph

        connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
        bucket = connection.get_bucket(settings.GRAPH_S3_BUCKET)

        key = Key(bucket)
        key.key = s3_id
        key.get_contents_to_filename('/var/otp/graphs/Graph.obj')

        # write tomcat-users file
        
        tutemplate = open(os.path.join(deployer_resources_dir, 'tomcat-users.xml'), 'r')
        tuxml = tutemplate.read()
        tutemplate.close()

        tuxml = tuxml.format(password=settings.TOMCAT_ADMIN_PASSWORD)

        tufilepath = os.path.join(tomcat_home, 'conf/tomcat-users.xml')
        tufile = open(tufilepath, 'w')
        tufile.write(tuxml)
        tufile.close()
                    
        # start & wait for tomcat
        
        subprocess.call(['/etc/init.d/tomcat6', 'start'])        
        
        tomcat_launched = wait_for_tomcat()

        launch_success = False

        if tomcat_launched is True:

            # deploy on tomcat

            encodedstring = base64.encodestring("admin:%s" % settings.TOMCAT_ADMIN_PASSWORD)[:-1]
            auth = "Basic %s" % encodedstring

            url ='http://localhost:8080/manager/install?path=/opentripplanner-api-webapp&war=/var/otp/wars/opentripplanner-api-webapp.war'
            req = urllib2.Request(url, None, {"Authorization": auth })
            url_handle = urllib2.urlopen(req)

            url ='http://localhost:8080/manager/deploy?path=/opentripplanner-webapp&war=/var/otp/wars/opentripplanner-webapp.war'
            req = urllib2.Request(url, None, {"Authorization": auth })
            url_handle = urllib2.urlopen(req)

            launch_success = True
    
        if launch_success is True:

            # rename otp-webapp as ROOT so that it loads on server's root directory
            subprocess.call(['mv', '/var/lib/tomcat6/webapps/ROOT', '/var/lib/tomcat6/webapps/ROOT-old'])
            subprocess.call(['mv', '/var/lib/tomcat6/webapps/opentripplanner-webapp', '/var/lib/tomcat6/webapps/ROOT'])

            # open security-application-context.xml template
            sactemplate = open(os.path.join(deployer_resources_dir, 'security-application-context.xml'), 'r')
            sacxml = sactemplate.read()
            sactemplate.close()

            # generate password and insert into file
            chars = string.letters + string.digits
            password = ''.join([choice(chars) for i in range(8)])
            sacxml = sacxml.format(password=password)

            # overwrite deployed security-application-context.xml
            sacfilepath = os.path.join(tomcat_home, 'webapps/opentripplanner-api-webapp/WEB-INF/classes/org/opentripplanner/api/security-application-context.xml')
            sacfile = open(sacfilepath, 'w')
            sacfile.write(sacxml)
            sacfile.close()
            
            # restart tomcat
            subprocess.call(['/etc/init.d/tomcat6', 'restart'])

            # publish deployment_ready message
            publisher = conn.Producer(routing_key="deployment_ready", exchange=exchange)
            publisher.publish({'request_id' : request_id, 'hostname' : socket.gethostname(), 'password' :  password })
    
            # acknowledge original message and exit
            message.ack()
            sys.exit(0)

    except:

        now = datetime.now()
        errfile = "/var/otp/dep_err_%s_%s" % (body['request_id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))
        

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queue, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events(timeout=600)

# shutdown the instance (if connection timed out)
stop_current_instance()

