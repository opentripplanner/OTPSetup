#!/usr/bin/python

from boto import connect_s3
from boto.s3.key import Key

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import permission_required
from django.shortcuts import redirect

from json import dumps
from kombu import Exchange

from otpsetup.client.models import InstanceRequest, GtfsFile
from otpsetup.shortcuts import render_to_response
from otpsetup.shortcuts import DjangoBrokerConnection

import base64
import hmac, sha

@permission_required('admin')
def index(request):
    requests = InstanceRequest.objects.all()
    return render_to_response(request, 'admin/index.html', locals())

@permission_required('admin')
def approve_request(request):
    irequest = InstanceRequest.objects.get(id=request.REQUEST['request_id'])

    exchange = Exchange("amq.direct", type="direct", durable=True)
    conn = DjangoBrokerConnection()

    publisher = conn.Producer(routing_key="create_instance",
                              exchange=exchange)

    action = request.REQUEST['action']
    if action == "Cancel":
        irequest.state = "rejected"
        connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
        bucket = connection.get_bucket(settings.S3_BUCKET)
        for gtfs in irequest.gtfsfile_set.all():
            key = Key(bucket)
            key.key = gtfs.s3_key
            key.delete()

            

    elif action == "Approve":
        irequest.state = "approved"
        files = [gtfsfile.s3_key for gtfsfile in irequest.gtfsfile_set.all()]
        publisher.publish({"files": files})
    irequest.save()
    return redirect("/admin")
