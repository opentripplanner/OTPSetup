from datetime import datetime
from django.db import models
from django.forms import ModelForm
from django.contrib.auth.models import User

STATES = (("running", "Running"),
          ("building", "Request not yet submitted"),
          ("pre_transload", "Getting GTFS"),
          ("submitted", "Waiting for approval"),
          ("rejected", "Rejected"),
          ("accepted", "Accepted, graph building"),
          )
class InstanceRequest(models.Model):
    state = models.CharField(max_length=15, default='building', choices = STATES)
    submit_date = models.DateTimeField('date submitted', default=datetime.now)
    decision_date = models.DateTimeField('date decided', null=True)

    user = models.ForeignKey(User)
    agency = models.CharField(max_length=40, blank=True)
    comments = models.TextField(max_length=20000, null=True, blank=True)
    ip = models.CharField(max_length=15)

class GtfsFile(models.Model):
    instance_request = models.ForeignKey(InstanceRequest)
    s3_key = models.CharField(max_length=200, null=True, db_index=True)
    transload_url = models.CharField(max_length=200, null=True)
    validation_output = models.TextField(max_length=20000, null=True, blank=True)

class InstanceRequestForm(ModelForm):
    class Meta:
        model = InstanceRequest
        fields = ('comments', 'agency')

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
