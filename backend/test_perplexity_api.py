"""Perplexity API 직접 테스트 (MCP 없이)"""
import asyncio
import httpx
import sys
import os

API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")

async def test_api():
    print("Testing Perplexity API directly...")
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-4:]}")

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": "What is 2+2? Answer in one word."}],
                    "max_tokens": 10
                }
            )

            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                print(f"SUCCESS! Response: {content}")
            else:
                print(f"FAILED! Response: {response.text}")

        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())
