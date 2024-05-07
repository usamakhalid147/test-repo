from fetchLogger import *
import boto3
from config import *
import json
import snowflake.connector as sf
from datetime import datetime
import pytz  # Import the pytz library
import uuid

def get_secret_dict():
    try:
        logger.info(f"Retrieving secrets for {secret_name} in {region_name}")
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name=region_name)

   
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        logger.info("Successfully retrieved secret.")
        secret = get_secret_value_response['SecretString']
        secretDict = json.loads(secret)

    except Exception as e:
        logger.error(f"Error retrieving secret: {e}")
        raise e
    
    return secretDict

def insert_into_xenial_records_count():
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
    
    # Insert data into Snowflake
    unique_id = str(uuid.uuid4())
    cur = conn.cursor()
    # Specify the EST timezone
    est_timezone = pytz.timezone("US/Eastern")
    
    # Get the current time in EST
    current_dateTime = datetime.now(est_timezone)
    insert_query = f"INSERT INTO {XENIAL_SCHEMA_NAME}.{XENIAL_RESEND_RECORDS_COUNT}(XENIALDATAID, STATUS, START_TIMESTAMP) values('{unique_id}', 'processing', '{current_dateTime}')"
    cur.execute(insert_query)
    cur.close()
    conn.commit()
    
    return unique_id

def insert_into_xenialOrders_table(secretDict, event):
    # Snowflake connection
    return_dict = dict()

    return_dict['status'] = SUCCESS
    return_dict['errorMessage'] = ""
    return_dict['records_count'] = 0
    
    logger.info("Initiating Snowflake connection...")

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
    
    # Kinesis setup
    logger.info(f"Setting up Kinesis with stream name {KINESIS_STREAM_NAME}")
    kinesis = boto3.client('kinesis')

    # Parsing the timestamps from the event payload
    est = pytz.timezone('US/Eastern')  # Define the EST timezone
    start_timestamp = datetime.strptime(event['start_timestamp'], '%Y-%m-%d') #.astimezone(est)  # Convert to EST
    end_timestamp = datetime.strptime(event['end_timestamp'], '%Y-%m-%d') #.astimezone(est)  # Convert to EST
    
    eastern_timezone = pytz.timezone('US/Eastern')
    
    start_timestamp = eastern_timezone.localize(start_timestamp).replace(hour=0, minute=0, second=0, microsecond=0)
    end_timestamp = eastern_timezone.localize(end_timestamp).replace(hour=23, minute=59, second=59, microsecond=0)
    record_timestamp = start_timestamp
    insertionData = list()


    records_found = False

    # Fetching Kinesis Records
    try:
        logger.info("Fetching Kinesis records...")
        shards = kinesis.describe_stream(StreamName=KINESIS_STREAM_NAME)['StreamDescription']['Shards']
        
        for shard in shards:
            
            shard_id = shard['ShardId']
            
            shard_iterator = kinesis.get_shard_iterator(
                StreamName=KINESIS_STREAM_NAME,
                ShardId=shard_id,
                ShardIteratorType='AT_TIMESTAMP',
                Timestamp=start_timestamp)['ShardIterator']
            
            while shard_iterator:
                response = kinesis.get_records(ShardIterator=shard_iterator, Limit=1000)
                for record in response['Records']:
                    record_timestamp = record['ApproximateArrivalTimestamp'].astimezone(est)  # Convert to EST
                    
            
                    logging.info(f"Record arrived time: {record_timestamp}")  # Log arrived_time to CloudWatch
                    
                    
                    if record_timestamp.date() > end_timestamp.date():
                        break
                    
                    
                    
                    if start_timestamp <= record_timestamp <= end_timestamp:
                        records_found = True
                        return_dict['records_count'] += 1
                        # Process the record
                        record_data = json.loads(record['Data'].decode('utf-8'))
                        logging.info(f"Record Data: {record_data}")
    
                        # Extract relevant data from the record_data
                        source_json = json.dumps(record_data)
                        created_date = record_timestamp
                        user = secretDict["snowflakeUsername"]
    
                        
                        insertionData.append((source_json, created_date, user))
                        # insert_query = f"INSERT INTO {XENIAL_SCHEMA_NAME}.{POC_RAW_XENIAL_ORDERS}(source_json, created_date, created_by)  select parse_json($1), $2, $3 from values(%s, %s, %s)"
                        # cur.executemany(insert_query, [(source_json, created_date, user)])
                        # conn.commit()
                        
                        logger.info("Inserted data into Snowflake successfully.")
                    
                    
                        
                    print("records_count:", return_dict['records_count'])
                    
                        

                shard_iterator = response.get('NextShardIterator')
                if not shard_iterator or response['MillisBehindLatest'] in (0,'0') or record_timestamp.date() > end_timestamp.date():
                    break
                
        cur = conn.cursor()
       
        insert_query = f"""INSERT INTO {XENIAL_SCHEMA_NAME}.{POC_RAW_XENIAL_ORDERS} (source_json, created_date, created_by) select parse_json($1), $2, $3 from VALUES (%s, %s, %s);"""
        
        print("insertionData", insertionData)
        cur.executemany(insert_query, insertionData)
        conn.commit()
        
        # Insert data into Snowflake
        # Specify the EST timezone
        est_timezone = pytz.timezone("US/Eastern")
        
        # Get the current time in EST
        current_time_est = datetime.now(est_timezone)

        xenial_data_id = event['xenial_data_id']
        print("xenial_data_id:", xenial_data_id)
        print("records_count:",  return_dict['records_count'] )
        cur = conn.cursor()
        update_query = f"UPDATE {XENIAL_SCHEMA_NAME}.{XENIAL_RESEND_RECORDS_COUNT} SET STATUS = 'complete', COUNT = %s, END_TIMESTAMP = %s where XENIALDATAID = %s"
        cur.execute(update_query, ( return_dict['records_count'], current_time_est, xenial_data_id))
        print("query executed")
        cur.close()
        conn.commit()
        conn.close()
        
        if not records_found:
            raise Exception("No records found in the specified time frame.")
        
    except Exception as e:
        print("Some exception occured in insert_into_xenialOrders_table function")
        print("Exception Message:", e)
        return_dict['status'] = FAILED
        return_dict['errorMessage'] = e

    return return_dict 



def prepare_final_response(records_count, success = True, errMsg=""):
    if success:
        res = {
            'statusCode': 200,
            'message':'Lambda execution completed!',
            'records_count': records_count
            }
    else:
        res = {
            'statusCode': 400,
            'body': json.dumps(f"Error: {errMsg}")
            }
    return res
    
def check_http(data):
    """ Check if a http request has come and push it into SNS"""
    
    xenial_data_id = insert_into_xenial_records_count()
    data['xenial_data_id'] = xenial_data_id
    
    sns_status = publish_to_sns(data)
    print("The sns status is : {0}".format(sns_status))
    return {"message": "processing", "status": "200", "xenial_data_id" : xenial_data_id}

def publish_to_sns(message):
    """ Publishing data to sns"""

    sns = boto3.client('sns')
    print("SNS_ARN:", SNS_ARN)
    return sns.publish(
        TopicArn=SNS_ARN,
        Message=json.dumps(message),
        MessageStructure='string',
        MessageAttributes={
            'summary': {
                'StringValue': 'HTTP call to SNS',
                'DataType': 'String'
            }
        }
    )