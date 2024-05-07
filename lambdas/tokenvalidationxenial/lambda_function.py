import json
from helpers import main

def lambda_handler(event, context):
    # TODO implement
    #print("test, event", event)
    # print("test, context", context)
    
    response = main(event)
    
    if response:
       
        return {
            'statusCode': 200,
            'message': 'Success!'
        }
    
    else:
        return {
            'statusCode': 400,
            'message': 'Invalid Authorization value'
        }
