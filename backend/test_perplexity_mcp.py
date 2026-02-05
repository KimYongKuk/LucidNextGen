"""Perplexity MCP 서버 연결 테스트"""
import asyncio
import subprocess
import sys
import os

# 환경변수 설정
# PERPLEXITY_API_KEY must be set in environment
if not os.environ.get("PERPLEXITY_API_KEY"):
    print("Error: PERPLEXITY_API_KEY environment variable not set")
    sys.exit(1)
os.environ["PERPLEXITY_TIMEOUT_MS"] = "60000"  # 1분
os.environ["PERPLEXITY_LOG_LEVEL"] = "DEBUG"

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

NPX_PATH = r"C:\Program Files\nodejs\npx.cmd"


async def test_perplexity_direct():
    """npx로 Perplexity MCP 서버 직접 테스트"""
    print("=" * 60)
    print("Perplexity MCP Server Test")
    print("=" * 60)

    # 1. npx 명령어 존재 확인
    print("\n[1/4] Checking npx availability...")
    try:
        result = subprocess.run(
            [NPX_PATH, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            shell=True
        )
        print(f"[OK] npx version: {result.stdout.strip()}")
    except Exception as e:
        print(f"[FAIL] npx not found: {e}")
        return False

    # 2. Perplexity API 키 테스트 (직접 HTTP 요청)
    print("\n[2/4] Testing Perplexity API key directly...")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": "Hello, say hi in 5 words"}],
                    "max_tokens": 20
                }
            )

            if response.status_code == 200:
                print("[OK] API key is valid!")
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                print(f"  Response: {content[:100]}...")
            elif response.status_code == 401:
                print("[FAIL] API key is INVALID (401 Unauthorized)")
                print(f"  Response: {response.text}")
                return False
            else:
                print(f"[WARN] Unexpected status: {response.status_code}")
                print(f"  Response: {response.text}")

    except ImportError:
        print("[SKIP] httpx not installed, skipping direct API test")
        print("  Install with: pip install httpx")
    except Exception as e:
        print(f"[FAIL] API test error: {e}")

    # 3. MCP 서버 시작 테스트
    print("\n[3/4] Starting MCP server process...")
    try:
        proc = await asyncio.create_subprocess_exec(
            NPX_PATH, "-yq", "@perplexity-ai/mcp-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ}
        )

        print("  Server process started, waiting for initialization...")

        # MCP initialize 메시지 전송
        init_msg = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n'

        proc.stdin.write(init_msg.encode())
        await proc.stdin.drain()

        # 응답 대기 (10초)
        try:
            stdout = await asyncio.wait_for(proc.stdout.readline(), timeout=15)
            response = stdout.decode().strip()
            if response:
                print(f"  [OK] Server response received!")
                print(f"  Response: {response[:150]}...")
            else:
                print("  [WARN] Empty response")
        except asyncio.TimeoutError:
            print("  [FAIL] No response from server (timeout)")
            # stderr 확인
            try:
                stderr = await asyncio.wait_for(proc.stderr.read(500), timeout=2)
                if stderr:
                    print(f"  stderr: {stderr.decode()[:200]}")
            except:
                pass

        proc.terminate()
        await proc.wait()

    except Exception as e:
        print(f"[FAIL] Server test error: {e}")

    # 4. perplexity_search 도구 직접 호출 테스트
    print("\n[4/4] Testing perplexity_search tool call...")
    try:
        proc = await asyncio.create_subprocess_exec(
            NPX_PATH, "-yq", "@perplexity-ai/mcp-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ}
        )

        # Initialize
        init_msg = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n'
        proc.stdin.write(init_msg.encode())
        await proc.stdin.drain()

        # Wait for init response
        await asyncio.wait_for(proc.stdout.readline(), timeout=15)

        # Initialized notification
        init_notif = '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        proc.stdin.write(init_notif.encode())
        await proc.stdin.drain()

        # Call perplexity_search
        search_msg = '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"perplexity_search","arguments":{"query":"hello world test"}}}\n'
        proc.stdin.write(search_msg.encode())
        await proc.stdin.drain()

        print("  Waiting for search result (up to 30 seconds)...")

        try:
            stdout = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
            response = stdout.decode().strip()
            if response:
                print(f"  [OK] Search response received!")
                print(f"  Response: {response[:200]}...")
            else:
                print("  [WARN] Empty response")
        except asyncio.TimeoutError:
            print("  [FAIL] Search timeout - no response")

        proc.terminate()
        await proc.wait()

    except Exception as e:
        print(f"[FAIL] Tool test error: {e}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_perplexity_direct())
