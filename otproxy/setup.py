from setuptools import setup, find_packages

setup(
    name='otproxy',
    version="0.1",
    install_requires=[
      "cube-client", "gevent", "httplib2", "wsgiref"
      ],
)
