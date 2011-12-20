#!/usr/bin/python

from boto import connect_s3
from boto.s3.key import Key
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.client.models import GtfsFile
from otpsetup import settings
from shutil import copyfileobj

import os
import subprocess
import tempfile

import builder

exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("create_instance", exchange=exchange, routing_key="create_instance")

print "starting graph builder"

def s3_bucket(cache = {}):
    if not 'bucket' in cache:
        
        connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)        
        #import pdb;pdb.set_trace()
        #print settings.S3_BUCKET
        bucket = connection.get_bucket(settings.S3_BUCKET)
        cache['bucket'] = bucket
    else:
        return cache['bucket']
    return bucket


def handle_instance_request(conn, body, message):
    #download the GTFS files and run them through the feed validator


    print "build graph"
    #import pdb;pdb.set_trace()
    #create a working directory for this feed
    directory = tempfile.mkdtemp()
    print "dir: "+directory
    #os.makedirs(directory)
    os.makedirs(os.path.join(directory, 'gtfs'))

    files = body['files']
    out = []
    for s3_id in files:
        print "id: " + s3_id
    
        bucket = s3_bucket()
        key = Key(bucket)
        key.key = s3_id

        basename = os.path.basename(s3_id)
        path = os.path.join(directory, 'gtfs', basename)
        
        key.get_contents_to_filename(path)        
   
    builder.build_graph(directory)
           
    #os.rmdir(directory)
    
    #TODO: produce AMQP output 
    #publisher = conn.Producer(routing_key="validation_done", exchange=exchange)
    #publisher.publish({'request_id' : body['request_id'], 'output' : out})
    #message.ack()

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queue, callbacks=[lambda body, message: handle_instance_request(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()
