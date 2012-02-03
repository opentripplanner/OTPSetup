from boto import connect_s3
from boto.s3.key import Key

import keys

connection = connect_s3(keys.access_key, keys.secret_key)
bucket = connection.get_bucket('otpsetup-resources')

key = Key(bucket)
key.key = 'settings-template.py'

local_file = 'settings-template.py'
key.get_contents_to_filename(local_file)

templatefile = open(local_file, 'r')
settings_content = templatefile.read()
templatefile.close()

settings_content = settings_content.format(awsaccesskey=keys.access_key, awssecretkey=keys.secret_key)

settings_file = open('/var/otp/OTPSetup/otpsetup/settings.py', 'w')
settings_file.write(settings_content)
settings_file.close()

