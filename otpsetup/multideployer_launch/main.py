from otpsetup.shortcuts import DjangoBrokerConnection, download_otp_wars, stop_current_instance
from otpsetup import settings

from boto import connect_ec2
from kombu import Exchange, Queue

import os, sys, subprocess, base64, urllib2, string, time, socket
from random import choice

exchange = Exchange("amq.direct", type="direct", durable=True)
queue = Queue("launch_multideployer", exchange=exchange, routing_key="launch_multideployer")

def wait_for_tomcat():
    
    attempt = 0
    max_attempts = 10
    success = False
    
    while (attempt < max_attempts):
        try: 
            url ='http://localhost:8080/'
            req = urllib2.Request(url, None, { })
            urllib2.urlopen(req)
            success = True; # only reached if page loads successfully
            break
        except: 
            attempt = attempt + 1
            time.sleep(10)
    
    return success
    

deployer_resources_dir = '/var/otp/OTPSetup/deployer_resources'
tomcat_home = '/var/lib/tomcat6'
initfile = '/var/otp/init'

def handle(conn, body, message):

    print "begin"

    # write tomcat-users file
    tutemplate = open(os.path.join(deployer_resources_dir, 'tomcat-users.xml'), 'r')
    tuxml = tutemplate.read()
    tutemplate.close()

    tuxml = tuxml.format(password=settings.TOMCAT_ADMIN_PASSWORD)

    tufilepath = os.path.join(tomcat_home, 'conf/tomcat-users.xml')
    tufile = open(tufilepath, 'w')
    tufile.write(tuxml)
    tufile.close()

    print "wrote users"

    # start & wait for tomcat
    subprocess.call(['/etc/init.d/tomcat6', 'start'])        
    tomcat_launched = wait_for_tomcat()

    print "tomcat started"
        
    # download latest wars
    download_otp_wars()

    print "downloaded wars"

    # deploy otp-api-webapp on tomcat
    encodedstring = base64.encodestring("admin:%s" % settings.TOMCAT_ADMIN_PASSWORD)[:-1]
    auth = "Basic %s" % encodedstring

    url ='http://localhost:8080/manager/install?path=/opentripplanner-api-webapp&war=/var/otp/wars/opentripplanner-api-webapp.war'
    req = urllib2.Request(url, None, {"Authorization": auth })
    url_handle = urllib2.urlopen(req)

    print "deployed api"

    # override data-sources.xml and application-context.xml
    dspath_from = os.path.join(deployer_resources_dir, 'data-sources.xml')
    dspath_to = os.path.join(tomcat_home, 'webapps/opentripplanner-api-webapp/WEB-INF/classes/data-sources.xml')
    subprocess.call(['cp', dspath_from, dspath_to])
    
    acpath_from = os.path.join(deployer_resources_dir, 'application-context.xml')
    acpath_to = os.path.join(tomcat_home, 'webapps/opentripplanner-api-webapp/WEB-INF/classes/org/opentripplanner/api/application-context.xml')
    subprocess.call(['cp', acpath_from, acpath_to])

        
    # open security-application-context.xml template
    sactemplate = open(os.path.join(deployer_resources_dir, 'security-application-context.xml'), 'r')
    sacxml = sactemplate.read()
    sactemplate.close()

    # generate password and insert into file
    chars = string.letters + string.digits
    password = ''.join([choice(chars) for i in range(8)])
    sacxml = sacxml.format(password=password)

    # overwrite deployed security-application-context.xml
    sacfilepath = os.path.join(tomcat_home, 'webapps/opentripplanner-api-webapp/WEB-INF/classes/org/opentripplanner/api/security-application-context.xml')
    sacfile = open(sacfilepath, 'w')
    sacfile.write(sacxml)
    sacfile.close()
    
    # restart tomcat
    subprocess.call(['/etc/init.d/tomcat6', 'restart'])

    # init multideployer_ready message params
    instance_id = 'n/a'
    ec2_conn = connect_ec2(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    host_ip = socket.gethostname()[3:].replace('-','.')
    reservations = ec2_conn.get_all_instances()
    for reservation in reservations:
        for instance in reservation.instances:
            private_ip = instance.private_ip_address
            if private_ip == host_ip:
                instance_id = instance.id
                found_instance = True

    pomfile = open(os.path.join(tomcat_home, 'webapps/opentripplanner-api-webapp/META-INF/maven/org.opentripplanner/opentripplanner-api-webapp/pom.properties'), 'r')
    version = 'n/a'
    for line in pomfile:
        if line[:8] == 'version=':
            version = line[8:].rstrip()
            break

    print host_ip
    print instance_id
    print version

    # publish multideployer_ready message
    publisher = conn.Producer(routing_key="multideployer_ready", exchange=exchange)
    publisher.publish({'request_id' : body['request_id'], 'host_ip' : host_ip, 'instance_id' : instance_id, 'otp_version' : version, 'auth_password' : password})
    
    # create init file    
    subprocess.call(['touch', initfile])

    # acknowledge original message and exit
    message.ack()
    sys.exit(0)
                            
            
# on initial boot (only), listen for launch message
if(not os.path.exists(initfile)):

    with DjangoBrokerConnection() as conn:
        with conn.Consumer(queue, callbacks=[lambda body, message: handle(conn, body, message)]) as consumer:
            # Process messages and handle events on all channels
            while True:
                conn.drain_events(timeout=600)

    # shutdown the instance (if connection timed out)
    stop_current_instance()

else: # instance is being rebooted; just start tomcat

    subprocess.call(['/etc/init.d/tomcat6', 'start'])

