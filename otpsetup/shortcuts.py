from kombu import BrokerConnection

from django.conf import settings
from django.shortcuts import render_to_response as orig_render_to_response
from django.template import RequestContext

from boto import connect_ec2

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
