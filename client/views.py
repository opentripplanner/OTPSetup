#!/usr/bin/python

from carrot.connection import DjangoBrokerConnection
from carrot.messaging import Publisher

from otpsetup.client.models import InstanceRequestForm, InstanceRequest, GtfsFile
from datetime import datetime, timedelta

from otpsetup.client.shortcuts import render_to_response
from django.conf import settings
from django.shortcuts import redirect

from json import dumps

import base64
import hmac, sha

def index(request):   
    return render_to_response(request, 'index.html')

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

def upload(request):
    #todo: prevent too many uploads by the same IP address
    request_id = request.GET['request_id']
    irequest = InstanceRequest.objects.get(id=request_id)
    if irequest.user != request.user:
        return redirect("/")

    uploaded = irequest.gtfsfile_set.count()

    upload_filename = "uploads/%s/%s" % (request_id, datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.zip"))
    aws_access_key_id = settings.AWS_ACCESS_KEY_ID

    after_upload_url = request.build_absolute_uri("/done_upload")

    policy = make_s3_policy(upload_filename, after_upload_url)
    base64_policy = base64.b64encode(policy)
    signature = s3_sign(policy, settings.AWS_SECRET_KEY)

    s3_bucket = settings.S3_BUCKET
    return render_to_response(request, 'upload.html', locals())

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

def transload(request):
    request_id = request.GET['request_id']
    irequest = InstanceRequest.objects.get(id=request_id)
    uploaded = irequest.gtfsfile_set.count()
    return render_to_response(request, 'transload.html', locals())

def done_transload(request):

    irequest = InstanceRequest.objects.get(id=request_id)
    if irequest.user != request.user:
        return redirect("/")

    gtfs_file = GtfsFile(instance_request=irequest, transload_url=request.GET['transload_url'])
    gtfs_file.save()

    return render_to_response(request, 'done_transload.html', locals())

def finalize_request(request):
    request_id = request.POST['request_id']
    irequest = InstanceRequest.objects.get(id=request_id)
    if irequest.user != request.user:
        return redirect("/")

    conn = DjangoBrokerConnection()

    publisher = Publisher(connection=conn,
                          routing_key="transload")
    transloading=False
    s3_keys = []
    for gtfs_file in irequest.gtfsfile_set.all():
        if gtfs_file.transload_url:
            transloading = True
            publisher.send({"transload": gtfs_file.transload_url, "id" : gtfs_file.id})
            publisher.close()
        else:
            s3_keys.append(gtfs_file.s3_key)
    if transloading:
        irequest.state = 'pre_transload'
    else:
        publisher = Publisher(connection=conn,
                              routing_key="validate_request")
        publisher.send({"files" : s3_keys, "request_id" : irequest.id})
        irequest.state = 'submitted'
    irequest.save()
    return render_to_response(request, 'request_submitted.html', locals())

def make_s3_policy(filename, url):
    expiration =  datetime.utcnow() + timedelta(0,500)

    policy = {
        "expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conditions": [
            {"bucket": settings.S3_BUCKET}, 
            {"key" : filename},
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
