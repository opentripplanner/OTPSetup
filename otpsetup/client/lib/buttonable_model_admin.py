#by mamat and tsaylor on djangosnippets.org

import re

from django.conf.urls.defaults import patterns, url
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.functional import update_wrapper

class Button(object):
   def __init__(self, func):
      self.func_name = func.func_name
      self.short_description = func.short_description
      self.func = func
      self.alters_data = False

   #I have no clue why this is necessary.  Thanks, Django!
   def __getattr__(self, attr):
      val = self.__dict__[attr]
      return val

class ButtonableModelAdmin(admin.ModelAdmin):
   """
   A subclass of this admin will let you add buttons (like history) in the
   change view of an entry.

   ex.
   class FooAdmin(ButtonableModelAdmin):
      ...

      def bar(self, obj):
         obj.bar()
      bar.short_description='Example button'

      buttons = [ bar ]

   """
   buttons=[]

   def change_view(self, request, object_id, extra_context={}):

      if '/' in object_id:
         object_id = object_id[:object_id.find('/')]
      
      buttons = self.buttons
      if callable(buttons):
         buttons = buttons(request, object_id)

      buttons = map(Button, buttons)
      extra_context['buttons'] = buttons

      return super(ButtonableModelAdmin, self).change_view(request, object_id, extra_context)

   def button_view_dispatcher(self, request, url):
      if url is not None:
         res = re.match('(.*/)?(?P<id>\d+)/(?P<command>.*)', url)
         if res:
            buttons = self.buttons
            if callable(buttons):
               buttons = buttons()
            print res.group('command')
            if res.group('command') in [b.func_name for b in buttons]:
               id = res.group('id')
               obj = self.model._default_manager.get(pk=id)
               getattr(self, res.group('command'))(obj)
               path_without_command = "/".join(request.get_full_path().rstrip("/").split("/")[:-1])
               return HttpResponseRedirect(path_without_command)

      return super(ButtonableModelAdmin, self).__call__(request, url)

   def get_urls(self):
       def wrap(view):
           def wrapper(*args, **kwargs):
               return self.admin_site.admin_view(view)(*args, **kwargs)
           return update_wrapper(wrapper, view)

       urlpatterns = patterns('',
           url(r'^([0-9]+/.+)/$',
               wrap(self.button_view_dispatcher),)
       ) + super(ButtonableModelAdmin, self).get_urls()
       return urlpatterns
