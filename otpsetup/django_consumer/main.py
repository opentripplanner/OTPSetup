#!/usr/bin/python

from django.core.mail import send_mail
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.client.models import InstanceRequest, GtfsFile
from otpsetup import settings
from django.core.urlresolvers import reverse

exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("validation_done", exchange=exchange, routing_key="validation_done")


def handle(conn, body, message):
    request_id = body['request_id']
    output = request['output']

    for gtfs_result in output:
        gtfs_file = GtfsFile.objects.get(s3_key=gtfs_result['key'])
        gtfs_file.validation_output = gtfs_result['errors']
        gtfs_file.save()

    irequest = InstanceRequest.objects.get(id=request_id)
    irequest.state = "submitted"
    irequest.save()

    url = reverse("otpsetup.client.adminviews.index")

    send_mail('OTP instance request pending', 
              """There is a new OTP instance request which has just completed 
validation.  The request is from %s %s <%s>.  

To approve it, go to %s

""" % (irequest.user.first_name, irequest.user.last_name, 
       irequest.user.email, url),
              settings.DEFAULT_FROM_EMAIL,
              settings.ADMIN_EMAILS, fail_silently=False)

    message.ack()

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queue, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()
