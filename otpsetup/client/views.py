#!/usr/bin/python

from otpsetup.client.models import InstanceRequestForm, InstanceRequest, GtfsFile
from datetime import datetime, timedelta
from subprocess import call

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.http import HttpResponse

from boto import connect_s3
from boto.s3.key import Key

from json import dumps
from kombu import Exchange

from otpsetup.shortcuts import render_to_response
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.shortcuts import check_for_running_instance

import base64
import hmac, sha
import uuid

def index(request):   
    return render_to_response(request, 'index.html')

def download_graph(request):
    try:
        key = request.REQUEST['key']
    except KeyError:
        return HttpResponse("You must specify a graph key")
    else:
        s3_id = base64.b64decode(key)
        s3_conn = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)        
        bucket = s3_conn.get_bucket(settings.GRAPH_S3_BUCKET)
        
        key = Key(bucket)
        key.key = 'uploads/' + s3_id
        s3_id = s3_id.replace('/', '_')
        path = '/tmp/'+s3_id
        zippath = path + '.zip'
        key.get_contents_to_filename(path)
        call(['zip', '-j', zippath, path])
         
        graph_file = open(zippath, 'rb')
        response = HttpResponse(graph_file, mimetype='application/x-zip-compressed')
        response['Content-Disposition'] = 'attachment; filename=Graph.zip' 
        return response

@login_required
def create_request(request):
    if request.method == "GET":
        return render_to_response(request, 'create_request.html', locals())
    else:
        form = InstanceRequestForm(request.REQUEST)
        irequest = form.save(commit=False)
        irequest.user = request.user
        irequest.ip = request.META['REMOTE_ADDR']
        irequest.state = 'building'
        irequest.save()
        return redirect("/upload?request_id=%s" % irequest.id)

@login_required
def upload(request):
    #todo: prevent too many uploads by the same IP address
    request_id = request.GET['request_id']
    irequest = InstanceRequest.objects.get(id=request_id)
    if irequest.user != request.user:
        return redirect("/")

    uploaded = irequest.gtfsfile_set.count()
    files = [ ]
    for file in irequest.gtfsfile_set.all():
        file_name = file.s3_key if (file.s3_key is not None) else file.transload_url
        file_obj = { 'name' : file_name, 'id' : file.id }
        files.append(file_obj)

    base_filename = "uploads/%s/%s_" % (request_id, str(uuid.uuid4()))
    upload_filename = base_filename + "${filename}"
    aws_access_key_id = settings.AWS_ACCESS_KEY_ID

    after_upload_url = request.build_absolute_uri("/done_upload")

    policy = make_s3_policy(base_filename, after_upload_url)
    base64_policy = base64.b64encode(policy)
    signature = s3_sign(policy, settings.AWS_SECRET_KEY)

    s3_bucket = settings.S3_BUCKET
    return render_to_response(request, 'upload.html', locals())

@login_required
def done_upload(request):
    #get the instance request id out of the key
    key = request.REQUEST['key']
    _1, request_id, _2 = key.split("/")
    irequest = InstanceRequest.objects.get(id=request_id)
    if irequest.user != request.user:
        return redirect("/")

    gtfs_file = GtfsFile(instance_request=irequest, s3_key=key)
    gtfs_file.save()

    return redirect("/upload?request_id=%s" % irequest.id)

@login_required
def remove_gtfs(request):
    request_id = request.REQUEST['request_id']
    gtfsfile_id = request.REQUEST['gtfsfile_id']    
    gtfsfile = GtfsFile.objects.get(id=gtfsfile_id)
    gtfsfile.delete()

    return redirect("/upload?request_id=%s" % request_id)

@login_required
def transload(request):
    request_id = request.REQUEST['request_id']
    irequest = InstanceRequest.objects.get(id=request_id)
    uploaded = irequest.gtfsfile_set.count()
    return render_to_response(request, 'transload.html', locals())

@login_required
def done_transload(request):
    request_id = request.REQUEST['request_id']
    irequest = InstanceRequest.objects.get(id=request_id)
    if irequest.user != request.user:
        return redirect("/")

    gtfs_file = GtfsFile(instance_request=irequest, transload_url=request.REQUEST['transload_url'])
    gtfs_file.save()

    return redirect("/upload?request_id=%s" % request_id)

@login_required
def finalize_request(request):
    request_id = request.POST['request_id']
    irequest = InstanceRequest.objects.get(id=request_id)
    if irequest.user != request.user:
        return redirect("/")

    exchange = Exchange("amq.direct", type="direct", durable=True)
    conn = DjangoBrokerConnection()

    publisher = conn.Producer(routing_key="transload",
                              exchange=exchange)

    transloading=False
    s3_keys = []
    to_transload = []
    for gtfs_file in irequest.gtfsfile_set.all():
        if gtfs_file.transload_url:
            transloading = True
            to_transload.append(gtfs_file)
        else:
            s3_keys.append(gtfs_file.s3_key)

    if transloading:
        irequest.state = 'pre_transload'
        irequest.save()
        for gtfs_file in to_transload:
            publisher.publish({"transload": gtfs_file.transload_url, "gtfs_file_id" : gtfs_file.id})
    else:
        irequest.state = 'submitted'
        irequest.save()
        publisher = conn.Producer(routing_key="validate_request",
                                  exchange=exchange)
        publisher.publish({"files" : s3_keys, "request_id" : irequest.id})
        
        # start validator instance, if needed
        check_for_running_instance(settings.VALIDATOR_AMI_ID)
        
    publisher.close()

    return render_to_response(request, 'request_submitted.html', locals())

def make_s3_policy(base_filename, url):
    expiration =  datetime.utcnow() + timedelta(0,500)

    policy = {
        "expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conditions": [
            {"bucket": settings.S3_BUCKET}, 
            ["starts-with", "$key", base_filename],
            {"acl": "private"},
            {"success_action_redirect": url},
            ["content-length-range", 1024, 1024*1024*300]
            ]
     }
    return dumps(policy)

def s3_sign(doc, key):
    policy = base64.b64encode(doc)
    signature = base64.b64encode(hmac.new(key, policy, sha).digest())
    return signature

