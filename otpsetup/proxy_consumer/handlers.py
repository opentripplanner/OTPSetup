#!/usr/bin/python

from kombu import Exchange
from otpsetup import settings

import subprocess

# legacy message handler:

exchange = Exchange("amq.direct", type="direct", durable=True)

def setup_proxy(conn, body):

    if not 'request_id' in body or not 'hostname' in body:
        print 'message missing required parameters'
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

# multideployer message handler:

def init_proxy_multi(conn, body): 

    host_id = body['host_id']
    host_ip = body['host_ip']

    site_config  = open('/etc/nginx/sites-enabled/host-%s' % host_id, 'w')

    site_config.write('server {\n')
    site_config.write('    listen       80;\n')
    site_config.write('    server_name  host-%s.deployer.opentripplanner.org;\n' % host_id)
    site_config.write('\n')
    site_config.write('    location / {\n')
    site_config.write('      proxy_pass     http://%s:8080;\n' % host_ip)
    site_config.write('    }\n')
    site_config.write('}\n')

    site_config.close()

    subprocess.call(['/etc/init.d/nginx','reload'])


def register_proxy_multi(conn, body):

    if not 'request_id' in body or not 'host_ip' in body:
        print 'message missing required parameters'
        return
   
    request_id = body['request_id']
    host_ip = body['host_ip']
    
    site_config  = open('/etc/nginx/sites-enabled/site-%s' % request_id, 'w')

    site_config.write('server {\n')
    site_config.write('    listen       80;\n')
    site_config.write('    server_name  req-%s.deployer.opentripplanner.org;\n' % request_id)
    site_config.write('\n')
    site_config.write('    location / {\n')
    site_config.write('      proxy_pass     http://%s:8080/otp-webapp-req-%s/;\n' % (host_ip, request_id))
    site_config.write('    }\n')
    site_config.write('\n')
    site_config.write('    location /opentripplanner-api-webapp {\n')
    site_config.write('      proxy_pass     http://%s:8080;\n' % host_ip)
    site_config.write('    }\n')
    site_config.write('}\n')

    site_config.close()
    
    subprocess.call(['/etc/init.d/nginx','reload'])

    public_url = "http://req-%s.deployer.opentripplanner.org" % request_id

    # tell controller that proxy mapping is complete
    publisher = conn.Producer(routing_key="proxy_done", exchange=exchange)
    publisher.publish({'request_id' : request_id, 'public_url' : public_url})

