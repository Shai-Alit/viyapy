# -*- coding: utf-8 -*-
"""
Created on Fri Aug 19 09:29:36 2022

@author: seford
"""

#call_id_api_test
import os
import sys
import keyring

# getting the name of the director where the this file is present.
current = os.path.realpath(os.getcwd())

# Getting the parent directory name where the current directory is present.
parent = os.path.dirname(current)

# adding the parent directory to the sys.path.
if parent not in sys.path:
    sys.path.append(parent)

from src.viyapy.viya_utils import call_id_api, unpack_viya_outputs

token='eyJhbGciOiJSUzI1NiIsImprdSI6Imh0dHBzOi8vbG9jYWxob3N0L1NBU0xvZ29uL3Rva2VuX2tleXMiLCJraWQiOiJsZWdhY3ktdG9rZW4ta2V5IiwidHlwIjoiSldUIn0.eyJqdGkiOiJkZmFkYjMxOGE3MGQ0YmRjOWRmZjVjNzFmYzAzYjc5YyIsImV4dF9pZCI6InVpZD1zZWZvcmQsb3U9cGVvcGxlLGRjPWV4YW1wbGUsZGM9Y29tIiwicmVtb3RlX2lwIjoiMTQ5LjE3My44LjExMyIsInNlc3Npb25fc2lnIjoiMGUzMjlmNWMtYmYzZi00ZDMxLTlmNDctOTA3ZDBmM2M2MGJjIiwic3ViIjoiYTliMTM5MzYtZWZkZS00OWU4LWE4M2MtN2ZlMzI2MmU3OWRlIiwic2NvcGUiOlsib3BlbmlkIl0sImNsaWVudF9pZCI6ImJ1ZHNwcm9kY2xpZW50aWQiLCJjaWQiOiJidWRzcHJvZGNsaWVudGlkIiwiYXpwIjoiYnVkc3Byb2RjbGllbnRpZCIsImdyYW50X3R5cGUiOiJhdXRob3JpemF0aW9uX2NvZGUiLCJ1c2VyX2lkIjoiYTliMTM5MzYtZWZkZS00OWU4LWE4M2MtN2ZlMzI2MmU3OWRlIiwib3JpZ2luIjoibGRhcCIsInVzZXJfbmFtZSI6InNlZm9yZCIsImVtYWlsIjoiU2Vhbi5Gb3JkQHNhcy5jb20iLCJhdXRoX3RpbWUiOjE2NzU3ODQwNTYsInJldl9zaWciOiJlM2YzYmQ4MiIsImlhdCI6MTY3NTc4NDA1NiwiZXhwIjoyMTQ4ODI0MDU2LCJpc3MiOiJodHRwOi8vbG9jYWxob3N0L1NBU0xvZ29uL29hdXRoL3Rva2VuIiwiemlkIjoidWFhIiwiYXVkIjpbIm9wZW5pZCIsImJ1ZHNwcm9kY2xpZW50aWQiXX0.cuZDLcioah7YNjIyff9JG6KX0IEXHOIcqlIBX3CdZYtdFQfzrqF7Et_INt46uRwEOwb57WrlfFoGSP0cImzKm8gV0BSKdnwqbbmkZF4OjEey8n8hy9dYOJQLXoavZWrwXUiqD3_o1F9C99lS2ixkleg_zW9ZGHmYTCAKuh1GUV9wE8HaBuKRIU299_rqui3gB8Pl5xQWm_i1VAAJaU7XwQl2gA0B_U1G2sC8YiiA9WduGkAf4zp36n00t2cf_f8CdPVyu1PeHUj_4i1JNED1wiN89vr8wowC5Zq9YprPO5sbIYpeAZlAOyAnxir_kcde-sAWMUKseYr6B_9eoFKX3g'


username='seford'

#authentication token (get from Paige)


host='budsprod.viyamtes.com'

protocol='https'

#base URL for Viya
baseUrl = protocol + '://' + host + '/'

moduleID = 'api_tester1_0'

features = {'input_string': "this is a test"}
 
test_passes = True
test_details = []
try:
    response = call_id_api(baseUrl, token, features, moduleID)
except:
    test_passes = False
    test_details.append('call_id_api failed')

if test_passes:
    try:
        output_dict = unpack_viya_outputs(response['outputs'])
    except:
        test_passes = False
        test_details.append('unpack_viya_outputs failed')

if test_passes:
    if 'input_string' not in output_dict.keys():
        test_passes = False
        test_details.append('input string is not in the Viya return call')
    else:
        if output_dict['input_string'] != features['input_string']:
            test_passes = False
            test_details.append('input string is incorrect')
            
if test_passes:
    if 'output_string' not in output_dict.keys():
        test_passes = False
        test_details.append('output string is not in the Viya return call')
    else:
        if output_dict['output_string'] != "successfully ran decision flow":
            test_passes = False
            test_details.append('output_string is incorrect')
    
if test_passes:
    print('tests PASSED')
else:
    print('test FAILED')
    print(test_details)