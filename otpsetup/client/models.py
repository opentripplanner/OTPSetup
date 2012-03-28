from datetime import datetime
from django.db import models
from django.forms import ModelForm, RegexField
from django.contrib.auth.models import User

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
    fare_factory = models.TextField(max_length=200)
    deployment_hostname = models.CharField(max_length=30, null=True, blank=True)
    admin_password = models.CharField(max_length=15, null=True, blank=True)
    public_url = models.CharField(max_length=60, null=True, blank=True)
    graph_builder_output = models.TextField(max_length=20000, null=True, blank=True)    
    ip = models.CharField(max_length=15)

class GtfsFile(models.Model):
    instance_request = models.ForeignKey(InstanceRequest)
    s3_key = models.CharField(max_length=200, null=True, db_index=True)
    transload_url = models.CharField(max_length=200, null=True)
    validation_output = models.TextField(max_length=20000, null=True, blank=True)

class InstanceRequestForm(ModelForm):
    fare_factory = RegexField(label="Fare model", max_length=200, 
                             regex=r'^[\w.]+')

    class Meta:
        model = InstanceRequest
        fields = ('comments', 'agency', 'fare_factory')

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
