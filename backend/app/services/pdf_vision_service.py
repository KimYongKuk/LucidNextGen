"""PDF 하이브리드 처리 서비스 (텍스트 + 이미지)"""
import os
import json
import base64
import time
from typing import Dict, List, Optional
import fitz  # PyMuPDF
from PIL import Image
import io
import boto3


# ... (imports)
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor


def _log_timing(label: str, start_time: float, extra: str = ""):
    """타이밍 로그 출력"""
    elapsed = time.time() - start_time
    extra_str = f" | {extra}" if extra else ""
    print(f"[TIMING] {label}: {elapsed:.3f}s{extra_str}")
    sys.stdout.flush()

# ...

class PDFVisionService:
    """PDF 페이지별 텍스트/이미지 하이브리드 처리"""

    # 재시도 설정 상수
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # 초기 대기 시간 (초)
    MAX_DELAY = 30.0  # 최대 대기 시간 (초)

    def __init__(self):
        # ... (existing init)
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        self.model_id = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        self.text_threshold = 30
        self.dpi = 150
        self.drawing_complexity_threshold = 10
        self.max_image_size_bytes = 5 * 1024 * 1024

        # Vision API 동시 호출 제한 (환경변수로 설정 가능, 기본값 5)
        self.vision_concurrency = int(os.getenv('VISION_API_CONCURRENCY', '5'))

        # CPU 작업을 위한 스레드 풀 (CPU 코어 수에 따라 스케일링)
        self._executor = ThreadPoolExecutor(
            max_workers=min(os.cpu_count() or 4, 4),
            thread_name_prefix="pdf_vision_"
        )

    # ... (capture_page_as_image and is_page_complex remain the same but will be called via executor)

    def capture_page_as_image(
        self,
        page: fitz.Page,
        dpi: int = None
    ) -> bytes:
        """
        PDF 페이지를 이미지로 렌더링 (5MB 제한 준수)

        Args:
            page: PyMuPDF 페이지 객체
            dpi: 해상도 (None이면 자동 조정)

        Returns:
            JPEG 이미지 바이트
        """
        if dpi is None:
            dpi = self.dpi

        # DPI에 따른 확대 비율 계산 (72dpi 기준)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)

        # 렌더링 (알파 채널 없음, RGB)
        pix = page.get_pixmap(
            matrix=mat,
            alpha=False,
            colorspace=fitz.csRGB
        )

        # PNG 바이트로 변환
        img_bytes = pix.tobytes("png")

        # Pillow로 압축 및 크기 조정
        img = Image.open(io.BytesIO(img_bytes))

        # JPEG 압축으로 크기 줄이기 (품질 조정)
        quality = 85

        while quality > 20:
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=quality, optimize=True)
            img_bytes = output.getvalue()

            # 5MB 이하면 사용
            if len(img_bytes) <= self.max_image_size_bytes:
                return img_bytes

            # 크기 초과 시 품질 낮춤
            quality -= 15

        # 그래도 크면 리사이즈
        if len(img_bytes) > self.max_image_size_bytes:
            scale = 0.7
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

            output = io.BytesIO()
            img.save(output, format="JPEG", quality=70, optimize=True)
            img_bytes = output.getvalue()

        return img_bytes

    def is_page_complex(self, page: fitz.Page) -> bool:
        """
        페이지가 복잡한 레이아웃인지 판단 (표, 차트, 큰 이미지 등)

        판단 기준:
        1. 페이지의 20% 이상을 차지하는 큰 이미지가 있으면 → complex (스크린샷, 다이어그램 등)
        2. 의미 있는 이미지 + 복잡한 드로잉이 많으면 → complex (표+이미지 혼합)
        3. 복잡한 드로잉이 매우 많으면 → complex (표, 차트 단독)

        Args:
            page: PyMuPDF 페이지 객체

        Returns:
            복잡한 페이지 여부 (Vision API 필요 여부)
        """
        try:
            page_rect = page.rect
            page_area = page_rect.width * page_rect.height

            if page_area == 0:
                return False

            # 의미 있는 이미지 카운트 + 큰 이미지 감지
            images = page.get_images(full=True)
            significant_images = 0
            has_large_image = False

            for img in images:
                try:
                    xref = img[0]
                    rects = page.get_image_rects(xref)
                    if rects and len(rects) > 0:
                        img_ratio = rects[0].width * rects[0].height / page_area
                        if img_ratio > 0.05:
                            significant_images += 1
                        # 페이지의 20% 이상 차지하면 큰 이미지 (스크린샷, 다이어그램)
                        if img_ratio > 0.20:
                            has_large_image = True
                except Exception:
                    pass

            # 복잡한 드로잉만 카운트 (채워진 도형, 복잡한 경로)
            drawings = page.get_drawings()
            complex_drawings = 0

            for d in drawings:
                if d.get("fill") or len(d.get("items", [])) > 3:
                    complex_drawings += 1

            # 판정 기준:
            # 1. 큰 이미지(20%+)가 있으면 → Vision 필요 (스크린샷, 다이어그램 등)
            # 2. 의미 있는 이미지 + 복잡한 드로잉 → Vision 필요 (표+이미지 혼합)
            # 3. 복잡한 드로잉이 매우 많으면 → Vision 필요 (표/차트 단독)
            return has_large_image or \
                   (significant_images > 0 and complex_drawings > 30) or \
                   complex_drawings > 100

        except Exception:
            return False

    def _sync_invoke_vision_api(self, request_body: dict) -> dict:
        """
        동기 Vision API 호출 (ThreadPool에서 실행됨)
        지수 백오프 재시도 로직 포함

        Args:
            request_body: Bedrock API 요청 본문

        Returns:
            API 응답 본문

        Raises:
            Exception: 최대 재시도 횟수 초과 시
        """
        import random
        from botocore.exceptions import ClientError

        last_exception = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body)
                )
                return json.loads(response['body'].read())

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                last_exception = e

                # Throttling 또는 서비스 오류인 경우 재시도
                if error_code in ('ThrottlingException', 'ServiceUnavailableException',
                                  'ModelStreamErrorException', 'InternalServerException'):
                    # 지수 백오프 + 지터(jitter)
                    delay = min(
                        self.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1),
                        self.MAX_DELAY
                    )
                    print(f"[RETRY] Vision API {error_code}, attempt {attempt + 1}/{self.MAX_RETRIES}, "
                          f"waiting {delay:.2f}s")
                    sys.stdout.flush()
                    time.sleep(delay)
                else:
                    # 재시도 불가능한 오류는 즉시 raise
                    raise

            except Exception as e:
                # 네트워크 오류 등 기타 예외도 재시도
                last_exception = e
                delay = min(
                    self.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1),
                    self.MAX_DELAY
                )
                print(f"[RETRY] Vision API error: {str(e)}, attempt {attempt + 1}/{self.MAX_RETRIES}, "
                      f"waiting {delay:.2f}s")
                sys.stdout.flush()
                time.sleep(delay)

        # 모든 재시도 실패
        print(f"[ERROR] Vision API failed after {self.MAX_RETRIES} retries")
        sys.stdout.flush()
        raise last_exception

    @staticmethod
    def _detect_media_type(image_bytes: bytes) -> str:
        """이미지 바이너리의 매직바이트로 실제 media_type 감지"""
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if image_bytes[:2] == b'\xff\xd8':
            return "image/jpeg"
        if image_bytes[:4] == b'GIF8':
            return "image/gif"
        if image_bytes[:4] == b'RIFF' and len(image_bytes) > 12 and image_bytes[8:12] == b'WEBP':
            return "image/webp"
        return "image/jpeg"  # 폴백

    async def extract_text_from_image(
        self,
        image_bytes: bytes
    ) -> str:
        """
        Claude Vision API를 통해 이미지에서 텍스트 추출

        개선: run_in_executor를 사용하여 이벤트 루프 블로킹 방지

        Args:
            image_bytes: 이미지 바이트 (PNG/JPEG/GIF/WEBP)

        Returns:
            추출된 텍스트
        """
        # Base64 인코딩
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        # Vision API 프롬프트
        prompt = """이 PDF 페이지 이미지에서 모든 텍스트와 내용을 정확하게 추출해주세요.

지침:
1. 제목, 부제목, 본문, 표, 차트 설명, 그래프 레이블 등 모든 텍스트 포함
2. 원본 문서의 구조와 순서를 최대한 유지
3. 표는 마크다운 테이블 형식으로 변환
4. 차트나 그래프는 [차트: 설명] 형식으로 요약
5. 한국어와 영어 텍스트 모두 정확하게 추출
6. 불필요한 설명이나 해석 없이 원본 텍스트만 추출

출력 형식:
- 텍스트만 출력 (메타 정보 제외)
- 줄바꿈과 단락 구분 유지
"""

        try:
            # Bedrock API 요청 본문 구성
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": self._detect_media_type(image_bytes),
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }]
            }

            # 동기 호출을 executor로 감싸서 이벤트 루프 블로킹 방지
            loop = asyncio.get_running_loop()
            response_body = await loop.run_in_executor(
                self._executor,
                self._sync_invoke_vision_api,
                request_body
            )

            if response_body.get('content'):
                return response_body['content'][0]['text']

            return ""

        except Exception as e:
            print(f"Vision API 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return ""

    async def _run_in_executor(self, func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    async def process_pdf_page(
        self,
        page: fitz.Page,
        page_num: int
    ) -> Dict[str, any]:
        """
        PDF 페이지 하이브리드 처리 (텍스트/이미지 자동 판단)

        최적화: 충분한 텍스트가 있으면 복잡도 검사를 스킵하여 성능 향상
        """
        page_start = time.time()
        try:
            # 이벤트 루프가 숨쉴 수 있게 yield
            await asyncio.sleep(0)

            # 1. 텍스트 먼저 추출
            t0 = time.time()
            text = page.get_text("text").strip()
            text_length = len(text)
            _log_timing(f"Page {page_num} text extraction", t0, f"{text_length} chars")

            # FAST PATH: 충분한 텍스트(100자 이상)가 있으면 복잡도 검사 스킵
            # 대부분의 텍스트 기반 PDF는 이 경로로 즉시 처리됨
            if text_length >= 100:
                _log_timing(f"Page {page_num} TOTAL (fast-path)", page_start, "direct_text")
                return {
                    "page_num": page_num,
                    "type": "text_only",
                    "content": text,
                    "text_length": text_length,
                    "method": "direct_text_extraction"
                }

            # 2. 텍스트가 부족할 때만 복잡도 판단 (CPU bound)
            t0 = time.time()
            is_complex = self.is_page_complex(page)
            _log_timing(f"Page {page_num} complexity check", t0, f"complex={is_complex}")

            # 3. 처리 로직 분기 (기존 임계값 유지: 30자)
            if text_length >= self.text_threshold and not is_complex:
                _log_timing(f"Page {page_num} TOTAL", page_start, "direct_text (not complex)")
                return {
                    "page_num": page_num,
                    "type": "text_only",
                    "content": text,
                    "text_length": text_length,
                    "method": "direct_text_extraction"
                }

            elif text_length < self.text_threshold:
                # 텍스트가 거의 없는 페이지
                # 이미지가 있을 때만 Vision API 호출 (빈 페이지/구분선 페이지 낭비 방지)
                has_images = len(page.get_images(full=True)) > 0
                if has_images or is_complex:
                    t0 = time.time()
                    await asyncio.sleep(0)
                    img_bytes = self.capture_page_as_image(page, dpi=self.dpi)
                    await asyncio.sleep(0)
                    _log_timing(f"Page {page_num} image capture", t0, f"{len(img_bytes)} bytes")

                    # Vision API 호출
                    t0 = time.time()
                    extracted_text = await self.extract_text_from_image(img_bytes)
                    _log_timing(f"Page {page_num} Vision API", t0, f"{len(extracted_text)} chars extracted")

                    final_text = extracted_text if extracted_text.strip() else text

                    _log_timing(f"Page {page_num} TOTAL", page_start, f"vision_api (complex={is_complex})")
                    return {
                        "page_num": page_num,
                        "type": "image_to_text",
                        "content": final_text,
                        "text_length": len(final_text),
                        "method": "vision_api_extraction",
                        "original_text_length": text_length
                    }
                else:
                    # 텍스트 < 30자 + 이미지 없음 → 빈 페이지, Vision 불필요
                    _log_timing(f"Page {page_num} TOTAL", page_start, "direct_text (no images, skip vision)")
                    return {
                        "page_num": page_num,
                        "type": "text_only",
                        "content": text,
                        "text_length": text_length,
                        "method": "direct_text_extraction"
                    }

            else:
                # text >= 30 AND is_complex: 텍스트는 충분하지만 복잡한 레이아웃
                _log_timing(f"Page {page_num} TOTAL", page_start, "direct_text (complex but enough text)")
                return {
                    "page_num": page_num,
                    "type": "text_with_complex_layout",
                    "content": text,
                    "text_length": text_length,
                    "method": "direct_text_extraction",
                    "note": "complex_layout_but_sufficient_text"
                }
        except Exception as e:
            print(f"Page {page_num} processing error: {e}")
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            # 에러 발생 시 빈 결과 반환하여 전체 프로세스 중단 방지
            return {
                "page_num": page_num,
                "type": "error",
                "content": "",
                "error": str(e)
            }

    async def process_pdf(
        self,
        pdf_path: str
    ) -> List[Dict[str, any]]:
        """
        PDF 전체 처리 (페이지별 하이브리드 처리)

        개선: asyncio.gather()를 사용한 병렬 처리
        - Vision API 동시 호출은 Semaphore로 제한 (throttling 방지)
        - 텍스트 전용 페이지는 빠르게 처리됨
        """
        total_start = time.time()

        # Vision API 동시 호출 제한 (환경변수 VISION_API_CONCURRENCY로 설정, 기본값 5)
        vision_semaphore = asyncio.Semaphore(self.vision_concurrency)
        print(f"[CONFIG] Vision API concurrency: {self.vision_concurrency}")
        sys.stdout.flush()

        async def process_page_with_semaphore(page: fitz.Page, page_num: int) -> Dict[str, any]:
            """Semaphore로 보호된 페이지 처리"""
            async with vision_semaphore:
                return await self.process_pdf_page(page, page_num)

        try:
            print(f"\n{'='*60}")
            print(f"[PDF PROCESSING START] {pdf_path}")
            print(f"{'='*60}")
            sys.stdout.flush()

            t0 = time.time()
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            _log_timing("PDF open", t0, f"{total_pages} pages")

            # 페이지 수가 적으면 순차 처리 (오버헤드 방지)
            t0 = time.time()
            if total_pages <= 2:
                results = []
                for page_num in range(total_pages):
                    page = doc[page_num]
                    result = await self.process_pdf_page(page, page_num)
                    results.append(result)
            else:
                # 병렬 처리: 모든 페이지를 동시에 처리
                # Note: fitz 페이지 객체는 동일 문서 컨텍스트 내에서 사용
                tasks = []
                for page_num in range(total_pages):
                    page = doc[page_num]
                    tasks.append(process_page_with_semaphore(page, page_num))

                print(f"[INFO] Processing {total_pages} pages...")
                sys.stdout.flush()

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 예외를 에러 결과로 변환
                processed_results = []
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"Page {i} failed: {result}")
                        processed_results.append({
                            "page_num": i,
                            "type": "error",
                            "content": "",
                            "error": str(result)
                        })
                    else:
                        processed_results.append(result)
                results = processed_results

            _log_timing("All pages processing", t0)

            doc.close()

            # 결과 요약
            methods = {}
            for r in results:
                m = r.get("method", "unknown")
                methods[m] = methods.get(m, 0) + 1

            print(f"\n{'='*60}")
            _log_timing("PDF PROCESSING TOTAL", total_start, f"methods: {methods}")
            print(f"{'='*60}\n")
            sys.stdout.flush()

            return results

        except Exception as e:
            print(f"PDF 처리 치명적 오류: {str(e)}")
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            raise

# ... (combine_page_contents and singleton)

    def combine_page_contents(
        self,
        page_results: List[Dict[str, any]]
    ) -> str:
        """
        페이지별 처리 결과를 하나의 텍스트로 결합

        Args:
            page_results: process_pdf() 결과

        Returns:
            결합된 전체 텍스트
        """
        combined = []

        for result in page_results:
            page_num = result['page_num']
            content = result['content']

            # 페이지 구분자 추가
            combined.append(f"\n\n--- 페이지 {page_num + 1} ---\n")
            combined.append(content)

        return "".join(combined)


# 싱글톤
_pdf_vision_service = None

def get_pdf_vision_service() -> PDFVisionService:
    global _pdf_vision_service
    if _pdf_vision_service is None:
        _pdf_vision_service = PDFVisionService()
    return _pdf_vision_service
