#!/usr/bin/python

from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup import settings

import handlers

print "Starting Controller Consumer"

exchange = Exchange("amq.direct", type="direct", durable=True)

queues = [
    Queue("validation_done", exchange=exchange, routing_key="validation_done"),
    Queue("graph_done", exchange=exchange, routing_key="graph_done"),
    Queue("deployment_ready", exchange=exchange, routing_key="deployment_ready"),
    Queue("proxy_done", exchange=exchange, routing_key="proxy_done"),
    Queue("multideployer_ready", exchange=exchange, routing_key="multideployer_ready"),
    Queue("multideployment_done", exchange=exchange, routing_key="multideployment_done")
]

def handle(conn, body, message):
    
    key = message.delivery_info['routing_key']
    getattr(handlers, key)(conn, body)
    message.ack()

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queues, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()

