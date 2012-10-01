from datetime import datetime
from django.db import models
from django.forms import ModelForm, RegexField
from django.contrib.auth.models import User

from kombu import Exchange
from otpsetup.shortcuts import DjangoBrokerConnection


class DeploymentGroup(models.Model):
    name = models.CharField(max_length=20)
    description = models.TextField(max_length=1000, null=True, blank=True)

    def __str__(self):
        return self.name


class DeploymentHost(models.Model):
    name = models.CharField(max_length=50, blank=True)
    instance_id = models.CharField(max_length=20)
    host_ip = models.CharField(max_length=20)
    otp_version = models.CharField(max_length=20)
    auth_password = models.CharField(max_length=20)
    total_memory = models.BigIntegerField()
    free_memory = models.BigIntegerField()
    group = models.ForeignKey(DeploymentGroup, null=True, blank=True)

    def __str__(self):
        return "(%s) %s" % (self.id, self.name)


STATES = (("running", "Running"),
          ("building", "Request not yet submitted"),
          ("pre_transload", "Getting GTFS"),
          ("submitted", "Sent to validator"),
          ("validate_done", "Validation complete, waiting for approval"),
          ("rejected", "Rejected by administrator"),
          ("accepted", "Accepted, graph building"),
          ("graph_built", "Graph built successfully"),
          ("graph_failed", "Graph builder failed"),
          ("deploy_inst", "Deployed instance successfully"),          
          ("deploy_failed", "Deployment failed"),          
          ("deploy_proxy", "Deployment registered with proxy server"),          
          )

class InstanceRequest(models.Model):
    state = models.CharField(max_length=15, default='building', choices = STATES)
    submit_date = models.DateTimeField('date submitted', default=datetime.now)
    decision_date = models.DateTimeField('date decided', null=True)

    user = models.ForeignKey(User)
    agency = models.CharField(max_length=40, blank=True)
    comments = models.TextField(max_length=20000, null=True, blank=True)
    fare_factory = models.CharField(max_length=200)
    deployment_hostname = models.CharField(max_length=30, null=True, blank=True)
    admin_password = models.CharField(max_length=15, null=True, blank=True)
    public_url = models.CharField(max_length=60, null=True, blank=True)
    graph_key = models.CharField(max_length=60, null=True, blank=True)
    data_key = models.CharField(max_length=60, null=True, blank=True)
    graph_url = models.CharField(max_length=150, null=True, blank=True)
    ip = models.CharField(max_length=15)
    deployment_host = models.ForeignKey(DeploymentHost, null=True, blank=True)
    otp_version = models.CharField(max_length=20, null=True, blank=True)

    __original_dephost = None

    def __init__(self, *args, **kwargs):
        super(InstanceRequest, self).__init__(*args, **kwargs)
        self.__original_dephost = self.deployment_host

    def save(self, force_insert=False, force_update=False):
        if self.deployment_host != self.__original_dephost and self.deployment_host is not None:
            # dephost changed - publish deployer message
            exchange = Exchange("amq.direct", type="direct", durable=True)
            conn = DjangoBrokerConnection()
            publisher = conn.Producer(routing_key="deploy_graph_multi", exchange=exchange)
            publisher.publish({"request_id" : self.id, "instance_id" : self.deployment_host.instance_id, "graph_key" : self.graph_key})


        super(InstanceRequest, self).save(force_insert, force_update)
        self.__original_dephost = self.deployment_host


class InstanceRequestForm(ModelForm):
    fare_factory = RegexField(label="Fare model", max_length=200, 
                             regex=r'^[\w.]+')

    class Meta:
        model = InstanceRequest
        fields = ('comments', 'agency', 'fare_factory')

# currently used for user-uploaded gtfs files only
class GtfsFile(models.Model):
    instance_request = models.ForeignKey(InstanceRequest)
    s3_key = models.CharField(max_length=200, null=True, db_index=True)
    transload_url = models.CharField(max_length=200, null=True)
    validation_output = models.TextField(max_length=20000, null=True, blank=True)
    extra_properties = models.TextField(max_length=2000, null=True, blank=True)

    def validation_output_str(self):
        if(self.validation_output == None):
            return "(None)"
        return "<textarea rows=8 cols=85>%s</textarea>" % self.validation_output
    validation_output_str.allow_tags = True
    
    
class ManagedDeployment(models.Model):
    source = models.CharField(max_length=15)
    description = models.CharField(max_length=200, null=True, blank=True)
    group = models.ForeignKey(DeploymentGroup, null=True, blank=True)
    last_osm_key = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return "[%s] %s (%s)" % (self.id, self.source, self.description)

class GraphBuild(models.Model):
    deployment = models.ForeignKey(ManagedDeployment)
    creation_date = models.DateTimeField(default=datetime.now)
    completion_date = models.DateTimeField(null=True)
    config = models.TextField(max_length=10000, null=True, blank=True)
    osm_key = models.CharField(max_length=200, null=True, blank=True)
    graph_key = models.CharField(max_length=200, null=True, blank=True)
    graph_size = models.BigIntegerField(null=True)
    output_key = models.CharField(max_length=200, null=True, blank=True)
    success = models.BooleanField(default=False)
    otp_version = models.CharField(max_length=20, null=True, blank=True)

    def gtfs_count(self):
        return len(self.gtfsbuildmapping_set.all())

    def host_count(self):
        return len(self.buildhostmapping_set.all())

    def link(self):
        return "<a href='/admin/client/graphbuild/%s'>[<b>%s</b>]</a>" % (self.id, self.id)
    link.allow_tags = True

    def __str__(self):
        return "Build #%s / Deployment %s" % (self.id, self.deployment)


class ManagedGtfsFeed(models.Model):
    s3_key = models.CharField(max_length=200, db_index=True)
    default_agency_id = models.CharField(max_length=100, null=True, blank=True)
    default_bikes_allowed = models.CharField(max_length=20, null=True, blank=True)
    expire_on = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        if self.default_agency_id is not None:
            return "%s (%s)" % (self.s3_key, self.default_agency_id)
        return self.s3_key    
 
class GtfsBuildMapping(models.Model):
    gtfs_feed = models.ForeignKey(ManagedGtfsFeed)
    graph_build = models.ForeignKey(GraphBuild)

class BuildHostMapping(models.Model):
    graph_build = models.ForeignKey(GraphBuild)
    deployment_host = models.ForeignKey(DeploymentHost)
    

# not currently used:

MACHINE_TYPES=[('graph builder', 'Graph Builder', ), ('webapp', 'Webapp')]

class AmazonMachineImage(models.Model):
    ami_id = models.CharField(max_length=200)
    machine_type = models.CharField(max_length=20, choices=MACHINE_TYPES)
    version = models.CharField(max_length=20)
    default_for_new_instances = models.BooleanField(max_length=20, default=True)
    def save(self, force_insert=False, force_update=False):
        if self.default_for_new_instances:
            AmazonMachineImage.objects.filter(~Q(id = self.id) & Q(machine_type = self.machine_type)).update(default_for_new_instances=False)
        super(Test, self).save(force_insert, force_update)

