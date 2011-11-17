from datetime import datetime
from django.db import models
from django.forms import ModelForm
from django.contrib.auth.models import User

class InstanceRequest(models.Model):
    state = models.CharField(max_length=15, default='submitted') #building, pre_transload, submitted, accepted, rejected
    submit_date = models.DateTimeField('date submitted', default=datetime.now)
    decision_date = models.DateTimeField('date decided', null=True)

    user = models.ForeignKey(User)
    agency = models.CharField(max_length=40)
    comments = models.CharField(max_length=20000)
    ip = models.CharField(max_length=15)

class GtfsFile(models.Model):
    instance_request = models.ForeignKey(InstanceRequest)
    s3_key = models.CharField(max_length=200, null=True)
    transload_url = models.CharField(max_length=200, null=True)

class InstanceRequestForm(ModelForm):
    class Meta:
        model = InstanceRequest
        fields = ('comments', 'agency')
