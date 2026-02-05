"""간단한 Bedrock 연결 및 응답 시간 테스트"""
import boto3
import time
import os
from dotenv import load_dotenv

load_dotenv()

client = boto3.client(
    service_name='bedrock-runtime',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

model_id = os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')

print("="*80)
print("Bedrock Simple Response Time Test")
print("="*80)

# 5번 연속 호출하여 평균 응답 시간 측정
times = []
for i in range(5):
    try:
        start = time.time()

        response = client.converse(
            modelId=model_id,
            messages=[
                {"role": "user", "content": [{"text": "Hi"}]}
            ],
            inferenceConfig={
                "maxTokens": 50,
                "temperature": 0.5
            }
        )

        elapsed = (time.time() - start) * 1000
        times.append(elapsed)

        print(f"Request {i+1}: {elapsed:.0f}ms ✅")
        time.sleep(1)  # 1초 대기

    except Exception as e:
        print(f"Request {i+1}: FAILED - {e}")
        if "ThrottlingException" in str(e):
            print("  → THROTTLED! You are hitting rate limits.")
            break

if times:
    print("\n" + "="*80)
    print(f"Average Response Time: {sum(times)/len(times):.0f}ms")
    print(f"Min: {min(times):.0f}ms, Max: {max(times):.0f}ms")
    print("="*80)

    if sum(times)/len(times) > 2000:
        print("\n⚠️  Average > 2s → AWS may be throttling or overloaded")
    else:
        print("\n✅ Response times are normal")
