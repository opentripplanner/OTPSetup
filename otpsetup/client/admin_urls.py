from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('',
    url(r'^$', 'otpsetup.client.adminviews.index', name='index'),
    url(r'^approve_request$', 'otpsetup.client.adminviews.approve_request', name='approve_request'),

)
