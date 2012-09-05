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
import json

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

def managed_gtfs_bucket(cache = {}):
    if not 'bucket' in cache:        
        connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)        
        bucket = connection.get_bucket('gtfs-test')
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

def osm_bucket(cache = {}):
    if not 'bucket' in cache:        
        connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)        
        bucket = connection.get_bucket('managed-osm')
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

def download_managed_gtfs(directory, config):
    bucket = managed_gtfs_bucket()

    print "feeds:"
    os.makedirs(os.path.join(directory, 'gtfs'))
    for feed in config['feeds']:
        print " - %s" % feed['feedId']
        key = Key(bucket)
        key.key = feed['feedId']
        basename = os.path.basename(feed['feedId'])
        path = os.path.join(directory, 'gtfs', "%s.zip" % basename)
        key.get_contents_to_filename(path)
        #if extract is True:
        #    gtfsfeeddir = os.path.join(directory, 'gtfs', basename)
        #    subprocess.call(['unzip', path, '-d', gtfsfeeddir])


# handler functions


# legacy support to create "preview" deployment. look into merging w/ "managed" deployment workflow below
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
            if s3_id is None:
                continue

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
        builder.generate_osm_extract(directory)
        builder.generate_graph_config(directory, body['fare_factory'], extra_props_dict)
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



def build_managed(conn, body):

    try:        
        print "build_managed"
        print body['config']
        print body['osm_key']

        if body['osm_key'] is None:
            print "no osm key"
            publisher = conn.Producer(routing_key="build_managed_osm", exchange=exchange)
            publisher.publish({ 'id' : body['id'], 'config' : body['config'], 'trigger_rebuild' : True })
            return

        
        print "key exists, building"

        config = json.loads(body['config'])

        # set up working directory
        req_name = "managed_%s" % get_req_name(body['id']);
        directory = init_directory(req_name);

        # download osm extract and gtfs feeds
        bucket = osm_bucket()
        key = Key(bucket)
        key.key = body['osm_key']
        path = os.path.join(directory, 'extract.osm')
        key.get_contents_to_filename(path)

        download_managed_gtfs(directory, config)

        # run graph builder
        builder.generate_graph_config_managed(directory, config) 
        gbresults = builder.run_graph_builder(directory)

        graph_key = None

        # upload graph to S3
        if gbresults['success']:
            key = Key(graph_bucket())
            graph_key = "managed/%s/Graph_%s.obj" % (body['id'], datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
            key.key = graph_key
            graph_file = os.path.join(directory,'Graph.obj')
            key.set_contents_from_filename(graph_file)

        # publish managed_graph_done
        publisher = conn.Producer(routing_key="managed_graph_done", exchange=exchange)
        publisher.publish({ 'id' : body['id'], 'success' : gbresults['success'], 'graph_key' : graph_key, 'otp_version' : get_otp_version(), 'config' : body['config'] })

    except:
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (body['id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))
        traceback.print_exc()




def build_managed_osm(conn, body):

    try:        
        print "build_managed_osm"

        req_name = "managed_%s" % get_req_name(body['id']);
        directory = init_directory(req_name);
	
        config = json.loads(body['config'])

        download_managed_gtfs(directory, config)
        
        builder.generate_osm_extract(directory)

        key = Key(osm_bucket())
        osm_key = "%s.osm" % body['id']
        key.key = osm_key
        key.set_contents_from_filename(os.path.join(directory, 'extract.osm'))
        
        print 'uploaded osm'

        publisher = conn.Producer(routing_key="osm_extract_done", exchange=exchange)
        publisher.publish({ 'id' : body['id'], 'osm_key' : osm_key })       

        print 'published extract_osm_done'

        if 'trigger_rebuild' in body and body['trigger_rebuild'] is True:
            publisher = conn.Producer(routing_key="build_managed", exchange=exchange)
            publisher.publish({ 'id' : body['id'], 'osm_key' : osm_key, 'config' : body['config'] })


    except:
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (body['id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))
        traceback.print_exc()


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

