from setuptools import setup, find_packages

setup(
    name='OTPSetup',
    version="0.1",
    install_requires=[
      "Django==1.3.1",
#      "django-registration",  need to pull version 0.8 which is not currently available
      "kombu",
      "boto",
      "transitfeed"
      ],
)
