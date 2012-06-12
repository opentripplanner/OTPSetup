#!/usr/bin/python

from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.shortcuts import stop_current_instance
from otpsetup import settings
from datetime import datetime
import traceback

import handlers

print "Starting Graph Builder Consumer"

exchange = Exchange("amq.direct", type="direct", durable=True)

queues = [
    Queue("create_instance", exchange=exchange, routing_key="create_instance"),
    Queue("rebuild_graph", exchange=exchange, routing_key="rebuild_graph")
]

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
            
stop_current_instance()


