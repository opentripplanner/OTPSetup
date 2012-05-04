#!/usr/bin/python

from boto import connect_s3, connect_ec2
from boto.s3.key import Key
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.shortcuts import stop_current_instance
from otpsetup.client.models import GtfsFile
from otpsetup import settings
from shutil import copyfileobj
from datetime import datetime

import os
import socket
import traceback
import subprocess
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
        req_name = "req%s_%s" % (body['request_id'], now.strftime("%F-%T"))
        directory = os.path.join("/mnt", req_name)
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
       
        fare_factory = body['fare_factory']

        gbresults = builder.build_graph(directory, fare_factory)
                
        msgparams = { }
        msgparams['request_id'] = body['request_id']
        msgparams['success'] = gbresults['success']

        bucket = graph_bucket()

        if gbresults['success']:
            key = Key(bucket)
            key.key = "uploads/%s/Graph_%s.obj" % (body['request_id'], datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
            graph_file = os.path.join(directory,'Graph.obj')
            key.set_contents_from_filename(graph_file)
            msgparams['key'] = key.key
            subprocess.call(['rm', graph_file])
            
            # read otp version 
            pompropsfile = 'META-INF/maven/org.opentripplanner/opentripplanner-graph-builder/pom.properties'
            subprocess.call(['unzip', os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'otpgb/graph-builder.jar'), pompropsfile, '-d', '/mnt'])
            pomprops = open(os.path.join('/mnt', pompropsfile), 'r')
            version = 'n/a'
            for line in pomprops:
                if line[:8] == 'version=':
                    version = line[8:].rstrip()
                    break
            msgparams['otp_version'] = version
            
        
        publisher = conn.Producer(routing_key="graph_done", exchange=exchange)
        publisher.publish(msgparams)
        
        print 'published graph_done'
        
        message.ack()

        # create data tarball and upload to s3
        tarball = os.path.join('/mnt', ('%s.tar.gz' % req_name))
        subprocess.call(['tar', 'czf', tarball, directory])

        key = Key(bucket)
        key.key = "data/%s.tar.gz" % req_name
        key.set_contents_from_filename(tarball)

        # write gb output to file to s3
        outputfilename = os.path.join(directory, 'gb_output')
        outputfile = open(outputfilename, 'w')
        outputfile.write(gbresults['output'])
        outputfile.close()

        key = Key(bucket)
        key.key = "output/%s_output.txt" % req_name
        key.set_contents_from_filename(outputfilename)


    except:
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (body['request_id'], now.strftime("%F-%T"))
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
            
stop_current_instance()

