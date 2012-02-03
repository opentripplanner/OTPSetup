from boto import connect_s3
from boto.s3.key import Key

import keys

connection = connect_s3(keys.access_key, keys.secret_key)
bucket = connection.get_bucket('otpsetup-resources')

key = Key(bucket)
key.key = 'opentripplanner-api-webapp.war'
local_file = '/var/otp/wars/opentripplanner-api-webapp.war'
key.get_contents_to_filename(local_file)

key = Key(bucket)
key.key = 'opentripplanner-webapp.war'
local_file = '/var/otp/wars/opentripplanner-webapp.war'
key.get_contents_to_filename(local_file)
