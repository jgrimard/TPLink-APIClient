import json
import tplink
import logging

api = tplink.TPLinkClient('192.168.1.1', log_level = logging.ERROR)

# Set logout_others to False if you don't want to kick out a logged in user
api.connect('password', logout_others = True)

result = api.get_led_status()
if result['data']['enable'] == 'on':
    api.set_led_status("toggle")
    
# Print connected clients
print(json.dumps(api.get_client_list(), indent = 4, sort_keys = True))

# Print devices that are available to be blocked
print(json.dumps(api.get_black_devices(), indent = 4, sort_keys = True))

# UnBlock a device by it's MAC address
api.unblock_device('7D-24-92-59-70-E8')

# Block a device by it's MAC address
api.block_device('7D-24-92-59-70-E8')

print("The following devices are blocked:")
print(json.dumps(api.get_black_list(), indent = 4, sort_keys = True))

# Safely logout so others can login
api.logout()
