from setuptools import setup, find_packages

setup(
    name='OTPSetup',
    version="0.1",
    install_requires=[
      "Django==2.2.24",
#      "django-registration",  need to pull version 0.8 which is not currently available
      "kombu",
      "boto==2.1.1",
      "transitfeed"
      ],
)
