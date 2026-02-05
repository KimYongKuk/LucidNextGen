"""YouTube 요약 서비스

n8n webhook을 호출하여 유튜브 비디오 요약을 가져오고,
결과를 MariaDB에 저장하여 캐싱합니다.
"""
import os
import re
import json
import asyncio
import sys
from typing import Optional, Dict
import aiohttp
from dotenv import load_dotenv

from app.core.database import get_database_connection

load_dotenv()

# MCP 서버에서도 로그가 보이도록 stderr에 출력
def log(message):
    print(message, file=sys.stderr, flush=True)
    print(message, flush=True)


class YoutubeSummaryService:
    """YouTube 비디오 요약 서비스"""

    def __init__(self):
        self.webhook_url = os.getenv(
            "N8N_YOUTUBE_WEBHOOK_URL",
            "http://localhost:5678/webhook/youtube-summary"
        )
        self.timeout = int(os.getenv("N8N_WEBHOOK_TIMEOUT", "15"))
        self.db = get_database_connection()

    @staticmethod
    def extract_video_id(youtube_url: str) -> Optional[str]:
        """
        유튜브 URL에서 video_id를 추출합니다.

        지원 형식:
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtube.com/watch?v=VIDEO_ID
        - https://m.youtube.com/watch?v=VIDEO_ID

        Args:
            youtube_url: 유튜브 URL

        Returns:
            video_id (11자리 문자열) 또는 None
        """
        # 정규식 패턴 (쿼리 파라미터 제외를 위해 ? 앞에서 종료)
        patterns = [
            # youtu.be/VIDEO_ID 형태 (? 또는 & 앞에서 종료)
            r'youtu\.be/([a-zA-Z0-9_-]{11})(?:[?&]|$)',
            # youtube.com/watch?v=VIDEO_ID 형태 (& 또는 공백 앞에서 종료)
            r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})(?:&|$)',
            # youtube.com/embed/VIDEO_ID 형태
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})(?:[?&]|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, youtube_url)
            if match:
                video_id = match.group(1)
                # 추가 검증: 정확히 11자리인지 확인
                if len(video_id) == 11:
                    return video_id

        return None

    async def get_summary_by_video_id(self, video_id: str) -> Optional[Dict]:
        """
        DB에서 캐시된 요약을 조회합니다.

        Args:
            video_id: 유튜브 비디오 ID

        Returns:
            요약 데이터 dict 또는 None
        """
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    video_id, title, original_link, summary, insight,
                    keywords, segments, created_at, user_id
                FROM youtube_summaries
                WHERE video_id = %s
                """
                cursor.execute(query, (video_id,))
                row = cursor.fetchone()

                if row:
                    print(f"[CACHE HIT] video_id: {video_id}")
                    # JSON 문자열을 dict로 변환
                    if isinstance(row['keywords'], str):
                        row['keywords'] = json.loads(row['keywords']) if row['keywords'] else []
                    if isinstance(row['segments'], str):
                        row['segments'] = json.loads(row['segments']) if row['segments'] else []

                    # MCP 도구에서 JSON 직렬화 가능하도록 created_at, user_id 제외
                    return {
                        'video_id': row['video_id'],
                        'title': row['title'],
                        'original_link': row['original_link'],
                        'summary': row['summary'],
                        'insight': row['insight'],
                        'keywords': row['keywords'],
                        'segments': row['segments']
                    }

                return None

        except Exception as e:
            print(f"[DB ERROR] 캐시 조회 실패: {str(e)}")
            return None

    async def call_n8n_webhook(self, video_id: str, youtube_url: str) -> Dict:
        """
        n8n webhook을 호출하여 유튜브 비디오 요약을 가져옵니다.

        Args:
            video_id: 유튜브 비디오 ID
            youtube_url: 유튜브 URL

        Returns:
            n8n 응답 JSON

        Raises:
            aiohttp.ClientError: HTTP 요청 실패
            asyncio.TimeoutError: 타임아웃
        """
        # 하이픈으로 시작하는 video_id의 경우, 표준 youtube.com URL로 정규화
        # (일부 라이브러리/API가 -로 시작하는 ID를 옵션으로 오인할 수 있음)
        if video_id.startswith('-'):
            normalized_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f"[N8N] video_id starts with '-', using normalized URL: {normalized_url}")
        else:
            normalized_url = youtube_url

        payload = {
            "youtube_url": normalized_url,
            "prompt": "요약해줘"
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        print(f"[N8N] Calling webhook: {self.webhook_url}")
        print(f"[N8N] Payload: {payload}")

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    if data is None:
                        print(f"[N8N] ERROR: Received None response")
                        return None

                    # n8n 응답 구조: {title: "...", video_id: "...", ...} 또는 [{...}]
                    print(f"[N8N] Raw response type: {type(data)}")

                    # 패턴 1: 배열 형태 [{...}]
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                        summary_data = data[0]
                        print(f"[N8N] Array format detected, extracting first element")
                    # 패턴 2: 직접 객체 형태 {...}
                    elif isinstance(data, dict):
                        summary_data = data
                        print(f"[N8N] Direct object format detected")
                    else:
                        print(f"[N8N] ERROR: Unexpected response format")
                        print(f"[N8N] Response: {str(data)[:1000]}...")
                        raise Exception("n8n 응답 형식이 올바르지 않습니다. dict 또는 [dict] 형태를 예상했습니다.")

                    print(f"[N8N] Successfully received summary data!")
                    print(f"[N8N] Keys: {list(summary_data.keys())}")
                    print(f"[N8N] Title: {summary_data.get('title', 'N/A')[:100]}...")
                    print(f"[N8N] Video ID: {summary_data.get('video_id', 'N/A')}")

                    return summary_data
        except aiohttp.ClientConnectorError as e:
            print(f"[N8N] ERROR: Cannot connect to n8n server at {self.webhook_url}")
            print(f"[N8N] Error details: {str(e)}")
            raise
        except asyncio.TimeoutError:
            print(f"[N8N] ERROR: Webhook timeout after {self.timeout} seconds")
            raise
        except Exception as e:
            print(f"[N8N] ERROR: {str(e)}")
            raise

    async def save_summary(self, summary_data: Dict, user_id: str) -> int:
        """
        요약 데이터를 MariaDB에 저장합니다.

        Args:
            summary_data: n8n에서 받은 요약 데이터
            user_id: 요청한 사용자 ID

        Returns:
            저장된 레코드의 id

        Raises:
            Exception: DB 저장 실패
        """
        try:
            # n8n이 잘못된 video_id를 반환할 수 있으므로 정제
            raw_video_id = summary_data.get('video_id', '')

            # 쿼리 파라미터 제거 (? 이후 모두 제거)
            if '?' in raw_video_id:
                clean_video_id = raw_video_id.split('?')[0]
                print(f"[DB] video_id 정제: '{raw_video_id}' -> '{clean_video_id}'")
            else:
                clean_video_id = raw_video_id

            # video_id 길이 검증
            if len(clean_video_id) != 11:
                print(f"[DB WARNING] video_id 길이가 11이 아님: '{clean_video_id}' (len={len(clean_video_id)})")
                # 11자리로 자르기
                clean_video_id = clean_video_id[:11]

            # summary_data에 정제된 video_id 업데이트
            summary_data['video_id'] = clean_video_id

            with self.db.get_cursor() as cursor:
                # JSON 데이터를 문자열로 변환
                keywords_json = json.dumps(summary_data.get('keywords', []), ensure_ascii=False)
                segments_json = json.dumps(summary_data.get('segments', []), ensure_ascii=False)

                query = """
                INSERT INTO youtube_summaries
                (video_id, title, original_link, summary, insight, keywords, segments, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    original_link = VALUES(original_link),
                    summary = VALUES(summary),
                    insight = VALUES(insight),
                    keywords = VALUES(keywords),
                    segments = VALUES(segments),
                    updated_at = CURRENT_TIMESTAMP,
                    user_id = VALUES(user_id)
                """

                cursor.execute(query, (
                    summary_data['video_id'],
                    summary_data['title'],
                    summary_data['original_link'],
                    summary_data['summary'],
                    summary_data.get('insight'),
                    keywords_json,
                    segments_json,
                    user_id
                ))

                # 저장된 ID 반환
                if cursor.lastrowid:
                    record_id = cursor.lastrowid
                else:
                    # UPDATE인 경우 기존 ID 조회
                    cursor.execute(
                        "SELECT id FROM youtube_summaries WHERE video_id = %s",
                        (summary_data['video_id'],)
                    )
                    record_id = cursor.fetchone()['id']

                print(f"[DB] 요약 저장 완료: id={record_id}, video_id={summary_data['video_id']}")
                return record_id

        except Exception as e:
            print(f"[DB ERROR] 요약 저장 실패: {str(e)}")
            raise

    async def summarize_video(self, youtube_url: str, user_id: str = "anonymous") -> Dict:
        """
        유튜브 비디오를 요약합니다.

        1. URL에서 video_id 추출
        2. DB 캐시 확인
        3. 캐시 미스 시 n8n webhook 호출
        4. DB에 저장
        5. 결과 반환

        Args:
            youtube_url: 유튜브 URL
            user_id: 요청 사용자 ID

        Returns:
            요약 데이터 dict

        Raises:
            ValueError: 잘못된 URL
            Exception: n8n 호출 또는 DB 저장 실패
        """
        print(f"\n[YouTube Summary] ===== START =====")
        print(f"[YouTube Summary] URL: {youtube_url}")
        print(f"[YouTube Summary] User: {user_id}")

        # 1. video_id 추출
        video_id = self.extract_video_id(youtube_url)
        if not video_id:
            raise ValueError(f"유효하지 않은 유튜브 URL입니다: {youtube_url}")

        print(f"[YouTube Summary] video_id: {video_id}")

        # 2. DB 캐시 확인
        cached = await self.get_summary_by_video_id(video_id)
        if cached:
            print(f"[YouTube Summary] 캐시된 요약 반환")
            return cached

        # 3. n8n webhook 호출
        print(f"[YouTube Summary] n8n webhook 호출 중...")
        try:
            summary_data = await self.call_n8n_webhook(video_id, youtube_url)

            # n8n이 None을 반환한 경우
            if summary_data is None:
                raise Exception("n8n webhook이 응답하지 않았습니다. n8n 서버가 실행 중인지 확인해주세요.")

            # 필수 필드 검증
            if not isinstance(summary_data, dict):
                raise Exception(f"n8n 응답 형식이 올바르지 않습니다. dict가 아닌 {type(summary_data)}를 받았습니다.")

            required_fields = ['video_id', 'title', 'summary']
            missing_fields = [field for field in required_fields if field not in summary_data]
            if missing_fields:
                raise Exception(f"n8n 응답에 필수 필드가 누락되었습니다: {', '.join(missing_fields)}")

        except aiohttp.ClientError as e:
            raise Exception(f"유튜브 요약 서비스에 연결할 수 없습니다: {str(e)}")
        except Exception as e:
            # 이미 포맷된 메시지는 그대로 전달
            if "n8n" in str(e) or "필수 필드" in str(e):
                raise
            raise Exception(f"유튜브 요약 중 오류가 발생했습니다: {str(e)}")

        # 4. DB 저장
        try:
            await self.save_summary(summary_data, user_id)
        except Exception as e:
            print(f"[YouTube Summary] DB 저장 실패 (요약은 반환): {str(e)}")
            # DB 저장 실패해도 요약 결과는 반환

        # 5. 결과 반환
        print(f"[YouTube Summary] 요약 완료\n")
        return summary_data


# 싱글톤 인스턴스
_service_instance: Optional[YoutubeSummaryService] = None


def get_youtube_summary_service() -> YoutubeSummaryService:
    """YouTube Summary Service 싱글톤 반환"""
    global _service_instance
    if _service_instance is None:
        _service_instance = YoutubeSummaryService()
    return _service_instance
