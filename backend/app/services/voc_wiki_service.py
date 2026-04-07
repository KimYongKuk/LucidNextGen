# -*- coding: utf-8 -*-
"""
IT VOC → L&F Wiki 자동 축적 서비스

IT VOC DB(v_works_app_934_data)에서 해결 사례를 조회하여
L&F Wiki "L&F IT 지식베이스" 컬렉션에 시스템별/주제별 문서로 축적합니다.

아키텍처:
  1. asyncpg로 VOC DB 조회
  2. Haiku LLM으로 시스템/주제 분류 (DB 시스템 컬럼은 hint)
  3. Haiku LLM으로 기존 문서와 신규 건 병합
  4. Outline HTTP API로 문서 생성/업데이트
"""
import os
import json
import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Optional
from collections import defaultdict

import httpx
import asyncpg

from app.core.database import get_database_connection
from app.services.bedrock_service import BedrockService

logger = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────
OUTLINE_API_URL = os.environ.get("OUTLINE_API_URL", "http://192.168.90.30:3003/api")
OUTLINE_API_KEY = os.environ.get("OUTLINE_API_KEY", "")

# VOC DB (IT VOC MCP 서버와 동일)
VOC_DATABASE_URL = "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"

# 배치 설정
CLASSIFY_BATCH_SIZE = 20  # LLM 분류 시 한번에 처리할 건수
MERGE_MAX_TOKENS = 4000   # 병합 LLM 최대 출력 토큰
OUTLINE_REQUEST_TIMEOUT = 30

# 동기 DB 호출을 이벤트 루프 밖에서 실행하기 위한 executor
_db_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="voc_wiki")


# ── LLM 프롬프트 ──────────────────────────────────────

CLASSIFY_PROMPT = """당신은 IT 지원 사례를 분류하는 전문가입니다.

아래 IT VOC(지원 요청 해결 사례) 목록을 읽고, 각 건을 **시스템**과 **주제**로 분류하세요.

## 분류 규칙
1. **시스템**: 실제 내용을 기반으로 판단하세요. DB의 시스템 컬럼은 참고만 합니다.
   - 예: DB에 "기타"로 되어 있어도 내용이 LFON 관련이면 "LFON"으로 분류
   - 반드시 아래 정규화 목록의 시스템명을 사용하세요:
     SAP, LFON, DLP, DRM, 네트워크, SW, HW, HR, EHS, 데이터서버(NAS), 보안, MDM, AD, MES, VPN, 기타
   - "하드웨어"→"HW", "Microsoft Office"→"SW", "데이터서버"→"데이터서버(NAS)", "보안성 검토"→"보안"
2. **주제**: 같은 시스템 내에서 유사한 문제를 묶는 소분류입니다.
   - 간결하고 명확한 한국어 명사구 (예: "로그인/권한 문제", "프린터 장애")
   - 기존 주제가 있으면 최대한 기존 주제에 배정하세요 (새 주제 난립 방지)
   - 유사한 주제를 난립시키지 마세요 (예: "로그인/권한 문제"와 "로그인/인증 문제"는 하나로)
3. 하나의 VOC는 반드시 하나의 시스템+주제에만 배정

## 기존 시스템/주제 목록 (있으면 우선 사용)
{existing_topics}

## VOC 목록
{entries}

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
```json
[
  {{"index": 0, "system": "SAP", "topic": "로그인/권한 문제"}},
  {{"index": 1, "system": "네트워크", "topic": "VPN 접속 장애"}}
]
```"""

MERGE_PROMPT = """당신은 IT 지식베이스 문서 편집자입니다.

기존 위키 문서에 새로운 IT VOC(지원 해결 사례)를 통합하세요.

## 편집 규칙
1. **중복 제거**: 동일 증상+해결 방법이면 참고 날짜만 추가
2. **신규 추가**: 새로운 증상/해결법이면 적절한 위치에 H3 섹션 추가
3. **내용 보강**: 기존 설명이 부실하면 조치내역을 바탕으로 보완
4. **포맷 유지**: 아래 문서 구조를 따르세요
5. **개인정보 제외**: 요청자/담당자 이름은 포함하지 않음

## 문서 구조
```markdown
# [시스템명] - [주제명]

> N건의 사례 기반 | 최종 업데이트: YYYY-MM-DD

## 주요 증상 및 해결 방법

### [증상/이슈 제목]
- **증상**: 구체적 에러 메시지나 현상
- **원인**: 파악된 원인 (있으면)
- **조치**: 해결 방법 단계별 설명
- **참고 사례**: YYYY-MM-DD, YYYY-MM-DD
```

## 기존 문서 내용
{existing_content}

## 새로 추가할 VOC 건
{new_entries}

## 지시사항
위 규칙에 따라 통합된 마크다운 문서 전체를 출력하세요. 마크다운만 출력하고 다른 설명은 하지 마세요."""

NEW_DOC_PROMPT = """당신은 IT 지식베이스 문서 편집자입니다.

아래 IT VOC(지원 해결 사례)를 바탕으로 새로운 위키 문서를 작성하세요.

## 문서 구조
```markdown
# [시스템명] - [주제명]

> N건의 사례 기반 | 최종 업데이트: YYYY-MM-DD

## 주요 증상 및 해결 방법

### [증상/이슈 제목]
- **증상**: 구체적 에러 메시지나 현상
- **원인**: 파악된 원인 (있으면)
- **조치**: 해결 방법 단계별 설명
- **참고 사례**: YYYY-MM-DD
```

## 규칙
1. 유사한 증상은 하나의 H3 섹션으로 묶기
2. 개인정보(요청자/담당자 이름) 제외
3. 조치내역을 기반으로 실용적인 해결 가이드 작성
4. 마크다운만 출력, 다른 설명 없이

## VOC 건
시스템: {system}
주제: {topic}

{entries}"""

TOC_TEMPLATE = """# {system_name} 지원 사례 모음

> 최종 업데이트: {date} | 총 {total_count}건

## 목차

| 주제 | 최종 업데이트 |
|------|--------------|
{rows}
"""


class VocWikiService:
    """IT VOC → L&F Wiki 동기화 서비스"""

    def __init__(self):
        self.bedrock = BedrockService()
        self._voc_pool: Optional[asyncpg.Pool] = None
        self._sync_lock = asyncio.Lock()  # 동시 실행 방지

    async def _call_haiku_safe(self, **kwargs) -> str:
        """generate_text_haiku 래퍼 — boto3 동기 호출을 executor로 격리"""
        loop = asyncio.get_event_loop()

        def _sync_call():
            """동기 컨텍스트에서 boto3 직접 호출"""
            import json as _json
            bedrock = self.bedrock
            haiku_model_id = os.getenv(
                "BEDROCK_FALLBACK_MODEL_ID",
                "us.anthropic.claude-haiku-4-5-20251001-v1:0"
            )
            effective_model_id = bedrock._get_model_id(haiku_model_id)

            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": kwargs.get("max_tokens", 1000),
                "temperature": kwargs.get("temperature", 0.3),
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": kwargs["prompt"]}]}
                ]
            }

            logger.info(f"[VOC Wiki] Calling Haiku: {effective_model_id}")
            response = bedrock.client.invoke_model(
                modelId=effective_model_id,
                body=_json.dumps(request_body)
            )
            response_body = _json.loads(response['body'].read())

            if 'content' in response_body and len(response_body['content']) > 0:
                return response_body['content'][0]['text']
            return ""

        return await loop.run_in_executor(_db_executor, _sync_call)

    # ── VOC DB ────────────────────────────────────────

    async def _get_voc_pool(self) -> asyncpg.Pool:
        """VOC PostgreSQL 연결 풀 (싱글톤)"""
        if self._voc_pool is None:
            self._voc_pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    VOC_DATABASE_URL,
                    min_size=1,
                    max_size=5,
                    command_timeout=30,
                ),
                timeout=15,  # 15초 내 연결 못하면 포기
            )
            logger.info("[VOC Wiki] PostgreSQL pool created")
        return self._voc_pool

    async def fetch_new_voc(self, since: date) -> list[dict]:
        """지정 날짜 이후의 해결된 VOC 건 조회"""
        pool = await self._get_voc_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 요약, 요청상세, 조치내역, 시스템, created_at
                FROM v_works_app_934_data
                WHERE 조치내역 IS NOT NULL
                  AND created_at >= $1::date
                ORDER BY created_at
                """,
                since,
            )
        entries = []
        for r in rows:
            entries.append({
                "summary": r["요약"] or "",
                "detail": r["요청상세"] or "",
                "resolution": r["조치내역"] or "",
                "system_hint": r["시스템"] or "",
                "created_at": str(r["created_at"])[:10] if r["created_at"] else "",
            })
        logger.info(f"[VOC Wiki] Fetched {len(entries)} VOC entries since {since}")
        return entries

    # ── Outline API ───────────────────────────────────

    async def _outline_request(self, endpoint: str, payload: dict) -> dict:
        """Outline API POST 요청"""
        if not OUTLINE_API_KEY:
            return {"error": "OUTLINE_API_KEY가 설정되지 않았습니다."}

        url = f"{OUTLINE_API_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {OUTLINE_API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=OUTLINE_REQUEST_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Outline API 오류 ({e.response.status_code}): {e.response.text[:500]}"}
        except httpx.ConnectError:
            return {"error": f"Outline 서버 연결 실패: {url}"}
        except Exception as e:
            return {"error": f"요청 실패: {str(e)[:300]}"}

    async def _get_collection_tree(self, collection_id: str) -> list[dict]:
        """컬렉션 문서 트리 조회 → 플랫 리스트 반환"""
        result = await self._outline_request("collections.documents", {"id": collection_id})
        if "error" in result:
            logger.error(f"[VOC Wiki] Collection tree error: {result['error']}")
            return []

        nodes = result.get("data", [])
        flat = []

        def flatten(items, depth=0, parent_id=None):
            for node in items:
                flat.append({
                    "id": node.get("id"),
                    "title": node.get("title"),
                    "url": node.get("url"),
                    "depth": depth,
                    "parent_id": parent_id,
                })
                for child in node.get("children", []):
                    flatten([child], depth + 1, node.get("id"))

        flatten(nodes)
        return flat

    async def _get_document_content(self, doc_id: str) -> str:
        """문서 본문 마크다운 조회"""
        result = await self._outline_request("documents.info", {"id": doc_id})
        if "error" in result:
            logger.error(f"[VOC Wiki] Get document error: {result['error']}")
            return ""
        return result.get("data", {}).get("text", "")

    async def _create_document(self, title: str, text: str, collection_id: str,
                               parent_document_id: str = "") -> Optional[str]:
        """문서 생성, 생성된 doc_id 반환"""
        payload = {
            "title": title,
            "text": text,
            "collectionId": collection_id,
            "publish": True,
        }
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id

        result = await self._outline_request("documents.create", payload)
        if "error" in result:
            logger.error(f"[VOC Wiki] Create document error: {result['error']}")
            return None
        doc_id = result.get("data", {}).get("id")
        logger.info(f"[VOC Wiki] Created document: {title} ({doc_id})")
        return doc_id

    async def _update_document(self, doc_id: str, text: str, title: str = "") -> bool:
        """문서 내용 업데이트"""
        payload = {"id": doc_id, "text": text, "append": False}
        if title:
            payload["title"] = title
        result = await self._outline_request("documents.update", payload)
        if "error" in result:
            logger.error(f"[VOC Wiki] Update document error: {result['error']}")
            return False
        logger.info(f"[VOC Wiki] Updated document: {doc_id}")
        return True

    # ── LLM 분류 ──────────────────────────────────────

    async def classify_entries(
        self, entries: list[dict], existing_topics: dict[str, list[str]]
    ) -> list[dict]:
        """
        VOC 건들을 시스템/주제로 분류

        Args:
            entries: VOC 건 리스트
            existing_topics: {"SAP": ["로그인/권한", "트랜잭션 오류"], ...}

        Returns:
            [{"index": 0, "system": "SAP", "topic": "로그인/권한"}, ...]
        """
        # 기존 주제 목록 포맷팅
        if existing_topics:
            topics_str = "\n".join(
                f"- {sys}: {', '.join(topics)}"
                for sys, topics in existing_topics.items()
            )
        else:
            topics_str = "(아직 없음 — 자유롭게 생성)"

        all_classifications = []

        # 배치 단위 처리
        for batch_start in range(0, len(entries), CLASSIFY_BATCH_SIZE):
            batch = entries[batch_start:batch_start + CLASSIFY_BATCH_SIZE]

            # 엔트리 포맷팅
            entries_str = ""
            for i, e in enumerate(batch):
                global_idx = batch_start + i
                entries_str += (
                    f"\n[{global_idx}] 시스템(DB): {e['system_hint']}\n"
                    f"  요약: {e['summary']}\n"
                    f"  요청상세: {e['detail'][:200]}\n"
                    f"  조치내역: {e['resolution'][:200]}\n"
                    f"  날짜: {e['created_at']}\n"
                )

            prompt = CLASSIFY_PROMPT.format(
                existing_topics=topics_str,
                entries=entries_str,
            )

            try:
                response = await self._call_haiku_safe(
                    prompt=prompt,
                    max_tokens=2000,
                    temperature=0.1,
                )

                # JSON 파싱 (```json ... ``` 블록 추출)
                json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(1))
                else:
                    parsed = json.loads(response.strip())

                all_classifications.extend(parsed)

            except Exception as e:
                logger.error(f"[VOC Wiki] Classification batch {batch_start} failed: {e}")
                # 실패 시 DB 시스템 컬럼 + "미분류"로 폴백
                for i, entry in enumerate(batch):
                    all_classifications.append({
                        "index": batch_start + i,
                        "system": entry["system_hint"] or "기타",
                        "topic": "미분류",
                    })

        return all_classifications

    # ── LLM 병합 ──────────────────────────────────────

    async def merge_into_document(
        self, existing_content: str, new_entries: list[dict],
        system: str, topic: str,
    ) -> str:
        """기존 문서 내용에 신규 VOC 건을 병합"""
        entries_str = self._format_entries_for_merge(new_entries)
        today_str = date.today().strftime("%Y-%m-%d")

        if existing_content.strip():
            prompt = MERGE_PROMPT.format(
                existing_content=existing_content,
                new_entries=entries_str,
            )
        else:
            prompt = NEW_DOC_PROMPT.format(
                system=system,
                topic=topic,
                entries=entries_str,
            )

        try:
            result = await self._call_haiku_safe(
                prompt=prompt,
                max_tokens=MERGE_MAX_TOKENS,
                temperature=0.2,
            )
            # 마크다운 코드블록 제거 (LLM이 감싸는 경우)
            result = re.sub(r"^```markdown\s*\n?", "", result.strip())
            result = re.sub(r"\n?```\s*$", "", result.strip())
            return result
        except Exception as e:
            logger.error(f"[VOC Wiki] Merge failed for {system}/{topic}: {e}")
            # 실패 시 신규 건만 append
            return existing_content + f"\n\n---\n\n## 자동 추가 ({today_str})\n\n{entries_str}"

    def _format_entries_for_merge(self, entries: list[dict]) -> str:
        """VOC 건들을 LLM 입력용 텍스트로 포맷"""
        parts = []
        for e in entries:
            parts.append(
                f"- 요약: {e['summary']}\n"
                f"  요청상세: {e['detail']}\n"
                f"  조치내역: {e['resolution']}\n"
                f"  날짜: {e['created_at']}"
            )
        return "\n\n".join(parts)

    # ── 문서 구조 관리 ────────────────────────────────

    async def _get_existing_topics(self, collection_id: str) -> dict[str, list[str]]:
        """현재 위키의 시스템/주제 구조 파악"""
        tree = await self._get_collection_tree(collection_id)
        topics: dict[str, list[str]] = {}

        # depth=0 → 시스템 문서, depth=1 → 주제 문서
        system_map = {}
        for node in tree:
            if node["depth"] == 0:
                # "SAP 지원 사례 모음" → "SAP"
                system_name = node["title"].replace(" 지원 사례 모음", "").strip()
                system_map[node["id"]] = system_name
                topics[system_name] = []
            elif node["depth"] == 1 and node.get("parent_id") in system_map:
                parent_system = system_map[node["parent_id"]]
                # "SAP - 로그인/권한 문제" → "로그인/권한 문제"
                topic_title = node["title"]
                if " - " in topic_title:
                    topic_title = topic_title.split(" - ", 1)[1]
                topics[parent_system].append(topic_title)

        return topics

    async def _find_system_doc(self, tree: list[dict], system: str) -> Optional[str]:
        """시스템별 부모 문서 ID 찾기"""
        target_title = f"{system} 지원 사례 모음"
        for node in tree:
            if node["depth"] == 0 and node["title"] == target_title:
                return node["id"]
        return None

    async def _find_topic_doc(self, tree: list[dict], parent_id: str,
                              system: str, topic: str) -> Optional[str]:
        """주제별 자식 문서 ID 찾기"""
        target_title = f"{system} - {topic}"
        for node in tree:
            if node["depth"] == 1 and node.get("parent_id") == parent_id and node["title"] == target_title:
                return node["id"]
        return None

    async def _get_document_updated_at(self, doc_id: str) -> str:
        """문서의 updatedAt 날짜(YYYY-MM-DD) 조회"""
        result = await self._outline_request("documents.info", {"id": doc_id})
        if "error" in result:
            return "-"
        updated_at = result.get("data", {}).get("updatedAt", "")
        if updated_at:
            # ISO 8601 "2026-04-07T08:15:35.000Z" → "2026-04-07"
            return updated_at[:10]
        return "-"

    async def _update_system_toc(self, system_doc_id: str, collection_id: str,
                                 system_name: str) -> None:
        """시스템 부모 문서의 목차 갱신"""
        tree = await self._get_collection_tree(collection_id)

        # 자식 문서 수집
        children = [n for n in tree if n.get("parent_id") == system_doc_id and n["depth"] == 1]
        if not children:
            return

        # 각 자식 문서의 updatedAt 병렬 조회
        update_dates = await asyncio.gather(
            *[self._get_document_updated_at(child["id"]) for child in children]
        )

        rows = ""
        for child, updated_date in zip(children, update_dates):
            topic_title = child["title"]
            if " - " in topic_title:
                topic_title = topic_title.split(" - ", 1)[1]
            doc_url = child.get("url", "")
            rows += f"| [{topic_title}]({doc_url}) | {updated_date} |\n"

        today_str = date.today().strftime("%Y-%m-%d")
        toc_md = TOC_TEMPLATE.format(
            system_name=system_name,
            date=today_str,
            total_count=len(children),
            rows=rows,
        )

        await self._update_document(system_doc_id, toc_md)

    # ── 동기화 상태 관리 (MySQL) ──────────────────────

    def _get_last_sync_date_sync(self) -> Optional[date]:
        """마지막 성공 동기화 날짜 조회 (동기, executor에서 실행)"""
        db = get_database_connection()
        with db.get_cursor() as cursor:
            cursor.execute(
                "SELECT MAX(sync_date) as last_date FROM voc_wiki_sync_log WHERE status = 'success'"
            )
            row = cursor.fetchone()
            if row and row.get("last_date"):
                return row["last_date"]
        return None

    async def _get_last_sync_date(self) -> Optional[date]:
        """마지막 성공 동기화 날짜 조회 (이벤트 루프 블로킹 방지)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_db_executor, self._get_last_sync_date_sync)

    def _save_sync_log_sync(self, sync_date: date, voc_count: int,
                            docs_created: int, docs_updated: int,
                            status: str = "success", error_message: str = "") -> None:
        """동기화 결과 기록 (동기, executor에서 실행)"""
        db = get_database_connection()
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO voc_wiki_sync_log
                    (sync_date, voc_count, docs_created, docs_updated, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (sync_date, voc_count, docs_created, docs_updated, status, error_message),
            )

    async def _save_sync_log(self, sync_date: date, voc_count: int,
                             docs_created: int, docs_updated: int,
                             status: str = "success", error_message: str = "") -> None:
        """동기화 결과 기록 (이벤트 루프 블로킹 방지)"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            _db_executor,
            self._save_sync_log_sync,
            sync_date, voc_count, docs_created, docs_updated, status, error_message,
        )

    # ── 메인 오케스트레이션 ───────────────────────────

    async def sync(self, collection_id: str, since: Optional[date] = None) -> dict:
        """
        VOC → 위키 동기화 실행

        Args:
            collection_id: Outline 컬렉션 ID
            since: 조회 시작일 (None이면 마지막 동기화 이후)

        Returns:
            {"success": bool, "voc_count": int, "created": int, "updated": int}
        """
        if self._sync_lock.locked():
            logger.warning("[VOC Wiki] Sync already in progress, skipping")
            return {"success": False, "error": "동기화가 이미 진행 중입니다."}

        async with self._sync_lock:
            return await self._sync_inner(collection_id, since)

    async def _sync_inner(self, collection_id: str, since: Optional[date] = None) -> dict:
        """실제 동기화 로직 (락 내부에서 실행)"""
        today = date.today()
        today_str = today.strftime("%Y-%m-%d")
        docs_created = 0
        docs_updated = 0

        try:
            # 1. 조회 시작일 결정
            #    - 1일 오버랩: 마지막 동기화 당일부터 재조회 (중간 크래시/누락 방지)
            #    - LLM 병합 시 중복은 자동 제거됨 ("동일 증상+해결 → 참고 날짜만 추가")
            if since is None:
                since = await self._get_last_sync_date()
                if since is None:
                    since = today - timedelta(days=30)
                # else: since 그대로 사용 (오버랩 1일, 누락 방지)

            logger.info(f"[VOC Wiki] Sync starting: {since} ~ {today_str}")

            # 2. VOC 조회
            entries = await self.fetch_new_voc(since)
            if not entries:
                logger.info("[VOC Wiki] No new VOC entries, skipping")
                await self._save_sync_log(today, 0, 0, 0)
                return {"success": True, "voc_count": 0, "created": 0, "updated": 0}

            # 3. 기존 문서 구조 파악
            existing_topics = await self._get_existing_topics(collection_id)
            tree = await self._get_collection_tree(collection_id)

            # 4. LLM 분류
            classifications = await self.classify_entries(entries, existing_topics)

            # 5. 시스템/주제별 그룹핑
            grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
            for cls in classifications:
                idx = cls["index"]
                if 0 <= idx < len(entries):
                    system = cls["system"]
                    topic = cls["topic"]
                    grouped[system][topic].append(entries[idx])

            # 6. 시스템/주제별 문서 처리
            updated_systems = set()

            for system, topics in grouped.items():
                # 6a. 시스템 부모 문서 확보
                system_doc_id = await self._find_system_doc(tree, system)
                if not system_doc_id:
                    # 부모 문서 생성
                    toc_md = TOC_TEMPLATE.format(
                        system_name=system,
                        date=today_str,
                        total_count=0,
                        rows="",
                    )
                    system_doc_id = await self._create_document(
                        f"{system} 지원 사례 모음", toc_md, collection_id
                    )
                    if not system_doc_id:
                        logger.error(f"[VOC Wiki] Failed to create system doc: {system}")
                        continue
                    docs_created += 1
                    # 트리 재조회 (새 문서 반영)
                    tree = await self._get_collection_tree(collection_id)

                updated_systems.add(system_doc_id)

                for topic, topic_entries in topics.items():
                    # 6b. 주제 자식 문서 확보
                    topic_doc_id = await self._find_topic_doc(tree, system_doc_id, system, topic)

                    if topic_doc_id:
                        # 기존 문서 → 병합
                        existing_content = await self._get_document_content(topic_doc_id)
                        merged_md = await self.merge_into_document(
                            existing_content, topic_entries, system, topic
                        )
                        await self._update_document(topic_doc_id, merged_md)
                        docs_updated += 1
                    else:
                        # 신규 문서 생성
                        new_md = await self.merge_into_document(
                            "", topic_entries, system, topic
                        )
                        doc_title = f"{system} - {topic}"
                        new_id = await self._create_document(
                            doc_title, new_md, collection_id, system_doc_id
                        )
                        if new_id:
                            docs_created += 1
                        # 트리 재조회
                        tree = await self._get_collection_tree(collection_id)

                    # API 부하 분산
                    await asyncio.sleep(0.5)

            # 7. 변경된 시스템 목차 갱신
            for sys_doc_id in updated_systems:
                # 시스템 이름 역추출
                for node in tree:
                    if node["id"] == sys_doc_id:
                        sys_name = node["title"].replace(" 지원 사례 모음", "").strip()
                        await self._update_system_toc(sys_doc_id, collection_id, sys_name)
                        break

            # 8. 동기화 로그 저장
            await self._save_sync_log(today, len(entries), docs_created, docs_updated)

            result = {
                "success": True,
                "voc_count": len(entries),
                "created": docs_created,
                "updated": docs_updated,
                "since": str(since),
            }
            logger.info(f"[VOC Wiki] Sync completed: {result}")
            return result

        except Exception as e:
            logger.error(f"[VOC Wiki] Sync failed: {e}", exc_info=True)
            await self._save_sync_log(today, 0, docs_created, docs_updated, "failed", str(e)[:500])
            return {"success": False, "error": str(e)}

    async def close(self):
        """리소스 정리"""
        if self._voc_pool:
            await self._voc_pool.close()
            logger.info("[VOC Wiki] PostgreSQL pool closed")


# 싱글톤
_voc_wiki_service: Optional[VocWikiService] = None


def get_voc_wiki_service() -> VocWikiService:
    global _voc_wiki_service
    if _voc_wiki_service is None:
        _voc_wiki_service = VocWikiService()
    return _voc_wiki_service
