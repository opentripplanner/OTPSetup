from otpsetup.client.models import ManagedDeployment, DeploymentHost, DeploymentGroup, GraphBuild
import sys, urllib2, json

from kombu import Exchange
from otpsetup.shortcuts import DjangoBrokerConnection


def build_deployment_from_config(config_txt):
    config = json.loads(config_txt)

    if not 'metroId' in config:
        return "no metroId provided"
    
    if 'metro' in config:
        metro_name = config['metro'] 
    else:
        metro_name = "N/A"

    response = 'Metro #%s (%s) ' % (config['metroId'], metro_name)
    
    source = 'metro-%s' % config['metroId']
    osm_key = None
    try:
        man_dep = ManagedDeployment.objects.get(source=source)
        response += " has existing record."
    except ManagedDeployment.DoesNotExist:
        group = DeploymentGroup.objects.get(name="otpna")
        man_dep = ManagedDeployment(source=source, group=group)
        response += " has no record; created."

    man_dep.description = metro_name
    man_dep.save()

    build = GraphBuild(deployment=man_dep, osm_key=man_dep.last_osm_key, config=config_txt)
    build.save()

    exchange = Exchange("amq.direct", type="direct", durable=True)
    conn = DjangoBrokerConnection()

    publisher = conn.Producer(routing_key="process_gtfs", exchange=exchange)
    publisher.publish({'id' : build.id, 'config' : config_txt})
    response += ' Published process_gtfs message.'

    #publisher = conn.Producer(routing_key="build_managed", exchange=exchange)
    #publisher.publish({'id' : build.id, 'osm_key' : build.osm_key, 'config' : request.REQUEST['data']})
    #html = html + 'published build_managed message<br>'

    return response


def deploy_build_to_host(build, host):
    exchange = Exchange("amq.direct", type="direct", durable=True)
    conn = DjangoBrokerConnection()
    publisher = conn.Producer(routing_key="deploy_graph_multi", exchange=exchange)
    publisher.publish({"request_id" : build.id, "instance_id" : host.instance_id, "graph_key" : build.graph_key})


def update_memory(host):
    try:
        response = urllib2.urlopen('http://%s:8080/memcheck/total' % host.host_ip)
        host.total_memory = int(response.read().strip())   
 
        response = urllib2.urlopen('http://%s:8080/memcheck/free' % host.host_ip)
        host.free_memory = int(response.read().strip())        

        host.save()
    except:
        sys.stderr.write("warning: memory utilization for deployment host % could not be accessed" % host.id)


def deploy_once(build):

    group = build.deployment.group

    # check for existing instance
    for host in DeploymentHost.objects.all():
    
        # check that group matches
        if host.group != group:
            continue

        # check that otp version matches
        if host.otp_version != build.otp_version:
            continue
            
        # check that memory is available and that that deployment doesn't already exist on host
        used_graph_space = 0
        already_deployed = False
        for mapping in host.buildhostmapping_set.all():
            used_graph_space += mapping.graph_build.graph_size
            if mapping.graph_build == build:
                already_deployed = True

        if already_deployed is True:
            continue

        if host.total_memory is None:
            update_memory(host)

        total_graph_space = 0.75*host.total_memory
        print "used %s of %s, this graph=%s" % (used_graph_space, total_graph_space, build.graph_size)
        if build.graph_size > total_graph_space - used_graph_space:
            continue

        # if match found, deploy and exit
        print "match!"
        deploy_build_to_host(build, host)  
        return
        
    # create new instance

    print "no suitable host found, creating.."
