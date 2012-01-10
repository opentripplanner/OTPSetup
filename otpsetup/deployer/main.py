from boto import connect_s3, connect_ec2
from boto.s3.key import Key
from otpsetup import settings
from django.core.mail import send_mail
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup import settings

import base64
import urllib2
import socket
import sys

exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("deploy_instance", exchange=exchange, routing_key="deploy_instance")

def handle(conn, body, message):

    request_id = body['request_id']
    s3_id = body['key']

    # download the graph

    connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    bucket = connection.get_bucket(settings.GRAPH_S3_BUCKET)

    key = Key(bucket)
    key.key = s3_id
    key.get_contents_to_filename('/var/otp/graphs/Graph.obj')


    # deploy on tomcat

    encodedstring = base64.encodestring("tomcat:password")[:-1]
    auth = "Basic %s" % encodedstring

    url ='http://localhost:8080/manager/install?path=/opentripplanner-api-webapp&war=/var/otp/wars/opentripplanner-api-webapp.war'
    req = urllib2.Request(url, None, {"Authorization": auth })
    url_handle = urllib2.urlopen(req)

    #print "api deployed: "+url_handle.read()

    url ='http://localhost:8080/manager/deploy?path=/opentripplanner-webapp&war=/var/otp/wars/opentripplanner-webapp.war'
    req = urllib2.Request(url, None, {"Authorization": auth })
    url_handle = urllib2.urlopen(req)

    #print "webapp deployed: "+url_handle.read()


    # send email alerting administrators

    hostname = socket.gethostname()

    send_mail('OTP instance deployed', 
        """An OTP instance for request_id %s was deployed on AWS host %s""" % (request_id, hostname),
        settings.DEFAULT_FROM_EMAIL,
        settings.ADMIN_EMAILS, fail_silently=False)

    message.ack()
    
    sys.exit(0)

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queue, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events(timeout=600)

# shutdown the instance (if connection timed out)

ec2_conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)

hostname = socket.gethostname()
reservations = ec2_conn.get_all_instances()
running_instances = []
found_instance = False
for reservation in reservations:
    for instance in reservation.instances:
        private_dns = instance.private_dns_name.split('.')[0]
        if private_dns == hostname:
            instance.stop()
            found_instance = True

if not found_instance:
    print "warning: did not find instance matching host machine"
