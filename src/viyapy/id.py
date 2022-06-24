# -*- coding: utf-8 -*-
"""
Created on Thu Jun 23 19:34:24 2022

@author: seford
"""

import requests
import json
from base import post, get

    
def get_decision_content(baseUrl: str, decisionId: str, accessToken: str):
    '''Get the content for a decision in Intelligent Decisioning'''
    
    #create the header
    headers = {
        'Accept': 'application/vnd.sas.decision+json',
        "Authorization": "bearer " + accessToken
        }
    
    #set up the URL
    requestUrl = baseUrl + '/decisions/flows/' + decisionId
    
    #make the request
    r = requests.get(requestUrl, headers = headers)
    
    #return the result as a dictionary
    return r.json()

def get_models(baseUrl: str, decisionId: str, accessToken: str):
    '''get all the models in a decision'''
    
    #get the decision content
    response = get_decision_content(baseUrl,decisionId,accessToken)
    
    #grab the flow setps
    flow_steps = response['flow']['steps']
    
    models = []
    
    #loop through steps and capture any that are models
    for s in flow_steps:
        if s['type'] == 'application/vnd.sas.decision.step.model':
            models.append({'Model Name': s['model']['name'],'Modified By':s['modifiedBy'],'Modified Timestamp':s['modifiedTimeStamp']})
            
    return models

def gen_inputs(feature_dict):
    '''generate a json style string with the inputs in the format ID is expecting from a dictionary'''
    
    feature_list = []
    for k,v in feature_dict.items():
        if type(v) == str:
            feature_list.append(f'{{"name": "{k}_", "value" : "{v}"}}')
        else:
            feature_list.append(f'{{"name": "{k}_", "value" : {v}}}')
            
    feature_str = str.join(',',feature_list)
    
    return '{"inputs" : [' + feature_str + ']}'

def execute_decision(baseUrl, accessToken, feature_dict,moduleID):
    '''call the ID API and get the results as a python dictionary'''
    
    #create the request in format viya wants
    requestBody = gen_inputs(feature_dict)

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