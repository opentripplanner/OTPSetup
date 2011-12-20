import os
from subprocess import call
from otpsetup import settings

#TODO: move these to settings.py?
templatedir = '/home/demory/otp/hd/templates'
osmosisdir = '/home/demory/osm/osmosis'
osmtoolsdir = '/home/demory/otp/hd/osmtools'
otpgbdir = '/home/demory/otp/src1206/OpenTripPlanner'
pbffile = '/home/demory/osm/data/us-east.pbf'
usened = True;

def build_graph(workingdir): 

    print "wd: "+workingdir
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
    cmd = os.path.join(osmosisdir,'bin/osmosis')+' --rb '+pbffile+' --bounding-polygon file='+polyfile+' --wx '+extractfile
    print cmd
    os.system(cmd)


    # generate graph-builder config file
    if usened:
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

    if usened:
        gbxml = gbxml.format(graphpath=workingdir, gtfslist=gtfslist, osmpath=extractfile, nedcachepath=nedcachedir, awsaccesskey=settings.AWS_ACCESS_KEY_ID, awssecretkey=settings.AWS_SECRET_KEY)
    else:
        gbxml = gbxml.format(graphpath=workingdir, gtfslist=gtfslist, osmpath=extractfile)

    gbfile = open(os.path.join(workingdir, 'gb.xml'), 'w')
    gbfile.write(gbxml)
    gbfile.close()


    # run graph builder

    cmd = 'java -Xms2G -Xmx2G -jar '+os.path.join(otpgbdir, 'opentripplanner-graph-builder', 'target', 'graph-builder.jar')+' '+os.path.join(workingdir,'gb.xml')
    #print cmd
    os.system(cmd)

