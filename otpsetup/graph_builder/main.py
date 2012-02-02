#!/usr/bin/python

from boto import connect_s3, connect_ec2
from boto.s3.key import Key
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.client.models import GtfsFile
from otpsetup import settings
from shutil import copyfileobj
from datetime import datetime

import os
import socket

import builder
 
exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("create_instance", exchange=exchange, routing_key="create_instance")

def gtfs_bucket(cache = {}):
    if not 'bucket' in cache:        
        connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)        
        bucket = connection.get_bucket(settings.S3_BUCKET)
        cache['bucket'] = bucket
    else:
        return cache['bucket']
    return bucket

def graph_bucket(cache = {}):
    if not 'bucket' in cache:        
        connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)        
        bucket = connection.get_bucket(settings.GRAPH_S3_BUCKET)
        cache['bucket'] = bucket
    else:
        return cache['bucket']
    return bucket


def handle_instance_request(conn, body, message):

    try:
        #create a working directory for this feed
        now = datetime.now()
        directory = "/mnt/req%s_%s" % (body['request_id'], now.strftime("%F-%T"))
        os.makedirs(directory)

        os.makedirs(os.path.join(directory, 'gtfs'))

        files = body['files']
        out = []
        for s3_id in files:
            print "id: " + s3_id
        
            bucket = gtfs_bucket()
            key = Key(bucket)
            key.key = s3_id

            basename = os.path.basename(s3_id)
            path = os.path.join(directory, 'gtfs', basename)
            
            key.get_contents_to_filename(path)        
       
        gbresults = builder.build_graph(directory)
               
        if gbresults['success']:
            print 'writing to s3..'
            
            bucket = graph_bucket()
            key = Key(bucket)
            key.key = "uploads/%s/Graph_%s.obj" % (body['request_id'], datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
            key.set_contents_from_filename(os.path.join(directory,'Graph.obj'))
            print 'written'
            
            gbresults['key'] = key.key
            
        
        gbresults['request_id'] = body['request_id']
        
        publisher = conn.Producer(routing_key="graph_done", exchange=exchange)
        publisher.publish(gbresults)
        
        print 'published graph_done'
        
        message.ack()
        
        #os.rmdir(directory)

    except:
        now = datetime.now()
        errfile = "/var/otp/val_err_%s_%s" % (body['request_id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))
        
with DjangoBrokerConnection() as conn:

    with conn.Consumer(queue, callbacks=[lambda body, message: handle_instance_request(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        try:
            while True:
                conn.drain_events(timeout=900)
        except:
            print "exiting main loop"

    conn.close()
            
ec2_conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)

hostname = socket.gethostname()
reservations = ec2_conn.get_all_instances()
running_instances = []
found_instance = False
for reservation in reservations:
    for instance in reservation.instances:
        private_dns = instance.private_dns_name.split('.')[0]
        if private_dns == hostname:
            #instance.stop()
            found_instance = True

if not found_instance:
    print "warning: did not find instance matching host machine"
