from kombu import BrokerConnection

from django.conf import settings
from django.shortcuts import render_to_response as orig_render_to_response
from django.template import RequestContext

def render_to_response(req, *args, **kwargs):
    kwargs['context_instance'] = RequestContext(req)
    return orig_render_to_response(*args, **kwargs)

def DjangoBrokerConnection():

    return BrokerConnection("amqp://%s:%s@%s:%s/%s" % (
            settings.BROKER_USER,
            settings.BROKER_PASSWORD,
            settings.BROKER_HOST or "localhost",
            settings.BROKER_PORT or "5672",
            settings.BROKER_VHOST or "/"))
