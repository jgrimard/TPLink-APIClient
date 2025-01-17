'''
TP-Link Archer C2300 API client v1.1.0

Compatible (tested) with versions:
  Firmware: 1.1.1 Build 20200918 rel.67850(4555)
  Hardware: Archer C2300 v2.0

Copyright (c) 2021 Michal Chvila <dev@electry.sk>.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
'''
import requests
import json
import binascii
import time
import random
import logging
from Crypto.Cipher import AES
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad
from Crypto.Hash import MD5
from base64 import b64encode, b64decode

import urllib

class LoginException(Exception):
    pass

class UserConflictException(LoginException):
    pass

class TPLinkClient:
    HEADERS = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
    }

    def __init__(self, host, log_level = logging.INFO):
        logging.basicConfig()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        self.req = requests.Session()

        self.host = host
        self.token = None

        self.rsa_key_pw = None
        self.rsa_key_auth = None

        self.md5_hash_pw = None

    def get_url(self, endpoint, form):
        stok = self.token if self.token is not None else ''
        return 'http://{}/cgi-bin/luci/;stok={}/{}?form={}'.format(self.host, stok, endpoint, form)

    def connect(self, password, logout_others = False):
        # hash the password
        self.md5_hash_pw = self.__hash_pw('admin', password)

        # request public RSA keys from the router
        self.rsa_key_pw = self.__req_rsa_key_password()
        self.rsa_key_auth = self.__req_rsa_key_auth()

        # generate AES key
        self.aes_key = self.__gen_aes_key()

        # encrypt the password
        encrypted_pw = self.__encrypt_pw(password)

        # authenticate
        try:
            self.token = self.__req_login(encrypted_pw)
        except UserConflictException as e:
            if logout_others:
                self.token = self.__req_login(encrypted_pw, True)
            else:
                raise e

    def logout(self):
        if self.token is None:
            return False

        success = self.__req_logout()
        self.token = None

        return success

    def get_client_list(self):
        url = self.get_url('admin/status', 'client_status')
        data = {
            'operation': 'read'
        }

        return self.__request(url, data, encrypt = True)
    
## CUSTOM FUNCTIONS ## JASON GRIMARD 3/13/2023
    
    # This function returns the status of the router LEDs
    def get_led_status(self):
        url = self.get_url('admin/ledgeneral', 'setting')
        data = {
            'operation': 'read'
        }

        return self.__request(url, data, encrypt = True)
    
    # This function toggles the status of the router LEDs
    def set_led_status(self, status):
        url = self.get_url('admin/ledgeneral', 'setting')
        data = {
            'operation': 'write',
            'led_status': status
        }

        return self.__request(url, data, encrypt = True)
    
    # This function lists the devices that are available to block
    def get_black_devices(self):
        url = self.get_url('admin/access_control', 'black_devices')
        data = {
            'operation': 'load'
        }

        return self.__request(url, data, encrypt = True)
    
    # This function lists the devices that are currently blocked
    def get_black_list(self):
        url = self.get_url('admin/access_control', 'black_list')
        data = {
            'operation': 'load'
        }

        return self.__request(url, data, encrypt = True)
    

    # This function blocks a device by MAC address
    def block_device(self, mac):
        url = self.get_url('admin/access_control', 'black_devices')
        device_data = {
                "mac":mac,
                "host":"NOT HOST"
        }
        # data needs to be url encoded and wrapped in brackets
        encoded_device_data = urllib.parse.quote_plus(f"[{json.dumps(device_data)}]")
        data = {
            'operation': 'block',
            'key': 'key=1', # not sure if a key is really needed
            'index': 0,
            'data': encoded_device_data
        }

        return self.__request(url, data, encrypt = True)

    # This function unblocks a device by MAC address
    def unblock_device(self, mac):
        url = self.get_url('admin/access_control', 'black_list')
        blocked_devices = self.get_black_list()
        index = 0
        device_found = False
        key = 'anything'
        # loop through the blocked devices to get the index
        for device in blocked_devices['data']:
            if device['mac'] == mac:
                device_found = True
                key = device.get('key', 'anything') # not sure if a key is really needed
                break
            index += 1
        if not device_found:
            return "Device not found in black list"
        data = {
            'key': key,
            'index': str(index),
            'operation': 'remove'
        }

        return self.__request(url, data, encrypt = True)
        

## END CUSTOM FUNCTIONS ##

    def __request(self, url, data, encrypt = False, is_login = False):
        if encrypt:
            data_str = self.__format_body_to_encrypt(data)

            # pad to a multiple of 16 with pkcs7
            data_padded = pad(data_str.encode('utf8'), 16, 'pkcs7')

            # encrypt the body
            aes_encryptor = self.__gen_aes_cipher(self.aes_key)
            encrypted_data_bytes = aes_encryptor.encrypt(data_padded)

            # encode encrypted binary data to base64
            encrypted_data = b64encode(encrypted_data_bytes).decode('utf8')

            # get encrypted signature
            signature = self.__get_signature(len(encrypted_data), is_login)

            # order matters here! signature needs to go first (or we get empty 403 response)
            form_data = {
                'sign': signature,
                'data': encrypted_data
            }
        else:
            form_data = data

        r = self.req.post(url, data = form_data, headers = self.HEADERS)

        self.logger.debug('<Request  {}>'.format(r.url))
        self.logger.debug(r)
        self.logger.debug(r.text)

        assert r.text != ''

        if encrypt:
            # Try to parse the json response
            try:
                raw_response_json = json.loads(r.text)
                assert 'data' in raw_response_json # base64

                # decode base64 string
                encrypted_response_data = b64decode(raw_response_json['data'])

                # decrypt the response using our AES key
                aes_decryptor = self.__gen_aes_cipher(self.aes_key)
                response = aes_decryptor.decrypt(encrypted_response_data)

                # unpad using pkcs7
                j = unpad(response, 16, 'pkcs7').decode('utf8')

                return json.loads(j)
            # Added 3/13/2023 JG
            # If we fail to parse the json response, try parsing as a string response
            except json.decoder.JSONDecodeError:
                # decode base64 string
                encrypted_response_data = b64decode(r.text)

                # decrypt the response using our AES key
                aes_decryptor = self.__gen_aes_cipher(self.aes_key)
                response = aes_decryptor.decrypt(encrypted_response_data)

                # unpad using pkcs7
                j = unpad(response, 16, 'pkcs7').decode('utf8')
                return j
        # If not encrypting, just return the json response
        else:
            return json.loads(r.text)

    def __format_body_to_encrypt(self, data):
        # format form data into a string
        data_arr = []
        for attr, value in data.items():
            data_arr.append('{}={}'.format(attr, value))

        return '&'.join(data_arr)

    def __hash_pw(self, arg1, arg2 = None):
        md5 = MD5.new()

        if arg2 is not None:
            md5.update((arg1 + arg2).encode('utf8'))
        else:
            md5.update(arg1)

        result = md5.hexdigest()
        assert len(result) == 32

        return result

    def __encrypt_pw(self, password):
        '''
        pkcs1pad2 - PKCS#1 (type 2, random) pad input string s to n bytes
        '''
        pub_key = self.__make_rsa_pub_key(self.rsa_key_pw)
        rsa = PKCS1_v1_5.new(pub_key)

        binpw = password.encode('utf8')

        encrypted = rsa.encrypt(binpw)
        as_string = binascii.hexlify(encrypted).decode('utf8')

        assert len(as_string) == 256
        assert len(as_string) == (len(hex(pub_key.n)) - 2)

        return as_string

    def __make_rsa_pub_key(self, key):
        n = int('0x' + key[0], 16)
        e = int('0x' + key[1], 16)
        return RSA.construct((n, e))

    def __gen_aes_key(self):
        KEY_LEN = 128 // 8
        IV_LEN = 16

        ts = str(round(time.time() * 1000))

        key = (ts + str(random.randint(100000000, 1000000000-1)))[:KEY_LEN]
        iv = (ts + str(random.randint(100000000, 1000000000-1)))[:IV_LEN]

        assert len(key) == 16
        assert len(iv) == 16

        return (key, iv)

    def __gen_aes_cipher(self, aes_key):
        key, iv = aes_key

        # CBC mode, PKCS7 padding
        return AES.new(key.encode('utf8'), AES.MODE_CBC, iv = iv.encode('utf8'))

    def __get_signature(self, body_data_len, is_login = False):
        '''
        aes_key:       generated pseudo-random AES key (CBC, PKCS7)
        rsa_auth_key:  RSA public key from the TP-Link API endpoint (login?form=auth)
        auth_md5_hash: MD5 hash of the username+password as string
        body_data_len: length of the encrypted body message
        is_login:      set to True for login request
        '''
        rsa_n, rsa_e, rsa_seq = self.rsa_key_auth

        if is_login:
            # on login we also send our AES key, which is subsequently
            # used for E2E encrypted communication
            aes_key, aes_iv = self.aes_key
            aes_key_string = 'k={}&i={}'.format(aes_key, aes_iv)

            sign_data = '{}&h={}&s={}'.format(aes_key_string, self.md5_hash_pw, rsa_seq + body_data_len)
        else:
            sign_data = 'h={}&s={}'.format(self.md5_hash_pw, rsa_seq + body_data_len)

        signature = ''
        pos = 0

        # encrypt the signature using the RSA auth public key
        rsa = PKCS1_v1_5.new(self.__make_rsa_pub_key(self.rsa_key_auth))

        while pos < len(sign_data):
            enc = rsa.encrypt(sign_data[pos : pos+53].encode('utf8'))

            signature += binascii.hexlify(enc).decode('utf8')
            pos = pos + 53

        return signature

    def __req_rsa_key_password(self):
        '''
        Return value:
            (n, e) RSA public key for encrypting the password
        '''
        url = self.get_url('login', 'keys')
        data = {
            'operation': 'read'
        }

        response = self.__request(url, data, encrypt = False)
        assert response['success'] == True

        pw_pub_key = response['data']['password']
        assert len(pw_pub_key[0]) == 256
        assert len(pw_pub_key[1]) == 6

        return (pw_pub_key[0], pw_pub_key[1])

    def __req_rsa_key_auth(self):
        '''
        Return value:
            (n, e, seq) RSA public key for encrypting the signature
        '''
        url = self.get_url('login', 'auth')
        data = {
            'operation': 'read'
        }

        response = self.__request(url, data, encrypt = False)
        assert response['success'] == True

        auth_pub_key = response['data']['key']
        assert len(auth_pub_key[0]) == 128
        assert len(auth_pub_key[1]) == 6

        return (auth_pub_key[0], auth_pub_key[1], response['data']['seq'])

    def __req_login(self, encrypted_pw, force_login = False):
        '''
        Return value (on successful login):
            stok - API auth token
        '''
        url = self.get_url('login', 'login')
        data = {
            'operation': 'login',
            'password': encrypted_pw
        }

        if force_login:
            data['confirm'] = 'true'

        response = self.__request(url, data, encrypt = True, is_login = True)
        self.logger.info(response)

        assert 'success' in response

        if response['success'] is False:
            assert 'errorcode' in response

            if response['errorcode'] == 'login failed':
                attempts_allowed = response['data']['attemptsAllowed']
                attempts_total = response['data']['failureCount'] + attempts_allowed

                raise LoginException('Login failed, wrong password. Remaining attempts: {}/{}'.format(attempts_allowed, attempts_total))
            elif response['errorcode'] == 'exceeded max attempts':
                raise LoginException('Login failed, maximum login attempts exceeded. Please wait for 60-120 minutes.')
            elif response['errorcode'] == 'user conflict':
                raise UserConflictException('Login conflict. Someone else is logged in.')
            else:
                raise LoginException(response)

        assert response['success'] == True

        '''
        Example responses:

        {'errorcode': 'login failed', 'success': False, 'data': {'failureCount': 1, 'errorcode': '-5002', 'attemptsAllowed': 9}}

        {'errorcode': 'exceeded max attempts', 'success': False, 'data': {'failureCount': 10, 'attemptsAllowed': 0}}

        {'errorcode': 'user conflict', 'success': False, 'data': {}}

        {'success': True, 'data': {'stok': '94640fd8887fb5750d6a426345581b87'}}
        '''

        return response['data']['stok']

    def __req_logout(self):
        assert self.token is not None

        url = self.get_url('admin/system', 'logout')
        data = {
            'operation': 'write'
        }

        response = self.__request(url, data, encrypt = True)
        self.logger.info(response)

        assert 'success' in response

        return response['success']
