#!/usr/bin/python

from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.shortcuts import stop_current_instance, build_multi_queue
from otpsetup import settings
from datetime import datetime
import traceback

import handlers

import process_gtfs, transformer

print "Starting Graph Builder Consumer"

#merged_path = "/mnt/merged.zip"
#transformed_path = "/var/otp/transformed.zip"
#transformer.run_transform(merged_path, transformed_path)

queues = build_multi_queue(["create_instance", "rebuild_graph", "build_managed", "build_managed_osm", "process_gtfs"])

def handle(conn, body, message):
    
    key = message.delivery_info['routing_key']
    print "handling key "+key
    try: 
        getattr(handlers, key)(conn, body)
    except:
        print "gb handler error"
        now = datetime.now()
        errfile = "/var/otp/gb_err_%s_%s" % (key, now.strftime("%F-%T"))
        traceback.print_exc(file=open(errfile,"a"))
    message.ack()

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queues, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        try:
            while True:
                conn.drain_events(timeout=600)
        except:
            print "exited loop"            
    conn.close()
            
#stop_current_instance()


