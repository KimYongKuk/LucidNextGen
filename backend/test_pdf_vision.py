"""PDF Vision 서비스 테스트 스크립트"""
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

from app.services.pdf_vision_service import get_pdf_vision_service


async def test_pdf_processing(pdf_path: str):
    """PDF 하이브리드 처리 테스트"""

    print(f"\n{'='*80}")
    print(f"PDF 파일 테스트: {pdf_path}")
    print(f"{'='*80}\n")

    if not os.path.exists(pdf_path):
        print(f"❌ 파일을 찾을 수 없습니다: {pdf_path}")
        return

    try:
        # PDF Vision 서비스 가져오기
        pdf_vision = get_pdf_vision_service()

        # PDF 처리
        print("📄 PDF 처리 중...")
        page_results = await pdf_vision.process_pdf(pdf_path)

        # 결과 출력
        print(f"\n✅ 총 {len(page_results)}개 페이지 처리 완료\n")

        for result in page_results:
            page_num = result['page_num']
            page_type = result['type']
            method = result['method']
            text_length = result['text_length']
            content = result['content'][:200]  # 처음 200자만 미리보기

            print(f"{'─'*80}")
            print(f"📑 페이지 {page_num + 1}")
            print(f"   타입: {page_type}")
            print(f"   처리 방법: {method}")
            print(f"   텍스트 길이: {text_length}자")

            if 'original_text_length' in result:
                print(f"   원본 텍스트 길이: {result['original_text_length']}자")

            if 'note' in result:
                print(f"   참고: {result['note']}")

            print(f"\n   내용 미리보기:")
            print(f"   {content.replace(chr(10), ' ')[:200]}...")
            print()

        # 전체 텍스트 결합
        combined_text = pdf_vision.combine_page_contents(page_results)

        print(f"{'='*80}")
        print(f"📊 결합된 전체 텍스트 길이: {len(combined_text)}자")
        print(f"{'='*80}\n")

        # 통계
        type_counts = {}
        for result in page_results:
            page_type = result['type']
            type_counts[page_type] = type_counts.get(page_type, 0) + 1

        print("📈 처리 방법별 페이지 수:")
        for page_type, count in type_counts.items():
            print(f"   - {page_type}: {count}개")

        print()

    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


async def main():
    """메인 함수"""

    # 환경변수 확인
    required_env = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION']
    missing_env = [var for var in required_env if not os.getenv(var)]

    if missing_env:
        print(f"❌ 필요한 환경변수가 설정되지 않았습니다: {', '.join(missing_env)}")
        print("   .env 파일을 확인하세요.")
        return

    # 테스트할 PDF 파일 경로
    # 사용자가 직접 PDF 경로를 지정하거나, 명령줄 인자로 전달
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # 기본 테스트 파일 경로 (없으면 샘플 생성)
        pdf_path = "./test_sample.pdf"

        if not os.path.exists(pdf_path):
            print("ℹ️  테스트 PDF 파일이 없습니다.")
            print(f"   사용법: python test_pdf_vision.py [PDF_파일_경로]")
            print(f"   예시: python test_pdf_vision.py ./data/sample.pdf")
            return

    # 테스트 실행
    await test_pdf_processing(pdf_path)


if __name__ == "__main__":
    # .env 파일 로드
    from dotenv import load_dotenv
    load_dotenv()

    # 비동기 실행
    asyncio.run(main())
