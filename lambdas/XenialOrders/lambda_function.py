import json
import base64
import datetime
import boto3
import os
from botocore.exceptions import ClientError
import snowflake.connector as sf

def lambda_handler(event, context):
    # snowflake = boto3.resource('snowflake')
    # table = snowflake.Table('XenialOrders')
    
    secret_name = "CKESnowflakeXenialCreds"
    region_name = os.environ['AWS_REGION']
    env = os.environ['ENV']
    

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )


    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e
        
    secret = get_secret_value_response['SecretString']
    secretDict_json = json.loads(secret)
    secretDict = secretDict_json[env]
    
    #Initiation of Snowflake connection
    conn = sf.connect(
    user=secretDict["snowflakeUsername"], 
    password=secretDict["snowflakePassword"], 
    account=secretDict["snowflakeAccount"] ,
    role=secretDict["snowflakeRole"] ,
    warehouse=secretDict["snowflakeWarehouse"], 
    database=secretDict["snowflakeDatabase"],
    schema=secretDict["snowflakeSchema"]
    )

    
    # let's log the incoming event
    payload_as_string = json.dumps(event)
    print(payload_as_string)
    try:
        batch = []
        put_request_batches = []
        
        # event contains Records, which is an array with a certain structure
        for i in range(len(event["Records"])):
            # let's get the Record
            record = event["Records"][i]
            # let's decode the base64-encoded payload that was sent
            data = base64.b64decode(record["kinesis"]["data"]).decode('utf-8')
            # parse the data as a JSON string
            data_json = json.loads(data)
            # access the entityName and data fields
            entity_name = data_json["entityName"]
            entity_data = data_json["data"]
            # let's show the data
            print(f"Entity Name: {entity_name}")
            print(f"Data: {entity_data}")
            # let's show the timestamp in which it was received (approximately)
            received_tst = datetime.datetime.fromtimestamp(record["kinesis"]["approximateArrivalTimestamp"])
            print(f"Received tst: {received_tst}")
            #-----
            # The following part of the code deals with the Snowflake batches
            #-----
            # 
            data_for_snowflake = {
                "Data": data
            }
            # assign the value of "_id" element to data_for_snowflake["OrderID"]
            # data_for_snowflake["OrderID"] = entity_data["_id"]
            # put data into the current batch
            # batch.append(
            #     {
            #         "PutRequest": {"Item": data_for_snowflake}
            #     }
            # )
            batch.append(data_for_snowflake)
            # Batches are limited to 25 items; so, we "close" a batch when we reach 25 items.
            if len(batch) == 100 or i == len(event["Records"]) - 1:
                put_request_batches.append(batch)
                batch = []
               
        # print(table)
        # Here we have in putRequestBatches an array of batches
        for i in range(len(put_request_batches)):
            # params = {
            #     "RequestItems": {
            #         "XenialOrders": put_request_batches[i]
            #     }
            # }
            user=secretDict["snowflakeUsername"]
            current_time = datetime.datetime.now()
            params = {"XenialOrders": put_request_batches[i]}
            cur = conn.cursor()
            insert_query = f"INSERT INTO STAGE.RAW_XENIAL_ORDERS(source_json,created_date,created_by)  select parse_json($1),$2,$3 from values(%s,%s,%s)"
            data = [[json.dumps(params),current_time,user]]

            cur.executemany(insert_query,data)
            cur.close()
            conn.commit()
            print(f"Writing to snowflake: {json.dumps(params)}")
            # response = table.batch_write_item(RequestItems={
            #     'XenialOrders': put_request_batch
            # })
            # response = table.batch_write_item(RequestItems=params)
            # print(response)
    except Exception as e:
        # let's handle the errors, if any
        print("Error:", e)
        raise e
        # response = {
        #     "statusCode": 400,
        #     "body": str(e)
        # }
        return response
    response = {
        "statusCode": 200
    }
    return response
