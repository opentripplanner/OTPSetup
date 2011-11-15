from django.dispatch import receiver
from django.contrib.auth import login
from registration.signals import user_registered

@receiver(user_registered)
def registered(sender, request=None, user=None, **kwargs):
    user.backend='django.contrib.auth.backends.ModelBackend'
    login(request, user)
