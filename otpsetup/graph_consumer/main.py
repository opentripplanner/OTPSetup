#!/usr/bin/python

from boto import connect_ec2
from django.core.mail import send_mail
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.client.models import InstanceRequest, GtfsFile
from otpsetup import settings

print "Starting Graph Consumer"

exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("graph_done", exchange=exchange, routing_key="graph_done")

def handle(conn, body, message):
    request_id = body['request_id']
    success = body['success']

    if success:
        #publish a deploy_instance message
        publisher = conn.Producer(routing_key="deploy_instance", exchange=exchange)
        publisher.publish({'request_id' : request_id, 'key' : body['key'], 'output' : body['output']})

        #start a new deployment instance
        ec2_conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY) 

        image = ec2_conn.get_image(settings.DEPLOYMENT_AMI_ID) 

        print 'Launching EC2 Instance'
        image.run(placement='us-east-1b', key_name='otp-dev', security_groups=['default'], instance_type='m1.large') 

    else:
        send_mail('OTP graph builder failed', 
            """An OTP instance request failed during the graph-building stage.
              
Request ID: %s

Graph Builder output:
%s  
""" % (request_id, body['output']),
            settings.DEFAULT_FROM_EMAIL,
            settings.ADMIN_EMAILS, fail_silently=False)

    message.ack()

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queue, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()
