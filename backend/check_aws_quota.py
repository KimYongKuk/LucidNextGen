"""AWS Bedrock 쿼터 확인 스크립트"""
import boto3
from dotenv import load_dotenv
import os

load_dotenv()

# AWS 클라이언트 생성
session = boto3.Session(
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)

# Service Quotas 확인
quotas_client = session.client('service-quotas')

print("="*80)
print("AWS Bedrock 쿼터 확인")
print("="*80)

try:
    # Bedrock 서비스 쿼터 조회
    response = quotas_client.list_service_quotas(
        ServiceCode='bedrock'
    )

    print("\n현재 Bedrock 쿼터:")
    for quota in response.get('Quotas', []):
        quota_name = quota.get('QuotaName')
        value = quota.get('Value')
        unit = quota.get('Unit', '')

        if 'Claude' in quota_name or 'token' in quota_name.lower():
            print(f"  - {quota_name}: {value} {unit}")

except Exception as e:
    print(f"\n⚠️ 쿼터 조회 실패: {e}")
    print("\n대신 CloudWatch 메트릭으로 사용량 확인:")

    cloudwatch = session.client('cloudwatch')

    from datetime import datetime, timedelta

    # 최근 1시간 토큰 사용량
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/Bedrock',
        MetricName='Invocations',
        Dimensions=[
            {
                'Name': 'ModelId',
                'Value': os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')
            }
        ],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=3600,  # 1시간
        Statistics=['Sum']
    )

    print("\n최근 1시간 호출 횟수:")
    for datapoint in response.get('Datapoints', []):
        print(f"  - {datapoint['Timestamp']}: {datapoint['Sum']} 회")

print("\n" + "="*80)
print("\n💡 해결 방법:")
print("  1. AWS Console → Service Quotas → Amazon Bedrock")
print("  2. 'Tokens per day' 쿼터 증가 요청")
print("  3. 또는 다른 AWS 계정으로 분산")
print("\n" + "="*80)
