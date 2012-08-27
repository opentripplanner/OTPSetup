from kombu import BrokerConnection, Exchange, Queue

from django.conf import settings
from django.shortcuts import render_to_response as orig_render_to_response
from django.template import RequestContext

from boto import connect_ec2, connect_s3
from boto.s3.key import Key

import socket

def render_to_response(req, *args, **kwargs):
    kwargs['context_instance'] = RequestContext(req)
    return orig_render_to_response(*args, **kwargs)

def DjangoBrokerConnection():

    return BrokerConnection("amqp://%s:%s@%s:%s/%s" % (
            settings.BROKER_USER,
            settings.BROKER_PASSWORD,
            settings.BROKER_HOST or "localhost",
            settings.BROKER_PORT or "5672",
            settings.BROKER_VHOST or "/"))
            
def check_for_running_instance(ami_id):
    print "cfri"
    ec2_conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    found_instance = False
    reservations = ec2_conn.get_all_instances()
    for reservation in reservations:
        if found_instance:
            break
        for instance in reservation.instances:
            print "id: "+instance.image_id
            if instance.image_id == ami_id:
                if not instance.state == 'running':
                    instance.start()
                    print " starting" 
                found_instance = True
                break  


def stop_current_instance():

    ec2_conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)

    hostname = socket.gethostname()
    hostname = hostname[3:].replace('-','.')

    reservations = ec2_conn.get_all_instances()
    running_instances = []
    found_instance = False
    for reservation in reservations:
        for instance in reservation.instances:
            private_ip = instance.private_ip_address
            if private_ip == hostname:
                instance.stop()
                found_instance = True

    if not found_instance:
        print "warning: did not find instance matching host machine"
                    

def download_otp_wars():

    connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    bucket = connection.get_bucket('otpsetup-resources')

    key = Key(bucket)
    key.key = 'opentripplanner-api-webapp.war'
    local_file = '/var/otp/wars/opentripplanner-api-webapp.war'
    key.get_contents_to_filename(local_file)

    key = Key(bucket)
    key.key = 'opentripplanner-webapp.war'
    local_file = '/var/otp/wars/opentripplanner-webapp.war'
    key.get_contents_to_filename(local_file)


def get_instance_id():

    instance_id = 'n/a'
    ec2_conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    host_ip = socket.gethostname()[3:].replace('-','.')
    reservations = ec2_conn.get_all_instances()
    for reservation in reservations:
        for instance in reservation.instances:
            private_ip = instance.private_ip_address
            if private_ip == host_ip:
                instance_id = instance.id

    return instance_id
    
def build_multi_queue(keys):
    queues = [] 
    exchange = Exchange("amq.direct", type="direct", durable=True)

    for key in keys:
        queues.append(Queue(key, exchange=exchange, routing_key=key))
        
    return queues
    

