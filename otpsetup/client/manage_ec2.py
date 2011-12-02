from boto import connect_s3, connect_ec2

from otpsetup.client.models import AmazonMachineImage, InstanceRequestForm, InstanceRequest, GtfsFile
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import permission_required
from django.shortcuts import redirect

from json import dumps

from otpsetup.shortcuts import render_to_response
from otpsetup.shortcuts import DjangoBrokerConnection

import base64
import hmac, sha

@permission_required('admin')
def index(request):   
    conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    reservations = conn.get_all_instances()
    running_instances = []
    for reservation in reservations:
        for instance in reservation.instances:
            image = AmazonMachineImage.objects.get(ami_id=instance.image_id)
            running_instances.append(dict(image=image, instance=instance))

    images = AmazonMachineImage.objects.all()
    return render_to_response(request, 'manage_ec2/index.html', locals())

@permission_required('admin')
def start_instance(request):
    image_obj = AmazonMachineImage.objects.get(id=request.REQUEST['image_id'])
    conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)

    image = conn.get_image(image_obj.ami_id)
    image.run()
    return redirect('/manage_ec2')

@permission_required('admin')
def stop_instance(request):
    conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    instance_id = request.REQUEST['instance_id']
    conn.stop_instances([instance_id])
    return redirect('/manage_ec2')
