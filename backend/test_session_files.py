"""세션 파일 관리 테스트 스크립트"""
import asyncio
import sys
import os

# UTF-8 출력 설정 (Windows)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.abspath('.'))

from app.services.chromadb_service import get_chromadb_service


async def test_session_file_management():
    """세션 파일 관리 테스트"""

    print("\n" + "="*80)
    print("세션 파일 관리 테스트")
    print("="*80 + "\n")

    chromadb = get_chromadb_service()

    # 테스트 데이터
    test_session_id = "test_session_123"
    test_user_id = "test_user"

    # 시나리오 1: 첫 번째 파일 업로드
    print("[테스트 1] 첫 번째 파일 업로드")
    print("-" * 80)

    file1_content = b"This is test file 1. It contains some text for testing."
    result1 = await chromadb.upload_file(
        file_content=file1_content,
        filename="test_file_1.txt",
        user_id=test_user_id,
        session_id=test_session_id,
        replace_existing=True
    )

    print(f"✓ 파일 1 업로드 완료: {result1['filename']}")
    print(f"  - File ID: {result1['file_id']}")
    print(f"  - Chunks: {result1['chunks']}")

    # 검색 테스트
    search_result1 = await chromadb.search(
        query="test file",
        user_id=test_user_id,
        session_id=test_session_id,
        limit=3
    )
    print(f"  - 검색 결과 수: {len(search_result1)}")
    if search_result1:
        print(f"  - 첫 번째 검색 결과: {search_result1[0]['metadata']}")

    print()

    # 시나리오 2: 두 번째 파일 업로드 (기존 파일 교체)
    print("[테스트 2] 두 번째 파일 업로드 (기존 파일 교체)")
    print("-" * 80)

    file2_content = b"This is test file 2. It has completely different content about Python programming."
    result2 = await chromadb.upload_file(
        file_content=file2_content,
        filename="test_file_2.txt",
        user_id=test_user_id,
        session_id=test_session_id,
        replace_existing=True  # 기존 파일 삭제 후 업로드
    )

    print(f"✓ 파일 2 업로드 완료: {result2['filename']}")
    print(f"  - File ID: {result2['file_id']}")
    print(f"  - Chunks: {result2['chunks']}")

    # 검색 테스트 (파일 1은 없어야 함)
    search_result2 = await chromadb.search(
        query="test file",
        user_id=test_user_id,
        session_id=test_session_id,
        limit=3
    )
    print(f"  - 검색 결과 수: {len(search_result2)}")
    if search_result2:
        print(f"  - 첫 번째 검색 결과: {search_result2[0]['metadata']}")

    # 파일 1 키워드로 검색 (없어야 함)
    search_file1 = await chromadb.search(
        query="test file 1",
        user_id=test_user_id,
        session_id=test_session_id,
        limit=3
    )

    # 파일 2 키워드로 검색 (있어야 함)
    search_file2 = await chromadb.search(
        query="Python programming",
        user_id=test_user_id,
        session_id=test_session_id,
        limit=3
    )

    print(f"\n  [검증] 파일 1 키워드 검색 결과: {len(search_file1)}개")
    print(f"  [검증] 파일 2 키워드 검색 결과: {len(search_file2)}개")

    if len(search_file2) > 0 and len(search_result2) == result2['chunks']:
        print("\n  ✅ 성공: 기존 파일이 삭제되고 새 파일만 존재함")
    else:
        print("\n  ❌ 실패: 파일 교체가 제대로 작동하지 않음")

    print()

    # 시나리오 3: replace_existing=False로 추가 업로드
    print("[테스트 3] 파일 추가 업로드 (기존 파일 유지)")
    print("-" * 80)

    file3_content = b"This is test file 3. Additional content for testing append mode."
    result3 = await chromadb.upload_file(
        file_content=file3_content,
        filename="test_file_3.txt",
        user_id=test_user_id,
        session_id=test_session_id,
        replace_existing=False  # 기존 파일 유지
    )

    print(f"✓ 파일 3 업로드 완료: {result3['filename']}")
    print(f"  - File ID: {result3['file_id']}")
    print(f"  - Chunks: {result3['chunks']}")

    # 전체 검색
    search_all = await chromadb.search(
        query="test file",
        user_id=test_user_id,
        session_id=test_session_id,
        limit=10
    )

    print(f"\n  - 전체 검색 결과 수: {len(search_all)}")

    filenames = set()
    for doc in search_all:
        if 'metadata' in doc and 'filename' in doc['metadata']:
            filenames.add(doc['metadata']['filename'])

    print(f"  - 검색된 파일명: {filenames}")

    if len(filenames) >= 2:
        print("\n  ✅ 성공: 파일 2와 파일 3 모두 존재함")
    else:
        print("\n  ❌ 실패: 파일이 제대로 추가되지 않음")

    print()

    # 시나리오 4: 세션 전체 삭제
    print("[테스트 4] 세션 전체 삭제")
    print("-" * 80)

    delete_result = await chromadb.delete_session_files(test_session_id)
    print(f"✓ 삭제 결과: {delete_result}")

    # 검색 (없어야 함)
    search_after_delete = await chromadb.search(
        query="test file",
        user_id=test_user_id,
        session_id=test_session_id,
        limit=10
    )

    print(f"  - 삭제 후 검색 결과 수: {len(search_after_delete)}")

    if len(search_after_delete) == 0:
        print("\n  ✅ 성공: 세션의 모든 파일이 삭제됨")
    else:
        print("\n  ❌ 실패: 파일이 제대로 삭제되지 않음")

    print()

    # 최종 요약
    print("="*80)
    print("테스트 완료")
    print("="*80)


async def main():
    """메인 함수"""
    await test_session_file_management()


if __name__ == "__main__":
    # .env 파일 로드
    from dotenv import load_dotenv
    load_dotenv()

    # 비동기 실행
    asyncio.run(main())
