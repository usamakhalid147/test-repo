import json
from config import *
from fetchLogger import *
from helpers import *

def lambda_handler(event, context):
    print("event", event)
    
    AUTHORIZATION_KEY = os.environ.get('AUTHORIZATION_KEY')
    key = event.get('headers', {}).get('Authorization')
    status = True if key == AUTHORIZATION_KEY else False
    if not status:
        return {
            'statusCode': 401,
            'body': 'unauthorized'
        }
        
    action = event.get('action','')
    if 'Records' in event:
        event_records = event['Records'][0]
        if 'EventSource' in event_records:
            event_type = event_records['EventSource']
            if str(event_type) == 'aws:sns':
                print("SNS Request detected")
                request_json = json.loads(event_records['Sns']['Message'])
                print(request_json)
                process(request_json)
    elif action == 'get_records':

        print(event)

        req_status = check_http(event)


        return {
            'statusCode': 200,
            'body': json.dumps(req_status)
        }
        
    elif action == 'get_records_count':

        print(event)
        xenial_data_id = str(event['id'])
        results = get_sql_data(xenial_data_id)[0]

        status = results[2]
        
        if status.lower() == 'processing':
            return {
                'statusCode': 200,
                'status': "under processing"
                }
        elif status.lower() == 'complete':
            records_count = results[3]
            return {
                'statusCode': 200,
                'status': "process complete",
                'recordsCount': str(records_count)
                }

        return {
            'statusCode': 200,
            'body': json.dumps(req_status)
        }
    else:
        return {
            'statusCode': '400',
            'body': "Bad Request"
        }
        
def get_sql_data(xenial_data_id):
    print("xenial_data_id",xenial_data_id)
    secretDict = get_secret_dict()
    
    conn = sf.connect(
        user=secretDict["snowflakeUsername"],
        password=secretDict["snowflakePassword"],
        account=secretDict["snowflakeAccount"],
        role=secretDict["snowflakeRole"],
        warehouse=secretDict["snowflakeWarehouse"],
        database=secretDict["snowflakeDatabase"],
        schema=secretDict["snowflakeSchema"]
    )
    logger.info("Successfully connected to Snowflake")
    
    cur = conn.cursor()
    query = "SELECT * FROM STAGE_XENIAL.XENIAL_RESEND_RECORDS_COUNT WHERE XENIALDATAID = %s"
    cur.execute(query, (xenial_data_id,))

    results = cur.fetchall()
    
    return results
            
def process(event):
    logger.info("Starting lambda_handler")

    
    
    secretDict = get_secret_dict()
    
    retDict = insert_into_xenialOrders_table(secretDict, event)
    
    retval = prepare_final_response(retDict['records_count'])
            
    if retDict['status'] != SUCCESS:
        logger.error(f"Error while fetching and processing Kinesis records")
        retval = prepare_final_response(retDict['records_count'], success = False, errMsg=retDict['errorMessage'])
        
    logger.info("Lambda execution complete.")    

    return retval
