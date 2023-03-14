# TP-Link Archer AX6000 API client

An example implementation of the auth. mechanism and e2e encrypted comms. via the LuCI HTTP API on official TP-Link firmware.

### Compatible (tested) versions
* **Firmware:** 1.3.0 Build 20221208 rel.45145(5553)
* **Hardware:** Archer AX6000 v1.0
* **Firmware:** 1.1.1 Build 20200918 rel.67850(4555)
* **Hardware:** Archer C2300 v2.0

### Example usage
```
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
```

### Example auth responses

* On wrong password

`{'errorcode': 'login failed', 'success': False, 'data': {'failureCount': 1, 'errorcode': '-5002', 'attemptsAllowed': 9}}`

* On exceeded max auth attempts (usually 10)

`{'errorcode': 'exceeded max attempts', 'success': False, 'data': {'failureCount': 10, 'attemptsAllowed': 0}}`

* If some other user is logged in

`{'errorcode': 'user conflict', 'success': False, 'data': {}}`

* On successful auth

`{'success': True, 'data': {'stok': '94640fd8887fb5750d6a426345581b87'}}`

___

Licensed under GNU GPL v3
