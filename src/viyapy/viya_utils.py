# -*- coding: utf-8 -*-
"""
Created on Thu Jun  9 11:27:11 2022

@author: seford
"""
import requests
import json

#custom post that provides Viya authentication (OAuth2) with http request
#Note - requires an admin to create a token for user
def post(url1, contentType, accept, accessToken, body):
    sess = requests.Session()
    
    headers = {"Accept": accept,
    "Authorization": "bearer " + accessToken,
    "Content-Type": contentType }
    
    # Convert the request body to a JSON object.
    reqBody = json.loads(body)
    
    # Post the request.
    req = sess.post(url1, json=reqBody, headers=headers)
    
    #clean up
    sess.close()
    
    return req;

#generate inputs in the format ID is expecting from a dictionary
def gen_viya_inputs(feature_dict):
    feature_list = []
    for k,v in feature_dict.items():
        if type(v) == str:
            feature_list.append(f'{{"name": "{k}_", "value" : "{v}"}}')
        else:
            feature_list.append(f'{{"name": "{k}_", "value" : {v}}}')
            
    feature_str = str.join(',',feature_list)
    
    return '{"inputs" : [' + feature_str + ']}'

#call the ID API and get the results as a python dictionary
def call_id_api(baseUrl, accessToken, feature_dict,moduleID):
    #create the request in format viya wants
    requestBody = gen_viya_inputs(feature_dict)

    # Define the content and accept types for the request header.
    contentType = "application/json"
    acceptType = "application/json"
    
    # Define the request URL.
    masModuleUrl = "/microanalyticScore/modules/" + moduleID
    requestUrl = baseUrl + masModuleUrl + "/steps/execute"
    
    # Execute the decision.
    masExecutionResponse = post(requestUrl, contentType,
     acceptType, accessToken, requestBody)
    
    return json.loads(masExecutionResponse.content)

#unpack the ID outputs section as a python dictionary
def unpack_viya_outputs(outputs):
    d = {}
    for elem in outputs:
        d[elem['name']] = '' if 'value' not in elem.keys() else elem['value']
        
    return d
        