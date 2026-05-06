# -*- coding: utf-8 -*-
"""Outline Wiki → ChromaDB 초기 동기화 단독 실행 스크립트

사용법:
  cd backend
  python -X utf8 run_outline_sync.py

백그라운드 실행 (로그 파일로 확인):
  cd backend
  nohup python -X utf8 run_outline_sync.py > logs/outline_sync.log 2>&1 &

  # 또는 Windows:
  start /B python -X utf8 run_outline_sync.py > logs\outline_sync.log 2>&1

진행 확인:
  tail -f logs/outline_sync.log        (Linux)
  type logs\outline_sync.log           (Windows)
"""
import os
import sys
import asyncio
import time
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

# Windows 환경
if sys.platform == 'win32':
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# 로그 디렉토리 확보
os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)


async def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"[OutlineSync] 초기 동기화 시작 ({now})")
    print(f"[OutlineSync] OUTLINE_API_URL: {os.getenv('OUTLINE_API_URL', '(not set)')}")
    print(f"[OutlineSync] OUTLINE_API_KEY: {'***set***' if os.getenv('OUTLINE_API_KEY') else '(not set)'}")
    print("=" * 60)
    sys.stdout.flush()

    from app.services.outline_sync_service import get_outline_sync_service
    service = get_outline_sync_service()

    start = time.time()
    result = await service.full_sync()
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print(f"[OutlineSync] 완료! ({datetime.now().strftime('%H:%M:%S')})")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print(f"\n  총 소요 시간: {elapsed:.1f}초")
    print("=" * 60)
    sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())