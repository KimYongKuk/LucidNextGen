# 2026-04-17 SAP RFC Bridge 다중 시스템 지원 (DEV + PRD)

## 개요
기존 SAP RFC Bridge는 한 번에 한 시스템(운영 또는 개발)만 바라보는 단일 커넥션 구조였다. 실제로는 개발(DS4/600)과 운영(PS4/210)을 동시에 써야 하므로, 시스템별 커넥션 풀과 `system` 파라미터 기반 라우팅을 도입했다. 메모리에 기록된 운영 IP 오류(`172.16.3.64` → 실제 `172.16.3.147`)도 함께 보정.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `C:\Services\sap-rfc-bridge\main.py` | 수정 | `SAPConnectionPool` 다중 시스템화, `/rfc/*` 엔드포인트에 `system` 필드 추가 |
| `C:\Services\sap-rfc-bridge\.env` | 수정 | `SAP_DEV_*`/`SAP_PRD_*` 접두사 분리, `SAP_DEFAULT_SYSTEM=prd` |
| `backend/app/mcp_servers/works_it_mcp_server.py` | 수정 | `reset_sap_password(employee_number, system="prd")` 파라미터 추가 |
| `backend/app/agents/workers/it_support_worker.py` | 수정 | SAP 비밀번호 초기화 프롬프트에 dev/prd 판별 규칙 추가 |

## 상세 내용

### 1. Bridge 구조 변경

**기존**: 단일 `self._conn` + env 한 세트
```python
self._conn_params = {"ashost": os.getenv("SAP_ASHOST", ""), ...}
```

**변경**: 시스템별 딕셔너리 (`dev`, `prd`)
```python
SUPPORTED_SYSTEMS = ("dev", "prd")
self._conns: dict[str, Any] = {}
self._params: dict[str, dict] = {}
for sys_name in SUPPORTED_SYSTEMS:
    prefix = f"SAP_{sys_name.upper()}_"
    ashost = os.getenv(f"{prefix}ASHOST", "")
    if not ashost: continue  # 미설정 시스템은 건너뜀
    self._params[sys_name] = {...}
```

- `_normalize_system(system)`: None/빈값은 `SAP_DEFAULT_SYSTEM`(기본 `prd`)으로 폴백, 미설정/미지원 값은 ValueError
- `call(function_name, system=None, **params)`: 시스템 선택 후 lazy connect, 실패 시 해당 시스템만 재연결(다른 시스템 풀은 유지)
- `close()`: 모든 시스템 커넥션 정리

### 2. 엔드포인트 변경

| 엔드포인트 | 변경 |
|-----------|------|
| `GET /health` | `systems`, `default` 필드 추가 (구성된 시스템 목록 노출) |
| `POST /rfc/call` | Body에 `system: "dev"|"prd"|null` 추가, 응답에 `system` 필드 포함 |
| `POST /rfc/ping` | Body에 `system` 추가 (기존 파라미터 없음 → Optional body) |
| `POST /rfc/password-init` | Body에 `system` 추가, 응답에 `system` 포함 |

### 3. MCP 도구 변경

```python
async def reset_sap_password(employee_number: str, system: str = "prd") -> str:
```

- `system`은 `"dev"` 또는 `"prd"`만 허용, 그 외 값은 오류 반환
- Bridge `/rfc/call` 호출 시 `"system": system_norm` 포함
- 응답 메시지에 `[운영(PRD)]` / `[개발(DEV)]` 라벨 추가 → 사용자가 구분 가능
- `prepare_tools()`의 employee_number 강제 주입 로직은 그대로(system 파라미터는 LLM이 자유롭게 지정)

### 4. Worker 프롬프트 규칙

```
1. 대상 시스템(운영/개발) 판별:
   - "개발", "DEV", "개발서버", "테스트 SAP" → system="dev"
   - "운영", "PRD", "실서버" 또는 별도 언급 없음 → system="prd" (기본)
   - 애매하면 1회만 "운영 SAP인가요, 개발 SAP인가요?" 확인
2. 한 번에 양쪽 둘 다 초기화 요청 시 → 두 번 호출 (각각 "prd", "dev")
```

### 5. 배포 절차

1. 192.168.100.72의 `C:\Services\sap-rfc-bridge\main.py`, `.env` 교체
2. Bridge 프로세스 재시작 (`start.bat`)
3. 검증:
   ```bash
   curl http://192.168.100.72:8001/health
   # → {"status":"ok", "systems":["dev","prd"], "default":"prd"}

   curl -X POST http://192.168.100.72:8001/rfc/ping -d '{"system":"dev"}'
   curl -X POST http://192.168.100.72:8001/rfc/ping -d '{"system":"prd"}'
   # 둘 다 Sysid 다르게 나와야 성공 (DS4 vs PS4)
   ```
4. 메인 백엔드 재배포 (MCP/Worker 코드 변경 반영)

## 결정 사항 및 주의점

- **기본값을 `prd`로 고정**: 기존 API 사용자(`system` 필드 없이 호출)가 기본 동작을 유지하도록. 개발에 쓰려면 명시적으로 `"system":"dev"`.
- **QA(172.16.2.244/210/QS4) 미지원**: 사용 예정 없음. 추후 필요 시 `SUPPORTED_SYSTEMS`에 `"qa"` 추가 + `.env`에 `SAP_QA_*` 접두사 추가하면 확장 가능.
- **비밀번호 동기화 전제**: DEV/PRD 모두 `LNF12 / LFpass2026!`. 한쪽만 바뀌면 Bridge에 둘 다 별도 입력 필요.
- **Bridge API 버전**: `2.0.0`으로 표기 — breaking change는 아니지만 (system 파라미터 옵셔널) 다중 시스템 도입 기점 구분 용도.
- **커넥션 재사용**: 시스템별 1 커넥션을 프로세스 수명 동안 재사용. 실패 시 해당 시스템만 재연결(다른 시스템 영향 없음).
- **SU01 계정 타입**: 현재 Communication Data(타입 3). Dialog 아니어도 RFC 로그온 가능, `STFC_CONNECTION`/`Z02CMF_PASSWORD_INIT` 모두 확인 완료.
