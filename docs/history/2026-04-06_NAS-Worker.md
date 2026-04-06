# 2026-04-06 NAS 파일 탐색 Worker

## 개요
회사 Synology NAS(WebDAV)를 LFChatbot에 연동하여, 사용자가 자연어로 NAS 공유 폴더의 파일을 탐색/검색/다운로드할 수 있도록 NAS MCP 서버와 NASWorker를 신규 구현했다. 1단계로 읽기 전용 도구만 제공한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/nas_mcp_server.py` | 신규 | NAS MCP 서버 (FastMCP, stdio, 4개 읽기전용 도구) |
| `backend/app/agents/workers/nas_worker.py` | 신규 | NASWorker (Sonnet, prepare_tools 보안 래핑) |
| `backend/app/agents/state.py` | 수정 | Intent.NAS 추가 + INTENT_TO_WORKER/WORKER_CAPABILITIES 매핑 |
| `backend/app/agents/intent_classifier.py` | 수정 | NAS 키워드 quick_classify + LLM CLASSIFIER_PROMPT |
| `backend/app/agents/workers/__init__.py` | 수정 | NASWorker 등록 |
| `backend/mcp_config.json` | 수정 | nas_server 등록 |
| `backend/.env` | 수정 | NAS 환경변수 추가 |

## 상세 내용

### MCP 도구 (읽기 전용)
| 도구 | 설명 |
|------|------|
| `list_nas_directory` | 폴더 내 파일/하위폴더 목록 조회 |
| `search_nas_files` | 파일명 키워드로 재귀 검색 (max_depth 1~5, 최대 50건) |
| `download_nas_file` | 파일 다운로드 → `data/nas_download/{date}/{uuid}_{filename}` |
| `get_nas_file_info` | 파일/폴더 존재 여부 및 메타정보 (크기, 수정일) |

### 보안 설계 (이중 방어)
1. **MCP 서버 레벨**: `_validate_path()` — `..` 차단, `NAS_ALLOWED_PATHS` 화이트리스트
2. **Worker 레벨**: `prepare_tools()` — ainvoke 래핑으로 모든 경로 인자 재검증 + 감사 로그
3. **감사 로깅**: 모든 NAS 작업을 stderr에 기록 (`[NAS AUDIT]` / `[NAS]` 태그)

### 환경변수
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NAS_WEBDAV_URL` | `http://192.168.100.20:5005` | WebDAV 서버 URL |
| `NAS_USERNAME` | - | 서비스 계정 (현재 wg0403, 추후 전용 계정으로 교체) |
| `NAS_PASSWORD` | - | 서비스 계정 비밀번호 |
| `NAS_ALLOWED_PATHS` | `/Landf/부서간공유` | 허용 경로 (쉼표 구분) |
| `NAS_WORKER_ENABLED` | `true` | Worker 활성화 여부 |
| `NAS_WEBDAV_ROOT` | (빈 문자열) | WebDAV 루트 프리픽스 (현재 NAS는 루트 마운트) |

### Intent 분류
- `Intent.NAS = "nas"` → `NASWorker`
- quick_classify 키워드: NAS, 공유폴더, 부서간공유, 데이터서버, 파일서버, 시놀로지 등

### 암호화 파일 대응
- 다운로드 자체는 항상 성공 (바이너리 파일)
- 파싱 실패 시 Worker 시스템 프롬프트에서 "암호화 파일" 안내 유도
- 강제 해독 시도 안 함

## 결정 사항 및 주의점
- **1단계 읽기 전용**: 쓰기/삭제/이동 도구는 보안 검토 후 2단계에서 추가
- **서비스 계정**: 현재 개인 계정(wg0403) 사용 중, IT팀에 AD 서비스 계정 발급 요청 필요
- **WebDAV Root**: 이 NAS는 `/webdav/` 프리픽스 없이 루트에 직접 마운트됨 → `NAS_WEBDAV_ROOT=""` 설정
- **향후 확장**: 쓰기 도구, DSM FileStation API 연동, 부서별 접근 제어, RAG 자동 동기화
