from constants import *
import boto3
import json


def kinesis_put_record(json_data):
    stream_name = STREAM_NAME
    partition_key = str(json_data.get('data', {}).get('site_info', {}).get('store_number')) 

    kinesis_client = boto3.client('kinesis')

    response = kinesis_client.put_record(
        StreamName=stream_name,
        Data=json.dumps(json_data),
        PartitionKey=partition_key
    )

    print(f"Response for Put record to Kinesis: {response}")

    print(f"Successfully inserted into kinesis stream - {stream_name}")
    
def main(data):
    key = data.get('headers', {}).get('Authorization')
    
    status = True if key == AUTHORIZATION_KEY else False
    
    if status:
        put_data = data.get('body', {})
        kinesis_put_record(put_data)
        
        
    return status
        
