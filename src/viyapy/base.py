# -*- coding: utf-8 -*-
"""
Created on Thu Jun 23 19:34:46 2022

@author: seford
"""

import requests
import urllib
import json

def post(url1: str, contentType: str, accept: str, accessToken: str, body: str) -> str:
    '''custom post that provides Viya authentication (OAuth2) with http request
    Note - requires an admin to create a token for user'''
    
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

def get(url1: str, accessToken1: str, accept: str) -> str:
    '''This function defines request headers,
    submits the request, and returns both the response body and
    the response header.
    '''
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
