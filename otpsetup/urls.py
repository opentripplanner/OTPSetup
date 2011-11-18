from django.conf.urls.defaults import patterns, include, url

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    url(r'^accounts/', include('registration.backends.default.urls')),

    url(r'^$', 'otpsetup.client.views.index', name='index'),
    url(r'^create_request$', 'otpsetup.client.views.create_request', name='create_request'),
    url(r'^upload$', 'otpsetup.client.views.upload', name='upload'),
    url(r'^transload$', 'otpsetup.client.views.transload', name='transload'),
    url(r'^done_upload$', 'otpsetup.client.views.done_upload', name='done_upload'),
    url(r'^done_transload$', 'otpsetup.client.views.done_transload', name='done_transload'),
    url(r'^finalize_request$', 'otpsetup.client.views.finalize_request', name='finalize_request'),
    url(r'^admin/', include('otpsetup.client.admin_urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
)
