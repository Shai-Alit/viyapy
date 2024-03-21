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

with open('C:/certs/viya4_token.cred', 'rb') as filekey:
    token = filekey.read().decode('ascii')

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
        output_dict = unpack_viya_outputs(response)
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