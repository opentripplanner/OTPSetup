import os
import subprocess
from otpsetup import settings

from boto import connect_s3
from boto.s3.key import Key

templatedir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'templates')
osmosisdir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'osmosis')
osmtoolsdir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'osmtools')
graphannodir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'graphanno')
otpgbdir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'otpgb')

def ned_available(boundsfilename):
    boundsfile = open(boundsfilename, 'r')
    bounds = boundsfile.read()
    boundsarr = bounds.split(",")
    minx = int(round(float(boundsarr[0])))
    maxx = int(round(float(boundsarr[1])))
    miny = int(round(float(boundsarr[2])))
    maxy = int(round(float(boundsarr[3])))

    connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)        
    bucket = connection.get_bucket('ned13')

    all_exist = True        
    for x in range(minx, maxx+1):
        for y in range(miny, maxy+1):
            nsdir =  'n' if y > 0 else 's'
            ewdir =  'e' if x > 0 else 'w'
            tiff_file = "%s%02d%s%03d.tiff" % (nsdir, abs(y), ewdir, abs(x))
            
            key = Key(bucket)
            key.key = tiff_file
            print "%s exists: %s" % (tiff_file, key.exists())
            all_exist = all_exist and key.exists()

    boundsfile.close()
    
    return all_exist

def build_graph(workingdir, fare_factory):

    # copy stop files to single directory

    stopsdir = os.path.join(workingdir, "stops")
    if not os.path.exists(stopsdir): os.makedirs(stopsdir)

    gtfsdirlist = os.listdir(os.path.join(workingdir, "gtfs"))

    for item in gtfsdirlist:
        os.system('unzip '+os.path.join(workingdir, 'gtfs', item)+' -d '+os.path.join(workingdir, 'gtfs', item[:-4]))
        stopsfile = os.path.join(workingdir, 'gtfs', item[:-4], 'stops.txt')
        if os.path.isfile(stopsfile):
            cmd = 'cp '+stopsfile+' '+os.path.join(stopsdir, item+'_stops.txt')
            os.system(cmd)
        else:
            print 'WARNING: could not find stops.txt file for "'+item+'" GTFS feed'


    # generate osmosis polygon
        
    polyfile = os.path.join(workingdir, 'extract_poly.txt')
    boundsfile = os.path.join(workingdir, 'extract_bounds.txt')
    cmd = 'java -jar %s %s %s %s' % (os.path.join(osmtoolsdir, 'osmtools.jar'), stopsdir, polyfile, boundsfile)
    os.system(cmd)

    # run osm extract

    extractfile = workingdir+'/extract.osm'
    cmd = os.path.join(osmosisdir,'bin/osmosis')+' --rb '+settings.PLANET_OSM_PATH+' --bounding-polygon file='+polyfile+' --wx '+extractfile
    os.system(cmd)

    # generate graph-builder config file
    use_ned = settings.NED_ENABLED and ned_available(boundsfile)

    if use_ned:
        templatefile = open(os.path.join(templatedir, 'gb_ned.xml'), 'r')
        nedcachedir = os.path.join(workingdir, 'nedcache')
        if not os.path.exists(nedcachedir): os.makedirs(nedcachedir)    
    else:
        templatefile = open(os.path.join(templatedir, 'gb_no_ned.xml'), 'r')

    gbxml = templatefile.read()
    templatefile.close()


    gtfslist = ''
    for item in gtfsdirlist:
        gtfslist += '                        <bean class="org.opentripplanner.graph_builder.model.GtfsBundle">\n'
        gtfslist += '                            <property name="path" value="'+os.path.join(workingdir, 'gtfs', item)+'" />\n'
        gtfslist += '                        </bean>\n'

    if use_ned:
        gbxml = gbxml.format(graphpath=workingdir, gtfslist=gtfslist, osmpath=extractfile, nedcachepath=nedcachedir, awsaccesskey=settings.AWS_ACCESS_KEY_ID, awssecretkey=settings.AWS_SECRET_KEY, fare_factory=fare_factory)
    else:
        gbxml = gbxml.format(graphpath=workingdir, gtfslist=gtfslist, osmpath=extractfile, fare_factory=fare_factory)

    gbfilepath = os.path.join(workingdir, 'gb.xml')
    gbfile = open(gbfilepath, 'w')
    gbfile.write(gbxml)
    gbfile.close()


    # run graph builder

    print 'running OTP graph builder'
    otpjarpath = os.path.join(otpgbdir, 'graph-builder.jar')
    result = subprocess.Popen(["java", "-Xms14G", "-Xmx14G", "-jar", otpjarpath, gbfilepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    gb_stdout = result.stdout.read()
    gb_stderr = result.stderr.read()
    graphpath = os.path.join(workingdir, 'Graph.obj')
    graphsuccess = os.path.exists(graphpath) & os.path.getsize(graphpath) > 0
    
    results = {}
    
    results['success'] = graphsuccess
    results['output'] = 'STDOUT:\n\n%s\n\nSTDERR:\n\n%s' % (gb_stdout, gb_stderr) 
        
    return results

