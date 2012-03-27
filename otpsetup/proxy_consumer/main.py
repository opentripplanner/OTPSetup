#!/usr/bin/python

from django.core.mail import send_mail
from kombu import Exchange, Queue
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup import settings

import subprocess, sys

exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("setup_proxy", exchange=exchange, routing_key="setup_proxy")

print "Starting Proxy Consumer"

def handle(conn, body, message):

    if not 'request_id' in body or not 'hostname' in body:
        print 'message missing required parameters'
        message.ack()
        return
   
    request_id = body['request_id']
    print 'request: %s' % request_id
    hostname = body['hostname']
    
    hostname = hostname[3:].replace('-','.')

    site_config  = open('/etc/nginx/sites-enabled/site-%s' % request_id, 'w')

    site_config.write('server {\n')
    site_config.write('    listen       80;\n')
    site_config.write('    server_name  req-%s.deployer.opentripplanner.org;\n' % request_id)
    site_config.write('\n')
    site_config.write('    access_log   /var/log/nginx/dep-%s.access.log;\n' % request_id)
    site_config.write('\n')
    site_config.write('    location / {\n')
    site_config.write('      proxy_pass     http://%s:8080;\n' % hostname)
    site_config.write('    }\n')
    site_config.write('}\n')

    site_config.close()
    
    subprocess.call(['/etc/init.d/nginx','reload'])

    public_url = "http://req-%s.deployer.opentripplanner.org" % request_id

    # tell controller that proxy mapping is complete
    publisher = conn.Producer(routing_key="proxy_done", exchange=exchange)
    publisher.publish({'request_id' : request_id, 'public_url' : public_url})

    message.ack()

with DjangoBrokerConnection() as conn:

    with conn.Consumer(queue, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()

