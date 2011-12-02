import os

from django.core.management.base import BaseCommand
from django.db.models import get_app

class Command(BaseCommand):
    help = '''
Symlinks templates and medias from an app to another::

    ./manage.py overload app_to_reuse target_app

It will:

- create directories from app_to_reuse/templates into target_app/templates,
  and symlink every file into that,
- create directory target_app/_default with symlinks to app_to_reuse/templates/*.

Overload procedure:

- don't touch _default,
- remove the symlink of the template to overload and create the file like target_app/template/app_to_reuse/templates/foo.html,
- eventually extend _default/app_to_reuse/foo.html,
- hack blocks in _default/app_to_reuse/foo.html, without having to copy non-overloaded code from app_to_reuse/templates/foo.html
'''
    
    APP_TEMPLATES_DEFAULT_DIR = '_defaults'

    def handle(self, *args, **options):
        if len(args) != 2:
            print >> self.stderr, "./manage.py overload app_to_reuse target_app"
            return
        self.src_app_path = self.get_app_path(args[0])
        self.dst_app_path = self.get_app_path(args[1])

        to_link = [
            'media',
            'templates',
        ]

        for link in to_link:
            os.path.walk(os.path.join(self.src_app_path, link), \
                self.symlink_files, None)

    def get_app_path(self, name):
        app = get_app(name)
        models_path = app.__file__
        app_path = models_path[0:(len(models_path)-len('models.pyc'))]
        return app_path

    def symlink_files(self, arg, dirname, fnames):
        path = dirname[(len(self.src_app_path)):]
        dst_path = os.path.join(self.dst_app_path, path)
        
        # make sure the destination path exists
        if not os.path.exists(dst_path):
            os.mkdir(dst_path)

        if dirname.split('/')[-1] == 'templates':
            default_templates_path = os.path.join(dst_path, self.APP_TEMPLATES_DEFAULT_DIR)

            # make sure the default templates path exists
            if not os.path.exists(default_templates_path):
                os.mkdir(default_templates_path)

            # symlink everything in it to the default templates path
            for fname in fnames:
                src_file_path = os.path.join(dirname, fname)
                dst_file_path = os.path.join(default_templates_path, fname)
                os.symlink(src_file_path, dst_file_path)

        for fname in fnames:
            src_file_path = os.path.join(dirname, fname)
            dst_file_path = os.path.join(dst_path, fname)

            if not os.path.isdir(src_file_path) \
                and not os.path.exists(dst_file_path):
                os.symlink(src_file_path, dst_file_path)

        return fnames
