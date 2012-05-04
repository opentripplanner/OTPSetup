from boto import connect_s3
from boto.s3.key import Key

import keys
import subprocess

connection = connect_s3(keys.access_key, keys.secret_key)
bucket = connection.get_bucket('otpsetup-resources')

key = Key(bucket)
key.key = 'graph-builder.jar'

local_file = '/var/otp/resources/otpgb/graph-builder.jar'
key.get_contents_to_filename(local_file)


