# -*- coding: utf-8 -*-
"""
Created on Thu Jun  9 11:27:11 2022

@author: seford
"""
import requests
import urllib
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


# Define the GET function. This function defines request headers,
# submits the request, and returns both the response body and
# the response header.
def get(url1, accessToken1, accept):
    sess = requests.Session()
    
    headers = {"Accept": accept,
    "Authorization": "bearer " + accessToken1}
    try:
        # Submit the request.
        req = urllib.request.Request(url1, headers=headers)
        
        # Open the response, and convert it to a string.
        
        domainsResponse = urllib.request.urlopen(req)
        body = domainsResponse.read()
        
        # Return the response body and the response headers.
        respHeaders = domainsResponse.headers
        
        #clean up
        sess.close()
        
        return body, respHeaders
    except urllib.error.URLError as e:
        if hasattr(e, 'reason'):
            print ('Failed to reach a server.')
            print ('Error: ', e.read())
        elif hasattr(e, 'code'):
            print ('The server could not fulfill the request.')
            print ('Error: ', e.read())
    except urllib.error.HTTPError as e:
        print ('Error: ', e.read())
    

#function to get the decision content for a decision in Intelligent Decisioning
def get_decision_content(baseUrl,decisionId,accessToken):
    
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

#get all the models in a decision
def get_models(baseUrl,decisionId,accessToken):
    
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
        