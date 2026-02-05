"""AWS Bedrock 사용량 및 제한 확인"""
import boto3
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)

cloudwatch = session.client('cloudwatch')
model_id = os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')

print("="*80)
print(f"AWS Bedrock Usage Report - {model_id}")
print("="*80)

# 최근 1시간 호출 횟수
try:
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/Bedrock',
        MetricName='Invocations',
        Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=3600,
        Statistics=['Sum']
    )

    if response['Datapoints']:
        invocations = response['Datapoints'][0]['Sum']
        print(f"\nTotal Invocations (last 1 hour): {int(invocations)}")
    else:
        print("\nNo invocation data available for the last hour")

except Exception as e:
    print(f"\nFailed to get invocations: {e}")

# Throttle 발생 횟수 (중요!)
try:
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/Bedrock',
        MetricName='InvocationThrottle',
        Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=3600,
        Statistics=['Sum']
    )

    if response['Datapoints']:
        throttles = response['Datapoints'][0]['Sum']
        print(f"Throttle Events (last 1 hour): {int(throttles)} ⚠️")
        if throttles > 0:
            print("  → Rate limit exceeded! This is causing the 10s delays.")
    else:
        print("Throttle Events (last 1 hour): 0 ✅")

except Exception as e:
    print(f"\nFailed to get throttles: {e}")

# 오류 발생 횟수
try:
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/Bedrock',
        MetricName='InvocationClientError',
        Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=3600,
        Statistics=['Sum']
    )

    if response['Datapoints']:
        errors = response['Datapoints'][0]['Sum']
        print(f"Client Errors (last 1 hour): {int(errors)}")
    else:
        print("Client Errors (last 1 hour): 0 ✅")

except Exception as e:
    print(f"\nFailed to get errors: {e}")

print("\n" + "="*80)
print("\nInterpretation:")
print("  - Throttle > 0 → You hit rate limits (RPM/TPM)")
print("  - High errors → Quota exhausted or configuration issue")
print("  - Both zero → Server-side delays (AWS internal or MCP)")
print("\n" + "="*80)
