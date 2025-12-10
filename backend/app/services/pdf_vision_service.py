"""PDF 하이브리드 처리 서비스 (텍스트 + 이미지)"""
import os
import json
import base64
from typing import Dict, List, Optional
import fitz  # PyMuPDF
from PIL import Image
import io
import boto3


class PDFVisionService:
    """PDF 페이지별 텍스트/이미지 하이브리드 처리"""

    def __init__(self):
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        # Vision을 지원하는 모델 ID (기존 bedrock_service.py와 동일)
        self.model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"

        # 설정
        self.text_threshold = 30  # 텍스트 최소 길이
        self.dpi = 150  # 이미지 렌더링 해상도 (5MB 제한 대응)
        self.drawing_complexity_threshold = 10  # 복잡한 레이아웃 판단 기준
        self.max_image_size_bytes = 5 * 1024 * 1024  # Bedrock 이미지 크기 제한 (5MB)

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
        페이지가 복잡한 레이아웃인지 판단 (표, 차트 등)

        Args:
            page: PyMuPDF 페이지 객체

        Returns:
            복잡한 페이지 여부
        """
        # 드로잉 객체 수 확인
        drawings = page.get_drawings()

        # 이미지 객체 수 확인
        images = page.get_images(full=True)

        # 드로잉이 많거나 이미지가 있으면 복잡한 페이지로 판단
        return len(drawings) > self.drawing_complexity_threshold or len(images) > 0

    async def extract_text_from_image(
        self,
        image_bytes: bytes
    ) -> str:
        """
        Claude Vision API를 통해 이미지에서 텍스트 추출

        Args:
            image_bytes: PNG 이미지 바이트

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
            # Bedrock API 호출
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
                                "media_type": "image/jpeg",
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

            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )

            # 응답 파싱
            response_body = json.loads(response['body'].read())

            if response_body.get('content'):
                return response_body['content'][0]['text']

            return ""

        except Exception as e:
            print(f"Vision API 오류: {str(e)}")
            return ""

    async def process_pdf_page(
        self,
        page: fitz.Page,
        page_num: int
    ) -> Dict[str, any]:
        """
        PDF 페이지 하이브리드 처리 (텍스트/이미지 자동 판단)

        Args:
            page: PyMuPDF 페이지 객체
            page_num: 페이지 번호 (0-based)

        Returns:
            처리 결과 딕셔너리
        """
        # 1. 텍스트 추출
        text = page.get_text("text").strip()
        text_length = len(text)

        # 2. 페이지 복잡도 판단
        is_complex = self.is_page_complex(page)

        # 3. 처리 로직 분기
        if text_length >= self.text_threshold and not is_complex:
            # 케이스 1: 텍스트 충분하고 단순한 레이아웃 → 텍스트만 사용
            return {
                "page_num": page_num,
                "type": "text_only",
                "content": text,
                "text_length": text_length,
                "method": "direct_text_extraction"
            }

        elif text_length < self.text_threshold and is_complex:
            # 케이스 2: 텍스트 부족하고 복잡한 레이아웃 → 이미지만 처리
            img_bytes = self.capture_page_as_image(page, dpi=self.dpi)
            extracted_text = await self.extract_text_from_image(img_bytes)

            return {
                "page_num": page_num,
                "type": "image_to_text",
                "content": extracted_text,
                "text_length": len(extracted_text),
                "method": "vision_api_extraction",
                "original_text_length": text_length
            }

        elif text_length >= self.text_threshold and is_complex:
            # 케이스 3: 텍스트 충분하지만 복잡한 레이아웃 → 텍스트 우선 (선택적 이미지)
            # 비용 최적화: 텍스트가 충분하면 이미지 처리 스킵
            return {
                "page_num": page_num,
                "type": "text_with_complex_layout",
                "content": text,
                "text_length": text_length,
                "method": "direct_text_extraction",
                "note": "complex_layout_but_sufficient_text"
            }

        else:
            # 케이스 4: 텍스트 부족하고 단순한 레이아웃 → 텍스트만 (짧더라도)
            return {
                "page_num": page_num,
                "type": "short_text",
                "content": text,
                "text_length": text_length,
                "method": "direct_text_extraction",
                "note": "short_text_no_images"
            }

    async def process_pdf(
        self,
        pdf_path: str
    ) -> List[Dict[str, any]]:
        """
        PDF 전체 처리 (페이지별 하이브리드 처리)

        Args:
            pdf_path: PDF 파일 경로

        Returns:
            페이지별 처리 결과 리스트
        """
        results = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                result = await self.process_pdf_page(page, page_num)
                results.append(result)

            doc.close()

        except Exception as e:
            print(f"PDF 처리 오류: {str(e)}")
            raise

        return results

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
