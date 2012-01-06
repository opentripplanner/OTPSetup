
from boto import connect_s3, connect_ec2
from boto.s3.key import Key
from datetime import datetime
from django.conf import settings
from django.contrib import admin
from kombu import Exchange
from models import InstanceRequest, AmazonMachineImage, GtfsFile


from otpsetup.client.lib.buttonable_model_admin import ButtonableModelAdmin
from otpsetup.client.models import InstanceRequest, GtfsFile
from otpsetup.shortcuts import render_to_response
from otpsetup.shortcuts import DjangoBrokerConnection
from otpsetup.shortcuts import check_for_running_instance

def accept_instance_request(modeladmin, request, queryset):
    exchange = Exchange("amq.direct", type="direct", durable=True)
    conn = DjangoBrokerConnection()

    publisher = conn.Producer(routing_key="create_instance",
                              exchange=exchange)

    for irequest in queryset:
        if irequest.state != 'approved':
            files = [gtfsfile.s3_key for gtfsfile in irequest.gtfsfile_set.all()]
            publisher.publish({"files": files, "request_id" : irequest.id})

    if hasattr(queryset, 'update'):
        queryset.update(state='accepted', decision_date=datetime.now())
    else:
        for irequest in queryset:
            irequest.state = "accepted"
            irequest.decision_date = datetime.now()
            irequest.save()

    #launch a graph builder EC2 instance
    check_for_running_instance(settings.GRAPH_BUILDER_AMI_ID)

accept_instance_request.short_description = "Send an instance request to the graph builder"

def reject_instance_request(modeladmin, request, queryset):

    connection = connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_KEY)
    bucket = connection.get_bucket(settings.S3_BUCKET)

    for irequest in queryset:
        if irequest.state != 'rejected':
            for gtfs in irequest.gtfsfile_set.all():
                key = Key(bucket)
                key.key = gtfs.s3_key
                key.delete()

    if hasattr(queryset, 'update'):
        queryset.update(state='rejected', decision_date=datetime.now())
    else:
        for irequest in queryset:
            irequest.state = "rejected"
            irequest.decision_date = datetime.now()
            irequest.save()


reject_instance_request.short_description = "Reject an instance request"



class GtfsFileInline(admin.TabularInline):
    model = GtfsFile
    readonly_fields = ('transload_url', 'validation_output')

class InstanceRequestAdmin(ButtonableModelAdmin):
    list_display = ('user', 'agency', 'submit_date', 'state')
    list_filter = ('state', 'submit_date')
    actions = [accept_instance_request, reject_instance_request]
    readonly_fields = ('state', 'submit_date', 'decision_date', 'ip')

    inlines = [
        GtfsFileInline,
    ]

    def approve_or_reject_buttons(self, request=None, object_id=None):
        if request is None:
            return [self.approve, self.reject]
        irequest = InstanceRequest.objects.get(id=object_id)
        if irequest.state == "submitted":
            return [self.approve, self.reject]
        if irequest.state == "rejected":
            #you can actually approve a rejected request, and it will go through (I hope)
            return [self.approve]
        elif irequest.state != "running":
            #you can preemptively reject something, too
            return [self.reject]

    buttons = approve_or_reject_buttons

    def approve(self, irequest):
        accept_instance_request(None, None, [irequest])
    approve.short_description = "Approve"

    def reject(self, irequest):
        reject_instance_request(None, None, [irequest])
    reject.short_description = "Reject"

admin.site.register(InstanceRequest, InstanceRequestAdmin)

class AmazonMachineImageAdmin(admin.ModelAdmin):
    list_display = ('machine_type', 'version', 'ami_id', 'default_for_new_instances')

admin.site.register(AmazonMachineImage, AmazonMachineImageAdmin)
