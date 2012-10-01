#!/usr/bin/python

from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection, build_multi_queue
from otpsetup import settings
from datetime import datetime
import traceback

import handlers

print "Starting Controller Consumer"

queues = build_multi_queue(["validation_done", "graph_done", "rebuild_graph_done", "managed_graph_done", "process_gtfs_done", "osm_extract_done", "deployment_ready", "proxy_done", "multideployer_ready", "multideployment_done"])

def handle(conn, body, message):
    
    key = message.delivery_info['routing_key']
    print "handling key "+key
    try: 
        getattr(handlers, key)(conn, body)
    except:
        print "handler error"
        now = datetime.now()
        errfile = "/var/otp/cc_err_%s_%s" % (key, now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))
    message.ack()

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queues, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()

