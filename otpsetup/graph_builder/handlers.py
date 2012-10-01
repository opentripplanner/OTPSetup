#!/usr/bin/python

from boto import connect_s3, connect_ec2
from boto.s3.key import Key
from kombu import Exchange
#from otpsetup.client.models import GtfsFile
from otpsetup import settings
from shutil import copyfileobj
from datetime import datetime

import os, socket, traceback, subprocess, builder, json, uuid

#import transformer

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

def write_output_to_s3(key_text, output):
    outputfilename = '/mnt/gb_output'
    outputfile = open(outputfilename, 'w')
    outputfile.write(output)
    outputfile.close()

    key = Key(graph_bucket())
    key.key = key_text
    key.set_contents_from_filename(outputfilename)

def download_managed_gtfs(directory, feeds):
    bucket = managed_gtfs_bucket()

    print "feeds:"
    os.makedirs(os.path.join(directory, 'gtfs'))
    for feed in feeds:
        print " - %s" % feed['key']
        key = Key(bucket)
        key.key = feed['key']
        basename = os.path.basename(feed['key'].split('/')[-1])
        path = os.path.join(directory, 'gtfs', "%s.zip" % basename)
        key.get_contents_to_filename(path)
        print "    - wrote %s" % path


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
        write_output_to_s3("output/%s_output.txt" % req_name, gbresults['output'])

    except:
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (body['request_id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))

def process_gtfs(conn, body):

    try:
        print 'process_gtfs'
        print body['config']
        config = json.loads(body['config'])

        directory = "/mnt/gtfs%s" % body['id']
        bucket = managed_gtfs_bucket()

        print "feeds:"
        i = 0
        agency_groups = { } 
        os.makedirs(os.path.join(directory, 'gtfs'))
        for feed in config['feeds']:
            feedId = feed['feedId']
            print " - %s" % feedId
            
            if 'defaultAgencyId' in feed:
                agencyId = feed['defaultAgencyId']
                if agencyId in agency_groups:
                    agency_groups[agencyId].append(feed)
                else:
                    agency_groups[agencyId] = [ feed ]
 
            else:
                agencyId = "agency%s" % i
                i = i + 1
                agency_groups[agencyId] = [ feedId ]
                
        print agency_groups

        agency_keys = { }

        for agencyId in agency_groups:
            print "%s: %s" % (agencyId, len(agency_groups[agencyId]))
            agencyDir = os.path.join(directory, agencyId)
            
            if len(agency_groups[agencyId]) > 1:

                # download & shorten feeds
                os.makedirs(agencyDir)

                shortened_paths = []                
                for feed in agency_groups[agencyId]:
                    
                    feedId = feed['feedId']

                    print "downloading %s" % feedId
                    key = Key(bucket)
                    key.key = feedId
                    basename = os.path.basename(feedId)
                    path = os.path.join(agencyDir, "%s.zip" % basename)
                    key.get_contents_to_filename(path)

                    # shorten
                    print " shortening"
                    shortened_path = os.path.join(agencyDir, "%s_shortened.zip" % basename)
                    shorten_date = feed['expireOn'].replace("-","")
                    subprocess.call(['python', '/var/otp/resources/process_gtfs/shortenGtfsFeed.py', shorten_date, path, shortened_path])
                    shortened_paths.append(shortened_path) 
                    print " shortened"
                    
                # merge
                mergejarpath = "/var/otp/resources/process_gtfs/merger.jar"
                #merge_cmd = ['java', '-Xms15G', '-Xmx15G', '-jar', mergejarpath, '--file=agency.txt', '--fuzzyDuplicates', '--file=routes.txt', '--fuzzyDuplicates', '--file=shapes.txt', '--fuzzyDuplicates', '--file=fare_attributes.txt', '--fuzzyDuplicates', '--file=fare_rules.txt', '--fuzzyDuplicates', '--file=transfers.txt', '--fuzzyDuplicates', '--file=calendar.txt', '--renameDuplicates', '--file=trips.txt', '--renameDuplicates'] 
                merge_cmd = ['java', '-Xms15G', '-Xmx15G', '-jar', mergejarpath, '--file=agency.txt', '--fuzzyDuplicates', '--file=stops.txt', '--fuzzyDuplicates', '--file=routes.txt', '--fuzzyDuplicates', '--file=shapes.txt', '--fuzzyDuplicates', '--file=fare_attributes.txt', '--fuzzyDuplicates', '--file=fare_rules.txt', '--fuzzyDuplicates', '--file=transfers.txt', '--fuzzyDuplicates', '--file=calendar.txt', '--duplicateDetection=IDENTITY', '--renameDuplicates', '--file=trips.txt', '--duplicateDetection=IDENTITY', '--renameDuplicates'] 
                merge_cmd.extend(shortened_paths)

                merged_path = os.path.join(agencyDir, "merged.zip")
                merge_cmd.append(merged_path)

                print "merging"
                subprocess.call(merge_cmd)
                print "merged"

                to_transform = merged_path
 
            else:

                os.makedirs(agencyDir)
                feed = agency_groups[agencyId][0] 
                print "process standalone: %s" % feed['feedId']
                key = Key(bucket)
                key.key = feed['feedId']
                basename = os.path.basename(feedId)
                path = os.path.join(agencyDir, "%s.zip" % basename)
                key.get_contents_to_filename(path)

                # shorten
                print " shortening"
                shortened_path = os.path.join(agencyDir, "%s_shortened.zip" % basename)
                shorten_date = feed['expireOn'].replace("-","")
                subprocess.call(['python', '/var/otp/resources/process_gtfs/shortenGtfsFeed.py', shorten_date, path, shortened_path])
                print " shortened"

                to_transform = shortened_path


            # transform


            transformed_path = os.path.join(agencyDir, "transformed.zip")
            transformjarpath = "/var/otp/resources/process_gtfs/transformer.jar"

            transform_json = '{"op":"transform","class":"org.onebusaway.gtfs_transformer.updates.CalendarSimplicationStrategy"}'
            transform_cmd = ['java', '-Xms15G', '-Xmx15G', '-jar', transformjarpath, '--transform=json:%s' % transform_json, to_transform, transformed_path ]

            print "transforming"
            subprocess.call(transform_cmd)
            print "transformed"

            # upload to s3
            print "uploading to s3"
            s3_key = "processed/%s" % uuid.uuid1()
            key = Key(bucket)
            key.key = s3_key
            key.set_contents_from_filename(transformed_path)

            # add key to list
            agency_keys[agencyId] = s3_key

            #else:
            #
            #    # add standalone feed to list 
            #    agency_keys[agencyId] = agency_groups[agencyId][0]

        print agency_keys

        # publish process_gtfs_done message
        publisher = conn.Producer(routing_key="process_gtfs_done", exchange=exchange)
        publisher.publish({ 'id' : body['id'], 'key_map' : agency_keys }) 
        print "published p_g_d msg"



    except:
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (body['id'], now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))
        traceback.print_exc()


def build_managed(conn, body):

    try:        
        print "build_managed"

        print "osm_key=%s" % body['osm_key']

        feeds = body['feeds']

        if body['osm_key'] is None:
            print "no osm key"
            publisher = conn.Producer(routing_key="build_managed_osm", exchange=exchange)
            publisher.publish({ 'id' : body['id'], 'feeds' : feeds, 'trigger_rebuild' : True })
            return

        
        print "key exists, building"

        #config = json.loads(body['config'])

        # set up working directory
        req_name = "managed_%s" % get_req_name(body['id']);
        directory = init_directory(req_name);
        download_managed_gtfs(directory, feeds)


        # download osm extract
        bucket = osm_bucket()
        key = Key(bucket)
        key.key = body['osm_key']
        path = os.path.join(directory, 'extract.osm')
        key.get_contents_to_filename(path)


        # run graph builder
        builder.generate_graph_config_managed(directory, feeds) 
        gbresults = builder.run_graph_builder(directory)

        graph_key = None

        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        # upload graph to S3
        if gbresults['success']:
            key = Key(graph_bucket())
            graph_key = "managed/%s/Graph_%s.obj" % (str(body['id']).zfill(6), timestamp)
            key.key = graph_key
            graph_file = os.path.join(directory,'Graph.obj')
            key.set_contents_from_filename(graph_file)

        # write gb output to file to s3
        output_key = "managed/%s/output_%s.txt" % (str(body['id']).zfill(6), timestamp)
        write_output_to_s3(output_key, gbresults['output'])

        # publish managed_graph_done
        publisher = conn.Producer(routing_key="managed_graph_done", exchange=exchange)
        publisher.publish({ 'id' : body['id'], 'success' : gbresults['success'], 'graph_key' : graph_key, 'output_key' : output_key, 'otp_version' : get_otp_version() })

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
	
        feeds = body['feeds']

        download_managed_gtfs(directory, feeds)
        
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
            publisher.publish({ 'id' : body['id'], 'osm_key' : osm_key, 'feeds' : feeds })


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

