#!/usr/bin/python

from boto import connect_s3, connect_ec2
from boto.s3.key import Key
from kombu import Exchange
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

# helper functions

def get_req_name(request_id):
    return "req%s_%s" % (request_id, datetime.now().strftime("%F-%T"))

def init_directory(req_name):
    directory = os.path.join("/mnt", req_name)
    os.makedirs(directory)
    return directory

def get_otp_version():
    pompropsfile = 'META-INF/maven/org.opentripplanner/opentripplanner-graph-builder/pom.properties'
    subprocess.call(['unzip', '-o', os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'otpgb/graph-builder.jar'), pompropsfile, '-d', '/mnt'])
    pomprops = open(os.path.join('/mnt', pompropsfile), 'r')
    version = 'n/a'
    for line in pomprops:
        if line[:8] == 'version=':
            version = line[8:].rstrip()
            break
    return version

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

def write_output_to_s3(req_name, output):
    outputfilename = '/mnt/gb_output'
    outputfile = open(outputfilename, 'w')
    outputfile.write(output)
    outputfile.close()

    key = Key(graph_bucket())
    key.key = "output/%s_output.txt" % req_name
    key.set_contents_from_filename(outputfilename)


# handler functions

def create_instance(conn, body):

    try:
        req_name = get_req_name(body['request_id']);
        directory = init_directory(req_name);
        
        # extract gtfs files
        os.makedirs(os.path.join(directory, 'gtfs'))
        files = body['files']
        extra_props_list = body['extra_properties']
        extra_props_dict = { }
        out = []
        i = 0
        for s3_id in files:
            print "id: " + s3_id
        
            bucket = gtfs_bucket()
            key = Key(bucket)
            key.key = s3_id

            basename = os.path.basename(s3_id)
            path = os.path.join(directory, 'gtfs', basename)
            
            key.get_contents_to_filename(path)        

            extra_props_dict[basename] = extra_props_list[i]
            i += 1
       
        # prepare and run graph builder
        builder.prepare_graph_builder(directory, body['fare_factory'], extra_props_dict)
        gbresults = builder.run_graph_builder(directory)
                
        print "finished gb: %s" % gbresults['success']

        msgparams = { }
        msgparams['request_id'] = body['request_id']
        msgparams['success'] = gbresults['success']

        bucket = graph_bucket()

        if gbresults['success']:
            key = Key(bucket)
            key.key = "uploads/%s/Graph_%s.obj" % (body['request_id'], datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
            graph_file = os.path.join(directory,'Graph.obj')
            key.set_contents_from_filename(graph_file)
            key.set_acl('public-read')
            msgparams['key'] = key.key
            subprocess.call(['rm', graph_file])
            
            msgparams['otp_version'] = get_otp_version()
            
        # create data tarball and upload to s3
        tarball = os.path.join('/mnt', ('%s.tar.gz' % req_name))
        subprocess.call(['tar', 'czf', tarball, directory])

        key = Key(bucket)
        data_key = "data/%s.tar.gz" % req_name
        key.key = data_key
        key.set_contents_from_filename(tarball)
        msgparams['data_key'] = data_key

        # publish graph_done message        
        publisher = conn.Producer(routing_key="graph_done", exchange=exchange)
        publisher.publish(msgparams)
        
        print 'published graph_done'
        
        # write gb output to file to s3
        write_output_to_s3(req_name, gbresults['output'])

    except:
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (body['request_id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))


def rebuild_graph(conn, body):

    try:        
        req_name = body['data_key'][5:][:-7]

        directory = os.path.join('/mnt', req_name)

        # download and extract data tarball
        bucket = graph_bucket()
        key = Key(bucket)
        key.key = body['data_key']
        tarball = '/mnt/data.tar.gz'
        key.get_contents_to_filename(tarball)
        subprocess.call(['tar', 'xvf', tarball, '-C', '/'])
        
        # run graph builder
        gbresults = builder.run_graph_builder(directory)
                
        msgparams = { }
        msgparams['request_id'] = body['request_id']
        msgparams['success'] = gbresults['success']

        if gbresults['success']:
            #upload graph to s3            
            key = Key(bucket)
            key.key = "uploads/%s/Graph_%s.obj" % (body['request_id'], datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
            graph_file = os.path.join(directory,'Graph.obj')
            key.set_contents_from_filename(graph_file)
            key.set_acl('public-read')
            msgparams['key'] = key.key
            subprocess.call(['rm', graph_file])
            
            msgparams['otp_version'] = get_otp_version()
            
        
        publisher = conn.Producer(routing_key="rebuild_graph_done", exchange=exchange)
        publisher.publish(msgparams)
        
        print 'published rebuild_graph_done'
        
        # write gb output to file to s3
        write_output_to_s3(req_name, gbresults['output'])


    except:
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (body['request_id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))

