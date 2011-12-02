from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('',
    url(r'^$', 'otpsetup.client.manage_ec2.index', name='index'),
    url(r'^start_instance$', 'otpsetup.client.manage_ec2.start_instance', name='start_instance'),
    url(r'^stop_instance$', 'otpsetup.client.manage_ec2.stop_instance', name='stop_instance'),


)
