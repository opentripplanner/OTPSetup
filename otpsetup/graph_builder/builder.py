import os
import subprocess
from otpsetup import settings

templatedir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'templates')
osmosisdir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'osmosis')
osmtoolsdir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'osmtools')
graphannodir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'graphanno')
otpgbdir = os.path.join(settings.GRAPH_BUILDER_RESOURCE_DIR, 'otpgb')

def build_graph(workingdir): 

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
    cmd = 'java -jar '+os.path.join(osmtoolsdir, 'osmtools.jar')+' '+stopsdir+' '+polyfile
    os.system(cmd)


    # run osm extract

    extractfile = workingdir+'/extract.osm'
    cmd = os.path.join(osmosisdir,'bin/osmosis')+' --rb '+settings.PLANET_OSM_PATH+' --bounding-polygon file='+polyfile+' --wx '+extractfile
    print cmd
    os.system(cmd)


    # generate graph-builder config file
    if settings.NED_ENABLED:
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

    if settings.NED_ENABLED:
        gbxml = gbxml.format(graphpath=workingdir, gtfslist=gtfslist, osmpath=extractfile, nedcachepath=nedcachedir, awsaccesskey=settings.AWS_ACCESS_KEY_ID, awssecretkey=settings.AWS_SECRET_KEY)
    else:
        gbxml = gbxml.format(graphpath=workingdir, gtfslist=gtfslist, osmpath=extractfile)

    gbfilepath = os.path.join(workingdir, 'gb.xml')
    gbfile = open(gbfilepath, 'w')
    gbfile.write(gbxml)
    gbfile.close()


    # run graph builder

    print 'running OTP graph builder'
    otpjarpath = os.path.join(otpgbdir, 'graph-builder.jar')
    result = subprocess.Popen(["java", "-Xms2G", "-Xmx2G", "-jar", otpjarpath, gbfilepath], stdout=subprocess.PIPE)
    
    gb_stdout = result.stdout.read()
    graphpath = os.path.join(workingdir, 'Graph.obj')
    graphsuccess = os.path.exists(graphpath)
    
    results = {}
    
    results['success'] = graphsuccess
    if graphsuccess:
        # if successful, read graph annotations as output
        annoresult = subprocess.Popen(["java", "-Xms2G", "-Xmx2G", "-jar", os.path.join(graphannodir, 'graphanno.jar'), graphpath], stdout=subprocess.PIPE)
        results['output'] = annoresult.stdout.read()        
    else:
        # if failure, store graphbuilder stdout as output
        results['output'] = gb_stdout
        
    return results
    

