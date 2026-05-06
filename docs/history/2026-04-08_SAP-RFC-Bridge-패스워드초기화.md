# 2026-04-08 SAP RFC Bridge + 패스워드 초기화

## 개요
SAP RFC 함수를 호출하기 위한 별도 마이크로서비스(sap-rfc-bridge)를 구축하고, IT Support Worker에서 SAP 비밀번호 초기화(Z02CMF_PASSWORD_INIT)를 자동 수행할 수 있도록 통합했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| C:\Services\sap-rfc-bridge\main.py | 신규 | FastAPI 기반 SAP RFC Bridge 서비스 (Python 3.12) |
| C:\Services\sap-rfc-bridge\.env | 신규 | SAP 개발/품질 서버 접속정보 |
| C:\Services\sap-rfc-bridge\start.bat | 신규 | 서비스 실행 스크립트 |
| C:\nwrfcsdk\ | 신규 | SAP NW RFC SDK (Windows DLL) |
| backend/.env | 수정 | SAP_RFC_BRIDGE_URL 추가 |
| backend/app/mcp_servers/works_it_mcp_server.py | 수정 | reset_sap_password MCP 도구 + login_id→사번 변환 |
| backend/app/agents/workers/it_support_worker.py | 수정 | 도구 등록, 프롬프트 추가, 사번 자동 주입 |

## 상세 내용

### SAP RFC Bridge (별도 마이크로서비스)
- **위치**: `C:\Services\sap-rfc-bridge\` (배포: 192.168.100.72:8001)
- **이유**: pyrfc 라이브러리가 Python 3.13을 지원하지 않음 (Cython 빌드 + VS 2022 필요). Python 3.12 별도 서비스로 분리.
- **SDK**: SAP NW RFC SDK 7.50 Windows x64 → `C:\nwrfcsdk\`
- **환경변수**: `SAPNWRFC_HOME`, PATH에 lib 추가 필요

**API 엔드포인트:**
| Endpoint | 용도 |
|----------|------|
| GET /health | 헬스체크 |
| POST /rfc/ping | SAP 연결 테스트 (STFC_CONNECTION) |
| POST /rfc/call | 범용 RFC 함수 호출 |
| POST /rfc/password-init | 패스워드 초기화 전용 (미사용, /rfc/call로 통일) |

**인증**: 기본 비활성. `BRIDGE_API_KEY` 환경변수 설정 시 X-API-Key 헤더 필수.

### 메인 백엔드 통합
- `works_it_mcp_server.py`에 `reset_sap_password` MCP 도구 추가
- Bridge HTTP 호출: `POST {SAP_RFC_BRIDGE_URL}/rfc/call`
- **login_id → employee_number 변환**: SSO 쿠키는 login_id(wg0403)를 전달하므로, `v_user_info_mapping` 뷰에서 사번(A2304013)으로 변환 후 RFC 호출

### 사번 자동 주입 (보안)
- `prepare_tools()`에서 `reset_sap_password`도 기존 `register_works_voc`과 동일한 패턴으로 래핑
- LLM이 어떤 값을 넣든 SSO 세션의 user_id로 강제 덮어쓰기
- 본인 계정만 초기화 가능

### RFC 함수: Z02CMF_PASSWORD_INIT
- **Input**: I_EMP_NO (CHAR 40, 사원번호)
- **Output**: ES_RETURN.RETCD (S/E), ES_RETURN.RETMG (결과 메시지)
- **동작**: BAPI_USER_CHANGE로 패스워드를 Pass1234567890!로 초기화

## 결정 사항 및 주의점
- **네트워크**: LNFGPUDEV(개발서버)에서 SAP 대역(172.16.x.x) 접근 불가 → 192.168.100.72에 Bridge 배치
- **방화벽**: Bridge 서버에서 8001 포트 인바운드 + SAP 서버 3300 아웃바운드 필요
- **SAP 권한**: RFC 사용자 LNF12에 BAPI_USER_CHANGE 권한 필요 (SAP Basis팀에 요청 중)
- **SAP 접속정보**: 개발(172.16.3.52, Client 600, DS4) / 품질(172.16.2.244, Client 210, QS4)
- **스펙 vs 실제 차이**: 스펙 문서는 IS_INPUT 구조체였으나 실제는 직접 파라미터, 리턴도 ES_RESULT → ES_RETURN
