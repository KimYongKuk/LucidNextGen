# 2026-04-17 MCP 서버 동시 스폰 수 제한

## 개요
Windows 환경에서 MCP 서버 18개를 `asyncio.gather`로 동시 스폰 시 12개가 `ExceptionGroup` 프로세스 스폰 경쟁으로 실패하는 간헐적 버그 수정. 세마포어로 동시 로딩 수를 4개로 제한하여 안정성 확보.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/adapters/mcp_adapter.py | 수정 | `MAX_CONCURRENT_LOADS=4` 세마포어 추가 |

## 상세 내용

### 발생 현상
2026-04-17 07:08:38에 MailWorker가 "메일 조회 도구에 접근이 원활하지 않습니다" 응답을 반환. 로그 분석 결과:

```
[2026-04-17 07:08:37] [MCP] WARNING: Server 'mail_server' failed to load: ExceptionGroup: ...
[2026-04-17 07:08:37] [MCP] WARNING: Server 'youtube' failed to load: ExceptionGroup: ...
[2026-04-17 07:08:37] [MCP] WARNING: Server 'works_it' failed to load: ExceptionGroup: ...
... (총 12개 서버)
[2026-04-17 07:08:38] [MCP] Tools cached: 32 tools (from 18 servers, 0 blacklisted)
[2026-04-17 07:08:38] [MailWorker] Using tools: ['create_document_pdf', 'create_table_spec_pdf', 'create_document_docx']
```

- 정상 시 91개 도구 캐싱 → 32개만 성공
- MailWorker에 `get_inbox_mail` 등 메일 도구가 전달되지 않음
- LLM이 도구 호출 실패 후 자체 판단으로 "조회 불가" 응답

### 타임라인
| 시각 | 상태 |
|------|------|
| 2026-04-16 21:36 | 91개 도구 정상 캐싱 (18/18 서버) |
| 2026-04-17 07:08 | 캐시 만료 후 재로딩 시 **12개 서버 동시 실패** |
| 2026-04-17 07:11 | TTL 60초 단축 덕분에 자동 복구 (91개 도구) |

### 원인
`backend/app/adapters/mcp_adapter.py:300`의 `asyncio.gather`가 18개 MCP 서버를 동시에 스폰 → Windows 서브프로세스 스폰 경쟁 조건 → `ExceptionGroup: unhandled errors in a TaskGroup` 발생.

캐시 TTL 1시간이 만료된 직후 첫 요청에서 재로딩할 때 간헐적으로 발생. 평소에는 운 좋게 성공하지만 타이밍에 따라 실패.

### 수정
```python
# 동시 스폰 서버 수 제한 (Windows에서 한꺼번에 많은 프로세스 스폰 시 ExceptionGroup 실패 방지)
MAX_CONCURRENT_LOADS: int = 4

semaphore = asyncio.Semaphore(MCPAdapter.MAX_CONCURRENT_LOADS)

async def _load_server_tools(name: str):
    async with semaphore:
        try:
            return await asyncio.wait_for(...)
```

- `asyncio.Semaphore(4)`로 동시에 4개 서버만 스폰 허용
- 18개 서버 → 4개씩 5배치로 순차 로딩
- 초기 로딩 시간: 약 3초 → 5~6초 증가 (캐싱 이후에는 동일)

## 결정 사항 및 주의점
- **동시 수 4개 선택 근거**: Windows 프로세스 스폰은 CPU/IO 바운드 혼합이라 너무 낮으면 느려지고 너무 높으면 실패 증가. 4개는 경험적으로 안정적인 선택.
- **기존 TTL 복구 로직 유지**: 세마포어로도 혹시 실패 시 `cache_timestamp`를 `now - CACHE_TTL + 60`으로 설정하여 60초 후 자동 재시도.
- **블랙리스트 로직 유지**: `FileNotFoundError` 등 영구 실패는 여전히 블랙리스트 처리.
- **트레이드오프**: 초기 로딩 느려지는 대신 실패율 대폭 감소 — 캐싱 덕분에 사용자 체감은 "처음 1번만 약간 느림".
