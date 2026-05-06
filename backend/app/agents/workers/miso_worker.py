"""MISO Worker — 등록된 MISO Agent/Workflow를 호출하는 어댑터.

설계: docs/agent-hub/03_manifest_spec.md (runtime: miso)
- 매니페스트마다 별도 인스턴스 (endpoint/api_key/mode 보유)
- chat → POST /ext/v1/chat (query + conversation_id 지원)
- workflow → POST /ext/v1/workflows/run (inputs only)

BaseWorker 상속 안 함 — Bedrock/도구 사용 안 하고 외부 HTTP 호출만.
인터페이스: stream_response(messages, context, ...) → AsyncIterator[Dict]
(BaseWorker와 호환되어 orchestrator에서 통일된 호출)

Workflow input 매핑 (runtime.input_mapping):
- legacy dict 형태: `{변수명: "{{message}}"}` — 단일 텍스트만 가정 (구버전 폼)
- 신형 list 형태: `[{name, type, source}, ...]` — 타입별 처리
  - type: text | paragraph | list | number | file | files
  - source:
    - "{{message}}": 사용자 발화 그대로 (text/paragraph)
    - "{{message_lines}}": 발화를 줄바꿈으로 split → list
    - "{{message_number}}": 발화에서 숫자 추출 (number)
    - 단일 파일 (file):
      - "{{latest_file}}": 채팅창 가장 최근 업로드 파일 1개 (일회성)
      - "{{file:파일명}}": 채팅창 업로드 중 명시 파일명 매칭
      - "{{workspace_file:파일명}}": 워크스페이스 영속 파일 중 명시 파일명 매칭
    - 다중 파일 (files):
      - "{{recent_files}}": 채팅창 최근 시간 윈도우 내 업로드 파일 모두
      - "{{recent_files:N}}": 채팅창 mtime 최신 순 최대 N개
      - "{{workspace_files}}": 워크스페이스 영속 파일 모두 (cron 자동 호출에 적합)
      - "{{workspace_files:N}}": 워크스페이스 영속 파일 mtime 최신 순 N개
    - 그 외 문자열: 고정값으로 그대로 전달

context 요구사항:
- user_id: 채팅 첨부 파일 출처 (`{{latest_file}}`/`{{recent_files}}` 등)
- workspace_id: 워크스페이스 영속 파일 출처 (`{{workspace_file:..}}`/`{{workspace_files}}` 등)
"""
import os
import re
import json
import time
import logging
import uuid
from pathlib import Path as FilePath
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, AIMessageChunk

from app.core.database import get_database_connection

logger = logging.getLogger(__name__)


MISO_BASE_URL = os.getenv("MISO_API_BASE_URL", "https://api.miso.landf.co.kr")
MISO_REQUEST_TIMEOUT = int(os.getenv("MISO_REQUEST_TIMEOUT", "60"))
MISO_FILE_UPLOAD_TIMEOUT = int(os.getenv("MISO_FILE_UPLOAD_TIMEOUT", "120"))
# {{recent_files}} 토큰의 기본 시간 윈도우 (초). 기본 10분 — 사용자가 메시지 직전에 첨부한 파일을 잡기 위함.
MISO_RECENT_FILES_WINDOW_SEC = int(os.getenv("MISO_RECENT_FILES_WINDOW_SEC", "600"))
# 다중 파일 안전 상한 (한 호출에 너무 많이 업로드 방지)
MISO_RECENT_FILES_MAX = int(os.getenv("MISO_RECENT_FILES_MAX", "10"))

# 사용자 업로드 원본 경로 (ITSupportWorker와 동일 디렉토리 사용)
_USER_UPLOAD_DIR = FilePath(__file__).parent.parent.parent.parent / "data" / "user_uploads"


class FileMappingError(Exception):
    """input_mapping의 파일 처리 단계에서 발생한 에러 (사용자에게 친절한 메시지로 변환)."""
    pass


class MisoWorker:
    """MISO Agent/Workflow 호출 어댑터.

    한 인스턴스 = 한 등록된 MISO Agent. orchestrator가 매번 manifest를 받아 인스턴스화.
    """

    def __init__(
        self,
        agent_id: str,
        agent_slug: str,
        agent_name: str,
        runtime: Dict[str, Any],
    ):
        self.agent_id = agent_id
        self.agent_slug = agent_slug
        self.agent_name = agent_name
        self.runtime = runtime
        self.api_key = runtime.get("api_key")
        self.mode = runtime.get("mode")  # "chat" or "workflow"
        # endpoint 매니페스트 값(/ext/v1/chat 등)을 base와 결합
        endpoint_path = runtime.get("endpoint") or (
            "/ext/v1/chat" if self.mode == "chat" else "/ext/v1/workflows/run"
        )
        self.full_url = f"{MISO_BASE_URL.rstrip('/')}{endpoint_path}"

        if not self.api_key:
            raise ValueError(f"MisoWorker[{agent_slug}]: api_key missing in manifest.runtime")
        if self.mode not in ("chat", "workflow"):
            raise ValueError(f"MisoWorker[{agent_slug}]: invalid mode={self.mode}")

    @property
    def name(self) -> str:
        return f"MisoWorker[{self.agent_slug}]"

    # ============================================================
    # 핵심: 실행 (stream events 형식)
    # ============================================================

    async def stream_response(
        self,
        messages: List[BaseMessage],
        context: Dict[str, Any],
        all_tools: Optional[List[Any]] = None,  # MISO는 도구 직접 사용 안 함
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """MISO API 호출 + 응답을 events로 yield.

        BaseWorker.stream_response와 호환되는 형태로 events 발행.
        """
        import sys
        print(f"[MisoWorker] ENTER stream_response slug={self.agent_slug} mode={self.mode} url={self.full_url}", flush=True, file=sys.stderr)
        user_id = context.get("user_id", "anonymous")
        execution_id = str(uuid.uuid4())
        started_at = time.time()

        # 마지막 user message를 query로 추출
        query = self._extract_query(messages)
        if not query:
            yield self._error_event("사용자 발화를 찾지 못했습니다.")
            await self._record_execution(
                execution_id, user_id, context, "failed",
                error_message="empty query", started_at=started_at,
            )
            return

        # 시작 이벤트
        yield {
            "event": "miso_call_start",
            "agent_slug": self.agent_slug,
            "agent_name": self.agent_name,
            "mode": self.mode,
            "endpoint": self.full_url,
        }

        # MISO 호출 (blocking 모드 — 단순화. SSE는 후속)
        import sys
        workspace_id = context.get("workspace_id")
        try:
            request_body = await self._build_request_body(
                query, user_id, messages, workspace_id=workspace_id,
            )
        except FileMappingError as e:
            yield self._error_event(str(e))
            await self._record_execution(
                execution_id, user_id, context, "failed",
                error_message=str(e)[:500], started_at=started_at,
            )
            return
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        print(f"[MisoWorker] POST {self.full_url} body_keys={list(request_body.keys())} inputs_keys={list(request_body.get('inputs', {}).keys())} key={self.api_key[:10]}...", flush=True, file=sys.stderr)

        try:
            async with httpx.AsyncClient(timeout=MISO_REQUEST_TIMEOUT) as client:
                resp = await client.post(self.full_url, headers=headers, json=request_body)
            print(f"[MisoWorker] response status={resp.status_code} bytes={len(resp.text)}", flush=True, file=sys.stderr)
        except httpx.TimeoutException:
            yield self._error_event(f"MISO 응답 시간 초과 ({MISO_REQUEST_TIMEOUT}초)")
            await self._record_execution(
                execution_id, user_id, context, "timeout",
                error_message="MISO API timeout", started_at=started_at,
            )
            return
        except Exception as e:
            yield self._error_event(f"MISO 호출 실패: {type(e).__name__}: {e}")
            await self._record_execution(
                execution_id, user_id, context, "failed",
                error_message=str(e)[:500], started_at=started_at,
            )
            return

        # 응답 처리
        if resp.status_code != 200:
            body_text = (resp.text or "")[:300]
            # invalid_param인 경우 원인 추정 (Workflow inputs 미정의)
            hint = ""
            if self.mode == "workflow" and "invalid_param" in body_text:
                hint = (
                    "\n\n💡 **워크플로우 입력 변수 매핑이 필요합니다.** "
                    "MISO Studio에서 이 워크플로우의 시작 노드 입력 변수(이름·타입)를 확인한 뒤, "
                    "Agent 등록 폼의 '워크플로우 입력 변수 매핑' 섹션에서 변수명/타입/소스를 모두 등록해주세요. "
                    "(예: `user_query` 텍스트 + `사용자 발화 그대로`)"
                )
            yield self._error_event(
                f"MISO 응답 오류 (HTTP {resp.status_code}): {body_text}{hint}"
            )
            await self._record_execution(
                execution_id, user_id, context, "failed",
                error_message=f"HTTP {resp.status_code}: {resp.text[:300]}",
                started_at=started_at,
            )
            return

        try:
            data = resp.json()
        except Exception:
            yield self._error_event("MISO 응답 JSON 파싱 실패")
            await self._record_execution(
                execution_id, user_id, context, "failed",
                error_message="JSON parse error", started_at=started_at,
            )
            return

        print(f"[MisoWorker] response keys={list(data.keys()) if isinstance(data, dict) else type(data)} body_preview={json.dumps(data, ensure_ascii=False)[:500]}", flush=True, file=sys.stderr)
        # Workflow nested data 구조 진단
        if self.mode == "workflow" and isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                print(f"[MisoWorker] data.data keys={list(inner.keys())} outputs_type={type(inner.get('outputs')).__name__} outputs_preview={json.dumps(inner.get('outputs'), ensure_ascii=False)[:300]}", flush=True, file=sys.stderr)

        # mode별 응답 추출
        answer_text = self._extract_answer(data)
        print(f"[MisoWorker] extracted answer_text len={len(answer_text)} preview={answer_text[:200]!r}", flush=True, file=sys.stderr)

        # 텍스트 chunk 이벤트 (UI 스트리밍 호환)
        # chat.py가 hasattr(chunk, "content")로 체크 → AIMessageChunk 객체 사용 (dict 아님)
        # 더 자연스러운 streaming UX 위해 일정 크기로 분할 yield
        print(f"[MisoWorker] yielding answer ({len(answer_text)} chars) in chunks", flush=True, file=sys.stderr)
        CHUNK_SIZE = 80
        for i in range(0, len(answer_text), CHUNK_SIZE):
            piece = answer_text[i : i + CHUNK_SIZE]
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content=piece)},
            }
        print(f"[MisoWorker] yield complete", flush=True, file=sys.stderr)

        # 종료 이벤트
        yield {
            "event": "miso_call_complete",
            "agent_slug": self.agent_slug,
            "elapsed_ms": int((time.time() - started_at) * 1000),
            "miso_response_id": data.get("id") or data.get("workflow_run_id"),
        }

        await self._record_execution(
            execution_id, user_id, context, "success",
            output_summary=answer_text[:1000],
            started_at=started_at,
        )

    # ============================================================
    # Helpers
    # ============================================================

    def _extract_query(self, messages: List[BaseMessage]) -> str:
        """마지막 HumanMessage의 content 추출 + 명시적 호출 prefix 제거."""
        raw = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    raw = content
                elif isinstance(content, list):
                    raw = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                break
        if not raw:
            return ""
        # @slug 또는 /use slug prefix 제거 (명시 호출 시 매칭만 위함, 본문은 prefix 없이)
        cleaned = raw.lstrip()
        prefixes = [f"@{self.agent_slug}", f"/use {self.agent_slug}"]
        for p in prefixes:
            if cleaned.startswith(p):
                cleaned = cleaned[len(p):].lstrip()
                break
        return cleaned or raw

    async def _build_request_body(
        self,
        query: str,
        user_id: str,
        messages: List[BaseMessage],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MISO API request body 구성. 파일 매핑 시 MISO 업로드 호출이 필요해 async."""
        body = {
            "inputs": {},
            "mode": "blocking",
            "user": user_id or "lucid-hub-user",
        }
        if self.mode == "chat":
            body["query"] = query
            body["conversation_id"] = ""
            body["auto_gen_name"] = False
            return body

        # workflow
        input_mapping = self.runtime.get("input_mapping")

        # 1) 신형 list 형태 (multi-row, type-aware)
        if isinstance(input_mapping, list) and input_mapping:
            inputs: Dict[str, Any] = {}
            for row in input_mapping:
                if not isinstance(row, dict):
                    continue
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                vtype = (row.get("type") or "text").strip().lower()
                source = row.get("source")
                inputs[name] = await self._resolve_mapped_value(
                    vtype=vtype, source=source, query=query,
                    user_id=user_id, workspace_id=workspace_id, var_name=name,
                )
            body["inputs"] = inputs
            return body

        # 2) legacy dict 형태 (단일 텍스트)
        if isinstance(input_mapping, dict) and input_mapping:
            inputs = {}
            for k, v in input_mapping.items():
                if isinstance(v, str) and v.strip() == "{{message}}":
                    inputs[k] = query
                else:
                    inputs[k] = v
            body["inputs"] = inputs
            return body

        # 3) 매핑 미정의 → best-effort
        body["inputs"] = {
            "query": query, "input": query, "text": query,
            "message": query, "prompt": query, "user_input": query,
        }
        return body

    async def _resolve_mapped_value(
        self, *, vtype: str, source: Any, query: str,
        user_id: str, workspace_id: Optional[str], var_name: str,
    ) -> Any:
        """input_mapping 행 1개를 실제 값으로 치환.

        파일 토큰 출처는 명시적으로 분리:
        - {{latest_file}}/{{recent_files}}: 채팅창 첨부 (user_uploads, 일회성)
        - {{workspace_file:..}}/{{workspace_files}}: 워크스페이스 영속 파일 (cron에도 사용 가능)
        """
        # 고정값 (템플릿 토큰 아님)
        if not isinstance(source, str):
            return source

        token = source.strip()

        # 텍스트/문단
        if vtype in ("text", "paragraph", "string"):
            return query if token == "{{message}}" else token

        # 목록 (string array) — MISO list 변수가 array를 받는다고 가정
        if vtype == "list":
            if token == "{{message_lines}}":
                lines = [ln.strip() for ln in (query or "").splitlines() if ln.strip()]
                return lines or [query] if query else []
            if token == "{{message}}":
                return [query] if query else []
            return [token]

        # 숫자
        if vtype == "number":
            if token in ("{{message}}", "{{message_number}}"):
                m = re.search(r"-?\d+(?:\.\d+)?", query or "")
                if not m:
                    raise FileMappingError(
                        f"워크플로우 변수 '{var_name}'이 숫자를 요구하지만 발화에서 숫자를 찾지 못했습니다."
                    )
                num_str = m.group()
                return float(num_str) if "." in num_str else int(num_str)
            # 고정값 — 숫자 변환 시도
            try:
                return float(token) if "." in token else int(token)
            except ValueError:
                return token

        # 단일 파일
        if vtype == "file":
            # 1) 채팅 첨부 — 가장 최근 업로드 파일
            if token == "{{latest_file}}":
                latest = self._find_latest_user_file(user_id)
                if not latest:
                    raise FileMappingError(
                        f"워크플로우 변수 '{var_name}'에 사용할 업로드 파일이 없습니다. "
                        "채팅창에 파일을 먼저 첨부해주세요."
                    )
                return await self._upload_and_make_ref(latest, user_id)
            # 2) 채팅 첨부 — 명시 파일명
            if token.startswith("{{file:") and token.endswith("}}"):
                fname = token[len("{{file:"):-2].strip()
                path = self._resolve_user_file_by_name(user_id, fname)
                if not path:
                    raise FileMappingError(
                        f"워크플로우 변수 '{var_name}'에 지정한 파일 '{fname}'을 찾을 수 없습니다."
                    )
                return await self._upload_and_make_ref(path, user_id)
            # 3) 워크스페이스 영속 파일 — 명시 파일명
            if token.startswith("{{workspace_file:") and token.endswith("}}"):
                fname = token[len("{{workspace_file:"):-2].strip()
                path = self._resolve_workspace_file_by_name(workspace_id, fname)
                if not path:
                    raise FileMappingError(
                        f"워크플로우 변수 '{var_name}'에 지정한 워크스페이스 파일 '{fname}'을 찾을 수 없습니다."
                    )
                return await self._upload_and_make_ref(path, user_id)
            # 파일 타입에 일반 문자열 → 의미 없으므로 그대로 반환 (MISO가 거부할 가능성 높음)
            return token

        # 다중 파일 (Array[File])
        if vtype == "files":
            paths: List[FilePath] = []
            source_label = "채팅 첨부"  # 에러 메시지용
            # 채팅 첨부 — 시간 윈도우 / N개
            if token == "{{recent_files}}":
                paths = self._find_recent_user_files(
                    user_id,
                    window_sec=MISO_RECENT_FILES_WINDOW_SEC,
                    max_count=MISO_RECENT_FILES_MAX,
                )
            elif token.startswith("{{recent_files:") and token.endswith("}}"):
                count_str = token[len("{{recent_files:"):-2].strip()
                try:
                    n = max(1, min(MISO_RECENT_FILES_MAX, int(count_str)))
                except ValueError:
                    raise FileMappingError(
                        f"워크플로우 변수 '{var_name}'의 매핑 토큰 '{token}'의 N 값이 숫자가 아닙니다."
                    )
                paths = self._find_recent_user_files(user_id, window_sec=None, max_count=n)
            # 워크스페이스 영속 파일 — 모두 / N개
            elif token == "{{workspace_files}}":
                source_label = "워크스페이스 영속"
                paths = self._find_workspace_files(workspace_id, max_count=MISO_RECENT_FILES_MAX)
            elif token.startswith("{{workspace_files:") and token.endswith("}}"):
                source_label = "워크스페이스 영속"
                count_str = token[len("{{workspace_files:"):-2].strip()
                try:
                    n = max(1, min(MISO_RECENT_FILES_MAX, int(count_str)))
                except ValueError:
                    raise FileMappingError(
                        f"워크플로우 변수 '{var_name}'의 매핑 토큰 '{token}'의 N 값이 숫자가 아닙니다."
                    )
                paths = self._find_workspace_files(workspace_id, max_count=n)
            else:
                return []

            if not paths:
                if source_label == "워크스페이스 영속":
                    raise FileMappingError(
                        f"워크플로우 변수 '{var_name}'에 사용할 워크스페이스 영속 파일이 없습니다. "
                        "워크스페이스에 파일을 먼저 업로드해주세요."
                    )
                raise FileMappingError(
                    f"워크플로우 변수 '{var_name}'에 사용할 업로드 파일이 없습니다. "
                    "채팅창에 파일을 먼저 첨부해주세요."
                )

            refs: List[Dict[str, Any]] = []
            for p in paths:
                upload_id = await self._upload_file_to_miso(p, user_id)
                refs.append({
                    "transfer_method": "local_file",
                    "upload_file_id": upload_id,
                    "type": "document",
                })
            return refs

        # 알 수 없는 타입 — 안전하게 문자열로
        return query if token == "{{message}}" else token

    # ============================================================
    # 파일 매핑 헬퍼
    # ============================================================

    async def _upload_and_make_ref(self, path: FilePath, user_id: str) -> Dict[str, Any]:
        """파일을 MISO에 업로드 + workflow inputs용 file ref dict 반환."""
        upload_id = await self._upload_file_to_miso(path, user_id)
        return {
            "transfer_method": "local_file",
            "upload_file_id": upload_id,
            "type": "document",
        }

    # --- 워크스페이스 영속 파일 ---

    def _find_workspace_files(self, workspace_uuid: Optional[str], *, max_count: int = 10) -> List[FilePath]:
        """워크스페이스 영속 파일 mtime 최신 순 N개. workspace_uuid 없으면 빈 배열."""
        if not workspace_uuid:
            return []
        # workspace_service의 staticmethod 차용 (DB 조회 없음, 디스크만)
        from app.services.workspace_service import WorkspaceService
        rows = WorkspaceService.list_persisted_files_by_uuid(workspace_uuid)
        if not rows:
            return []
        rows = rows[:max_count]
        return [FilePath(r["path"]) for r in rows]

    def _resolve_workspace_file_by_name(self, workspace_uuid: Optional[str], filename: str) -> Optional[FilePath]:
        """워크스페이스 영속 파일 중 파일명 매칭 — 동명 다수 시 mtime 최신."""
        if not workspace_uuid or not filename:
            return None
        from app.services.workspace_service import WorkspaceService
        rows = WorkspaceService.list_persisted_files_by_uuid(workspace_uuid)
        target = filename.strip()
        matches = [r for r in rows if r["filename"] == target]
        if not matches:
            return None
        # rows는 이미 mtime 최신 정렬
        return FilePath(matches[0]["path"])

    # --- 채팅 첨부 (user_uploads) ---

    def _find_latest_user_file(self, user_id: str) -> Optional[FilePath]:
        """user_uploads/{date}/{user_id}/ 전체에서 가장 최근 mtime 파일 1개."""
        if not user_id or user_id == "anonymous":
            return None
        if not _USER_UPLOAD_DIR.exists():
            return None
        safe_uid = user_id.replace("/", "").replace("\\", "").replace("..", "").replace(" ", "_")
        candidates: List[Tuple[FilePath, float]] = []
        try:
            for date_dir in _USER_UPLOAD_DIR.iterdir():
                if not date_dir.is_dir():
                    continue
                user_dir = date_dir / safe_uid
                if not user_dir.is_dir():
                    continue
                for f in user_dir.iterdir():
                    if f.is_file():
                        candidates.append((f, f.stat().st_mtime))
        except Exception as e:
            logger.warning(f"[MisoWorker] user file scan failed: {e}")
            return None
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def _find_recent_user_files(
        self,
        user_id: str,
        *,
        window_sec: Optional[int] = None,
        max_count: int = 10,
    ) -> List[FilePath]:
        """user_uploads/{date}/{user_id}/ 전체에서 mtime 최신 순 파일들.

        Args:
            window_sec: 지정 시 (now - mtime) <= window_sec 인 파일만 반환. None이면 최신 N개.
            max_count: 최대 반환 개수 상한.
        """
        if not user_id or user_id == "anonymous":
            return []
        if not _USER_UPLOAD_DIR.exists():
            return []
        safe_uid = user_id.replace("/", "").replace("\\", "").replace("..", "").replace(" ", "_")
        candidates: List[Tuple[FilePath, float]] = []
        try:
            for date_dir in _USER_UPLOAD_DIR.iterdir():
                if not date_dir.is_dir():
                    continue
                user_dir = date_dir / safe_uid
                if not user_dir.is_dir():
                    continue
                for f in user_dir.iterdir():
                    if f.is_file():
                        candidates.append((f, f.stat().st_mtime))
        except Exception as e:
            logger.warning(f"[MisoWorker] recent files scan failed: {e}")
            return []
        if not candidates:
            return []
        candidates.sort(key=lambda x: x[1], reverse=True)
        if window_sec is not None:
            now = time.time()
            candidates = [(p, m) for p, m in candidates if (now - m) <= window_sec]
        return [p for p, _ in candidates[:max_count]]

    def _resolve_user_file_by_name(self, user_id: str, filename: str) -> Optional[FilePath]:
        """파일명으로 user_uploads/{date}/{user_id}/ 조회 — 가장 최근 매칭 1개."""
        if not user_id or user_id == "anonymous" or not filename:
            return None
        if not _USER_UPLOAD_DIR.exists():
            return None
        safe_uid = user_id.replace("/", "").replace("\\", "").replace("..", "").replace(" ", "_")
        target = filename.strip()
        matches: List[Tuple[FilePath, float]] = []
        try:
            for date_dir in _USER_UPLOAD_DIR.iterdir():
                if not date_dir.is_dir():
                    continue
                user_dir = date_dir / safe_uid
                if not user_dir.is_dir():
                    continue
                for f in user_dir.iterdir():
                    if f.is_file() and f.name == target:
                        matches.append((f, f.stat().st_mtime))
        except Exception as e:
            logger.warning(f"[MisoWorker] file resolve failed: {e}")
            return None
        if not matches:
            return None
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0]

    async def _upload_file_to_miso(self, file_path: FilePath, user_id: str) -> str:
        """MISO `/ext/v1/files/upload`에 파일 업로드 → upload_file_id 반환."""
        url = f"{MISO_BASE_URL.rstrip('/')}/ext/v1/files/upload"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        import sys
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
        except Exception as e:
            raise FileMappingError(f"파일을 읽지 못했습니다: {file_path.name} ({e})")

        files = {"file": (file_path.name, file_bytes)}
        data = {"user": user_id or "lucid-hub-user"}
        print(f"[MisoWorker] file upload → {url} name={file_path.name} size={len(file_bytes)}", flush=True, file=sys.stderr)
        try:
            async with httpx.AsyncClient(timeout=MISO_FILE_UPLOAD_TIMEOUT) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)
        except Exception as e:
            raise FileMappingError(f"MISO 파일 업로드 실패: {type(e).__name__}: {e}")

        print(f"[MisoWorker] file upload status={resp.status_code} body={(resp.text or '')[:200]}", flush=True, file=sys.stderr)
        if resp.status_code not in (200, 201):
            raise FileMappingError(
                f"MISO 파일 업로드 거부 (HTTP {resp.status_code}): {(resp.text or '')[:200]}"
            )
        try:
            payload = resp.json()
        except Exception:
            raise FileMappingError("MISO 파일 업로드 응답 JSON 파싱 실패")

        # MISO 응답 구조 변동 대비: id / upload_file_id / data.id 등
        upload_id = (
            payload.get("id")
            or payload.get("upload_file_id")
            or (payload.get("data") or {}).get("id")
            or (payload.get("data") or {}).get("upload_file_id")
        )
        if not upload_id:
            raise FileMappingError(
                f"MISO 파일 업로드 응답에서 file_id를 찾지 못했습니다: {json.dumps(payload, ensure_ascii=False)[:200]}"
            )
        return upload_id

    def _extract_answer(self, data: Dict[str, Any]) -> str:
        """mode별 응답에서 사용자에게 보여줄 텍스트 추출.

        파일 출력 처리 (Dify/MISO 표준):
        - outputs 내부 어디든 `{type, url}` 또는 `{type, upload_file_id}` shape
          (type ∈ image/document/audio/video) 발견 시 마크다운으로 변환:
          - image → ![filename](url) 인라인 표시
          - 그 외 → [📎 filename](url) 다운로드 링크
        - string 텍스트와 공존 가능 — 텍스트 + 파일 링크가 함께 표시됨.
        """
        if self.mode == "chat":
            answer = data.get("answer")
            if isinstance(answer, str) and answer.strip():
                base = answer
            else:
                inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                inner_answer = inner.get("answer") if isinstance(inner, dict) else None
                base = inner_answer if isinstance(inner_answer, str) and inner_answer.strip() else ""
            # chat 모드는 보통 답변이 다 텍스트 — files 필드가 있으면 같이 노출
            files_md = self._format_file_outputs(data.get("files") or (data.get("data") or {}).get("files") or [])
            if base and files_md:
                return f"{base}\n\n{files_md}"
            return base or files_md or "(MISO 응답 없음)"

        # workflow — outputs 위치는 data.data.outputs 또는 data.outputs
        outputs = data.get("outputs")
        if not outputs:
            inner = data.get("data")
            if isinstance(inner, dict):
                outputs = inner.get("outputs")
        outputs = outputs or {}

        if isinstance(outputs, dict):
            # 텍스트 part
            text_part = ""
            for key in ("결과", "output", "answer", "result", "text", "response", "message"):
                v = outputs.get(key)
                if isinstance(v, str) and v.strip():
                    text_part = v
                    break
            if not text_part:
                strs = [v for v in outputs.values() if isinstance(v, str) and v.strip()]
                if strs:
                    text_part = "\n\n".join(strs)

            # 파일 part (재귀 검출)
            files_md = self._format_file_outputs(outputs)

            if text_part and files_md:
                return f"{text_part}\n\n{files_md}"
            if text_part:
                return text_part
            if files_md:
                return files_md
            # 둘 다 없음 — JSON dump 또는 빈
            if outputs:
                return json.dumps(outputs, ensure_ascii=False, indent=2)
            return "(워크플로우 출력이 비어있습니다)"
        if isinstance(outputs, str):
            return outputs or "(워크플로우 출력 없음)"
        return str(outputs) or "(워크플로우 출력 없음)"

    # ============================================================
    # 파일 출력 검출 (Dify/MISO 표준 응답 → 마크다운)
    # ============================================================

    _FILE_TYPES = {"image", "document", "audio", "video"}

    def _format_file_outputs(self, node: Any) -> str:
        """outputs 내부를 재귀 스캔하여 file shape 발견 시 마크다운 라인으로 합침."""
        files = self._collect_file_nodes(node)
        if not files:
            return ""
        lines: List[str] = []
        for f in files:
            ftype = (f.get("type") or "").lower()
            url = f.get("url") or ""
            filename = f.get("filename") or f.get("name") or "file"
            if not url:
                continue
            if ftype == "image":
                lines.append(f"![{filename}]({url})")
            else:
                size = f.get("size")
                size_str = f" ({self._human_size(size)})" if isinstance(size, (int, float)) and size > 0 else ""
                lines.append(f"[📎 {filename}{size_str}]({url})")
        return "\n\n".join(lines)

    def _collect_file_nodes(self, node: Any, out: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """dict/list 트리에서 file shape `{type, url}` (type ∈ FILE_TYPES) 노드 수집."""
        if out is None:
            out = []
        if isinstance(node, dict):
            ftype = node.get("type")
            url = node.get("url")
            if isinstance(ftype, str) and ftype.lower() in self._FILE_TYPES and isinstance(url, str) and url:
                out.append(node)
                # file 노드 자체의 children은 더 안 봐도 됨 (file 안에 또 file 없음)
                return out
            for v in node.values():
                self._collect_file_nodes(v, out)
        elif isinstance(node, list):
            for v in node:
                self._collect_file_nodes(v, out)
        return out

    @staticmethod
    def _human_size(n: Any) -> str:
        try:
            n = float(n)
        except (TypeError, ValueError):
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
            n /= 1024
        return f"{n:.1f}TB"

    def _error_event(self, message: str) -> Dict[str, Any]:
        """에러를 사용자 채팅에 직접 표시 (on_chat_model_stream으로 변환)."""
        return {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessageChunk(content=f"⚠ {message}\n")},
        }

    async def _record_execution(
        self,
        execution_id: str,
        user_id: str,
        context: Dict[str, Any],
        status: str,
        output_summary: Optional[str] = None,
        error_message: Optional[str] = None,
        started_at: Optional[float] = None,
    ) -> None:
        """agent_executions INSERT (best-effort, 실패해도 응답에 영향 X)."""
        try:
            db = get_database_connection()
            elapsed_ms = int((time.time() - started_at) * 1000) if started_at else None
            with db.get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_executions (
                        id, agent_id, agent_version, user_id,
                        workspace_id, session_id,
                        input_args, output_summary, status, error_message,
                        started_at, completed_at, execution_time_ms
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s,
                        FROM_UNIXTIME(%s), NOW(), %s
                    )
                    """,
                    (
                        execution_id, self.agent_id, "1.0.0", user_id,
                        context.get("workspace_id"), context.get("session_id"),
                        json.dumps({"query": "(masked)"}, ensure_ascii=False),
                        output_summary,
                        status, error_message,
                        started_at if started_at else time.time(),
                        elapsed_ms,
                    ),
                )
        except Exception as e:
            logger.warning(f"[MisoWorker] execution log failed: {e}")
