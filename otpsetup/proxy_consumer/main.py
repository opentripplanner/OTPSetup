#!/usr/bin/python

from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup import settings

import handlers

print "Starting Proxy Consumer"

exchange = Exchange("amq.direct", type="direct", durable=True)

queues = [
    Queue("setup_proxy", exchange=exchange, routing_key="setup_proxy"),
    Queue("init_proxy_multi", exchange=exchange, routing_key="init_proxy_multi"),
    Queue("register_proxy_multi", exchange=exchange, routing_key="register_proxy_multi")
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

