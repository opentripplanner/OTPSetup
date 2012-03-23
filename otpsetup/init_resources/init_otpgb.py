from boto import connect_s3
from boto.s3.key import Key

import keys
import subprocess

connection = connect_s3(keys.access_key, keys.secret_key)
bucket = connection.get_bucket('otpsetup-resources')

key = Key(bucket)
key.key = 'otpgb.zip'

local_file = '/var/otp/resources/otpgb.zip'
key.get_contents_to_filename(local_file)

subprocess.call(['unzip', '-o', '/var/otp/resources/otpgb.zip', '-d', '/var/otp/resources/otpgb'])

