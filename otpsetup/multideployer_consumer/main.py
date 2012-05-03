#!/usr/bin/python

from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup import settings

import handlers

print "Starting Multideployer Consumer"

exchange = Exchange("amq.direct", type="direct", durable=True)

queues = [
    Queue("deploy_graph_multi", exchange=exchange, routing_key="deploy_graph_multi"),
    Queue("undeploy_graph_multi", exchange=exchange, routing_key="undeploy_graph_multi")
]

def handle(conn, body, message):
    
    key = message.delivery_info['routing_key']
    if getattr(handlers, key)(conn, body):
        message.ack()
    else:
        message.requeue()


with DjangoBrokerConnection() as conn:

    with conn.Consumer(queues, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()

