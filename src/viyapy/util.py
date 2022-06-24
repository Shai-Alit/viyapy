# -*- coding: utf-8 -*-
"""
Created on Thu Jun 23 19:38:23 2022

@author: seford
"""

def unpack_outputs(outputs):
    '''unpack the ID outputs section as a python dictionary'''
    
    d = {}
    for elem in outputs:
        d[elem['name']] = '' if 'value' not in elem.keys() else elem['value']
        
    return d