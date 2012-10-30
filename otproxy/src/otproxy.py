from cube import Cube
from datetime import datetime
from gevent import Greenlet
from gevent.pool import Pool
from gevent.wsgi import WSGIServer

from gevent import monkey
monkey.patch_socket() #must be done before loading httplib2

from json import loads, dumps
from math import floor, ceil
from random import randint
from threading import Lock
from time import time
from urlparse import parse_qs

import httplib2
import hmac
import logging
import logging.config
import re
import socket
import wsgiref.util
import yaml

cube = Cube()

secrets = {}
f = open("secrets.txt")
for line in f:
    if line.startswith("#"):
        continue
    key, secret = line.strip().split(":")
    secrets[key] = secret

regions = []
router_list_url = "http://test.deployer.opentripplanner.org/get_servers?groups=otpna"

config = yaml.load(open('logging.conf', 'r'))
logging.config.dictConfig(config)

LOGGER = logging.getLogger("error")
REQUEST_LOGGER = logging.getLogger("otp.request")
logging.basicConfig(filename='access.log',level=logging.DEBUG)

lock = Lock()

def init():
    urls = get_server_list(router_list_url)
    if urls:
        load_all_server_data(urls)
        return True
    return False

def get_server_list(url):
    h = httplib2.Http()
    resp, content = h.request(url, "GET",
                              headers={'Accept':'application/json'} )
    if resp['status'] != '200':
        return None
    urls = content.split(",")
    return urls

def load_all_server_data(urls):
    #load up a list of server domains, which it would be nice to get from
    #somewhere sensible but which for now we will hardcode
    lock.acquire()
    try:
        global regions
        regions = []
        for url in urls:
            load_server_data(url)
    finally:
        lock.release()

def make_bbox(coords):
    minx = miny = maxx = maxy = None

    for coord in coords:
        if isinstance(coord, list) and isinstance(coord[0], list):
            if minx:
                nminx, nminy, nmaxx, nmaxy = make_bbox(coord)
                if nminx < minx: minx = nminx
                if nminy < miny: miny = nminy
                if nmaxx > maxx: maxx = nmaxx
                if nmaxy > maxy: maxy = nmaxy
            else:
                minx, miny, maxx, maxy = make_bbox(coord)

        else:
            x,y = coord
            if miny:
                if x < minx: minx = x
                if y < miny: miny = y
                if x > maxx: maxx = x
                if y > maxy: maxy = y
            else:
                minx = maxx = x
                miny = maxy = y

    return minx, miny, maxx, maxy



def make_bbox_record(coords):
    minx, miny, maxx, maxy = make_bbox(coords)
    return {'maxx' : maxx, 'maxy' : maxy, 'minx' : minx, 'miny' : miny}


VERTICAL_REGIONS=1000

def index_coords (coords, bbox, index = None):
    """Create an index of the given polygon; the index divides the
    polygon into VERTICAL_REGIONS+1 vertically stacked regions, with
    each region having a list of all of the edges of the polygon
    which pass through it.  For sensible polygons, this allows
    constant-time containment tests, and for insane polygons, it's
    no worse than not having it.
    """
    if not index:
        index = []
        for i in range(VERTICAL_REGIONS + 1):
            index.append([])

    min_lat = bbox['miny']
    max_lat = bbox['maxy']
    lat_range = max_lat - min_lat
    scaling = VERTICAL_REGIONS / lat_range

    for poly in coords:
        if isinstance(poly[0][0], list):
            for inner in poly:
                index_coords(inner, bbox, index)
        else:
            n = len(poly)
            for i in range(n):
                lon1 = poly[i][0]
                lat1 = poly[i][1]
                lon2 = poly[(i+1) % n][0]
                lat2 = poly[(i+1) % n][1]

                if lat1 > lat2:
                    lat1, lon1, lat2, lon2 = lat2, lon2, lat1, lon1


                scaled_lat1 = int(floor((lat1 - min_lat) * scaling))
                scaled_lat2 = int(ceil((lat2 - min_lat) * scaling))
                for y in range(scaled_lat1, scaled_lat2):
                    index[y].append([lon1, lat1, lon2, lat2])

    return index


def load_server_data(url):
    global regions

    rurl = url + '/ws/routers'
    h = httplib2.Http()
    try:
        resp, content = h.request(rurl, "GET",
                                  headers={'Accept':'application/json'} )
    except socket.error, e:
        LOGGER.warn("Failed to load " + rurl + ": %s" % e)
        return

    if resp['status'] != '200':
        return

    json = loads(content)
    items = json['routerInfo']
    for router in items:

        #this varies across OTP versions
        if 'RouterInfo' in router:
            routerInfo = router['RouterInfo']
        else:
            routerInfo = router
        coords = routerInfo['polygon']['coordinates']
        #coords is a list of lists of 2-element lists we would like to check it
        #against the existing regions
        found = False
        for oldregion in regions:
            if oldregion['poly'] == coords:
                newrouter = {'url' : url,
                             'routerId' : routerInfo['routerId']}
                oldregion['routers'].append(newrouter)
                found = True
                break
        if found:
            continue

        #no existing region
        bbox = make_bbox_record(coords)
        newrouter = {
            'indexed' : index_coords(coords, bbox),
            'poly' : coords,
            'bbox' : bbox,
            'routers':[{'url' : url,
                        'routerId' : routerInfo['routerId']}]
            }

        regions.append(newrouter)


#figure out which region this point is in
def get_region(lat, lon):
    output = []

    for region in regions:
      poly = region['poly']
      crossings = 0
      poly = poly[0] #first polygon, excluding holes
      n = len(poly)
      for i in range(n):
          lon1 = poly[i][0]
          lat1 = poly[i][1]
          lon2 = poly[(i+1) % n][0]
          lat2 = poly[(i+1) % n][1]
          if lat1 > lat2:
              (lat1, lon1, lat2, lon2) = (lat2, lon2, lat1, lon1)


          if lat1 <= lat and lat < lat2:
              p = (lat - lat1) / (lat2 - lat1)
              lonp = p * (lon2 - lon1) + lon1
              if lonp > lon:
                  crossings += 1

      if crossings % 2 == 1:
          output.append(region)

    return output


def get_regions_indexed(lat, lon):
    output = []

    for region in regions:
      bbox = region['bbox']
      (minx, miny, maxx, maxy) = (bbox['minx'],
                                  bbox['miny'],
                                  bbox['maxx'],
                                  bbox['maxy'])

      if minx > lon or maxx < lon or miny > lat or maxy < lat:
          continue
     
      indexed = region['indexed']

      lat_range = maxy - miny
      scaling = VERTICAL_REGIONS / lat_range
      index = int (scaling * (lat - miny))

      crossings = 0
      for seg in indexed[index]:
          (lon1, lat1, lon2, lat2) = seg
          if lat1 <= lat and lat < lat2:
              p = (lat - lat1) / (lat2 - lat1)
              lonp = p * (lon2 - lon1) + lon1
              if lonp > lon:
                  crossings += 1

      if crossings % 2 == 1:
          output.append(region)

    return output

def test():
    init()
    print "nonindexed: " + get_region(41.5, -73.1)
    print "indexed: " + get_regions_indexed(45.5, -122.91)


place_re = re.compile("((?:.*::)?)(.*)")

def check_endpoints(args):
    #points - a json array of json arrays, each with a length of 2,
    #index 0 is lon, index 1 is lat [ [ -111.3, 40.1 ], [ -90.0, 43.5
    #], [ -101.1, 39 ] ]

    points = loads(args['points'][0])

    # constrainToSingleGraph - boolean, true or false
    #if false, the length of the response
    # array must equal the length of the request array, each response
    # item corresponding to the request item of the same index

    #if true, the response array will have a length of 1 and be true
    #if all request points are in the same graph, and false if at
    #least one of the request points is in a different graph than any
    #other request point

    constrain = loads(args['constrainToSingleGraph'][0])

    graphs = set()
    started = False
    out = []
    lock.acquire()
    try:
        for lon, lat in points:
            regions = get_regions_indexed(lat, lon)
            out.append(len(regions) > 0)

            routers = []
            for region in regions:
                for router in region['routers']:
                    routers.append(router['url'] + '?' + router['routerId'])
            if not started:
                started = True
                if len(regions) == 0 and constrain:
                    return [False]
                else:
                    graphs.update(routers)
            else:
                graphs.insersection_update(regions)
                if graphs.size() == 0:
                    return [False]
    finally:
        lock.release()
    if constrain:
        return [True]
    return out

def check_query_signature(args):
    api_key = args.get('apiKey', ' ')[0]
    if not api_key in secrets:
        return False

    secret = secrets[api_key]
    if secret == 'test':
        return True
    h = hmac.new(secret)

    h.update(api_key + args['fromPlace'][0] + args['toPlace'][0])
    return h.hexdigest() == args.get('signature', '')[0]

def log_request(environ, router, duration, status):

    def log():
        #request time, URL, API key, router selected, and
        #subrequest duration
        args = parse_qs(environ['QUERY_STRING'])
        api_key = args.get('apiKey', ['None'])[0]

        uri = wsgiref.util.request_uri(environ)
        REQUEST_LOGGER.info("%s %s %s %s %s", status, uri, api_key, router, duration)

        data = {"status" : status,
                "uri" : uri,
                "api_key" : api_key,
                "router" : router,
                "duration" : duration,
                "time" : datetime.now().isoformat(),
                }
        if 'fromPlace' in args:
            data['fromPlace'] = args['fromPlace'][0]
        if 'toPlace' in args:
            data['toPlace'] = args['toPlace'][0]
        cube.put("request", data)
    Greenlet.spawn(log)

def handle(environ, start_response):

    if not regions:
        init()

    args = parse_qs(environ['QUERY_STRING'])

    if environ['PATH_INFO'] == "/check-endpoints":
        start_response('200 OK', [])
        startTime = time()
        response = dumps(check_endpoints(args))
        log_request(environ, None, time() - startTime, 200)
        return [response]

    if not environ['PATH_INFO'] == '/opentripplanner-api-webapp/ws/plan':
        response_headers = [('Content-Type', 'text/plain')]
        start_response('404 Not found', response_headers)
        log_request(environ, None, 0, 404)
        return ["Not found"]

    if not check_query_signature(args):
        response_headers = [('Content-Type', 'text/plain')]
        start_response('403 Forbidden', response_headers)
        log_request(environ, None, 0, 403)
        return ["Forbidden"]

    if 'reload' in args:
        if init():
            log_request(environ, None, 0, 200)
            start_response('200 OK', [])
            return ["Reloaded"]
        else:
            log_request(environ, None, 0, 500)
            start_response('500 Internal Server Error', [])
            return ["Failed to reload"]

    startTime = time()

    fromPlace = args['fromPlace'][0]
    toPlace = args['toPlace'][0]

    lat, lon = map(float, place_re.match(fromPlace).group(2).split(","))

    lock.acquire()
    try:
        from_regions = get_regions_indexed(lat, lon)
        if len(from_regions):
            lat, lon = map(float, place_re.match(toPlace).group(2).split(","))
            to_regions = get_regions_indexed(lat, lon)
        else:
            to_regions = []
    finally:
        lock.release()

    found = False
    for region in from_regions:
        if not region in to_regions:
            #consider only regions in both from & to region sets
            continue
        found = True
        routers = region['routers']
        nrouters = len(routers)
        start = randint(0,nrouters)
        for router in routers[start:] + routers[:start]:
            url = router['url'] + "/ws/plan" + '?' + environ['QUERY_STRING'] + "&routerId=" + router['routerId']
            try:
                h = httplib2.Http()
                headers = dict((var[5:], val) for var, val in environ.items() if var.startswith("HTTP_"))

                h.timeout = 12 #seconds
                resp, content = h.request(url, "GET",
                                          headers=headers)

                status = resp.pop('status')
                if not status.startswith('200'):
                    #bad response. This might mean some kind of error.  We
                    #would like to log it, and try another server if there
                    #is one
                    log.error("Status " + status + " while processing " + url + "\n")
                    continue

                if 'transfer-encoding' in resp:
                    del resp['transfer-encoding']
                log_request(environ, None, time() - startTime, 200)
                start_response("200 OK", resp.items())
                return [content]
            except IOError, e:
                log.error("IOError while processing " + url + "\n" + e)

    if found:
        status = '500 Internal Server Error'
        response_headers = [('Content-Type', 'text/plain')]
        start_response(status, response_headers)
        log_request(environ, None, time() - startTime, 500)
        return ["There was a server that could have answered, but it didn't."]
    else:
        status = '404 Not Found'
        response_headers = [('Content-Type', 'text/plain')]
        start_response(status, response_headers)
        log_request(environ, None, time() - startTime, 404)
        return ["lat, lon %s, %s is out of range " % (lat, lon)]


pool = Pool(10000)
server = WSGIServer(('0.0.0.0', 1234), handle, spawn=pool)
server.serve_forever()
