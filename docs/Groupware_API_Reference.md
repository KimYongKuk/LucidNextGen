# 그룹웨어 관리 API Reference

> 작성일: 2026-04-21 (2026-04-22 secure 경로 + 인증 토큰 반영)
> Base URL: `https://api.landf.co.kr:44818/`
> 용도: 그룹웨어 사용자 계정 관리 (OTP/패스워드 초기화, 메일 용량 증설)

---

## 개요

LF그룹 그룹웨어(LFON) 사용자 계정의 **관리 작업을 원격으로 수행하기 위한 REST API**이다. 현재 지원하는 작업은 다음 3가지이다.

| 작업 | Endpoint | Method | updateDataFlag |
|------|----------|--------|----------------|
| OTP 초기화 | `/secure/lfon/management/OTP` | `PUT` | `OTP` |
| 패스워드 초기화 | `/secure/lfon/management/password` | `PUT` | `password` |
| 메일 용량 증설 | `/secure/lfon/management/userInfo` | `PUT` | `mail` |

### 공통 사항

- **프로토콜**: HTTPS (포트 `44818`)
- **요청 형식**: JSON (`Content-Type: application/json`)
- **인증**: `Authorization: <TOKEN>` 헤더 필수 (2026-04-22 추가). 토큰은 `.env`의 `LFON_MGMT_API_KEY`에 저장.
- **대상 지정**: `ids` 배열에 그룹웨어 ID(정수)를 하나 이상 담아 전달. 다건 처리 가능 구조.
- **동작 원리**: `updateDataFlag`로 엔드포인트별 처리 종류를 구분. 단일 API 패턴을 세 경로로 분기.

### 이력

| 날짜 | 변경 |
|------|------|
| 2026-04-21 | 최초 명세 수령 — 인증 없음, `/lfon/management/*` 경로 |
| 2026-04-22 | `/secure/lfon/management/*` 경로로 변경 + `Authorization` 헤더 인증 추가. 리버스 엔지니어링으로 타 사용자 계정 조작 가능했던 근본 취약점 해결 |

---

## 1. OTP 초기화

사용자의 OTP(일회용 비밀번호) 설정을 초기화한다. 주로 OTP 장치 분실/재설정 시 사용.

### Endpoint

```
PUT /secure/lfon/management/OTP
```

### Request Body

| 필드 | 필수 | 타입 | 설명 |
|------|------|------|------|
| `ids` | required | array\<integer\> | 그룹웨어 ID 목록 (예: `[870]`) |
| `updateDataFlag` | required | string | 고정값 `"OTP"` |

### 예시

```http
PUT /secure/lfon/management/OTP HTTP/1.1
Content-Type: application/json

{
  "ids": [870],
  "updateDataFlag": "OTP"
}
```

### Response

| 값 | 의미 |
|------|------|
| `success` | 초기화 성공 |
| `fail` | 초기화 실패 |

---

## 2. 패스워드 초기화

사용자의 그룹웨어 로그인 패스워드를 초기화한다. (초기화 후 사용자는 최초 로그인 시 재설정 필요)

### Endpoint

```
PUT /secure/lfon/management/password
```

### Request Body

| 필드 | 필수 | 타입 | 설명 |
|------|------|------|------|
| `ids` | required | array\<integer\> | 그룹웨어 ID 목록 |
| `updateDataFlag` | required | string | 고정값 `"password"` |

### 예시

```http
PUT /secure/lfon/management/password HTTP/1.1
Content-Type: application/json

{
  "ids": [870],
  "updateDataFlag": "password"
}
```

### Response

| 값 | 의미 |
|------|------|
| `success` | 초기화 성공 |
| `fail` | 초기화 실패 |

---

## 3. 메일 용량 증설

사용자의 그룹웨어 메일함 용량을 증설한다. 증설 단계에 따라 응답이 달라지며, `result.code`로 현재 상태를 구분한다.

### Endpoint

```
PUT /secure/lfon/management/userInfo
```

### Request Body

| 필드 | 필수 | 타입 | 설명 |
|------|------|------|------|
| `ids` | required | array\<integer\> | 그룹웨어 ID 목록 |
| `updateDataFlag` | required | string | 고정값 `"mail"` |

### 예시

```http
PUT /secure/lfon/management/userInfo HTTP/1.1
Content-Type: application/json

{
  "ids": [870],
  "updateDataFlag": "mail"
}
```

### Response 패턴

#### (1) 증설 완료 (정상)

```
success
```

단순 문자열 반환.

#### (2) 이미 증설된 상태 (1회 증설 후 재요청)

```json
{
  "result": {
    "success": false,
    "message": "이미 용량이 증설된 상태입니다. 추가 증설이 필요하신 경우 기안 상신을 부탁드립니다.",
    "code": "full"
  }
}
```

→ **후속 처리**: 사용자에게 "추가 증설은 결재 기안 필요" 안내. 기안 상신 workflow로 유도.

#### (3) 최대 용량 도달

```json
{
  "result": {
    "success": false,
    "message": "현재 용량이 최대치에 도달한 상태이므로, 메일 정리 및 백업 진행을 부탁드립니다.",
    "code": "end"
  }
}
```

→ **후속 처리**: 사용자에게 "메일 정리/백업 필요" 안내. 용량 증설 대신 사용자 정리 요청.

### result.code 요약

| code | 의미 | 권장 후속 안내 |
|------|------|----------------|
| (없음, `success`) | 증설 성공 | 완료 안내 |
| `full` | 이미 1회 증설 완료 | 결재 기안 상신 안내 |
| `end` | 최대 용량 도달 | 메일 정리/백업 안내 |

---

## 응답 형식의 비일관성 (주의)

세 엔드포인트의 응답 형식이 통일되어 있지 않다. 클라이언트 구현 시 **분기 처리**가 필요하다.

| Endpoint | 성공 응답 | 실패 응답 |
|----------|-----------|-----------|
| OTP 초기화 | `success` (문자열) | `fail` (문자열) |
| 패스워드 초기화 | `success` (문자열) | `fail` (문자열) |
| 메일 용량 증설 | `success` (문자열) | `{ "result": { "success": false, "message": ..., "code": ... } }` (JSON 객체) |

### 권장 파싱 로직 (의사 코드)

```python
if response.text.strip() == "success":
    # 성공
    ...
elif response.text.strip() == "fail":
    # 단순 실패
    ...
else:
    # JSON 객체 — 메일 증설 실패 케이스
    data = response.json()
    code = data["result"]["code"]  # "full" | "end"
    message = data["result"]["message"]
    ...
```

---

## 챗봇 연동 시 고려 사항

본 API를 LFChatbot에 통합할 경우 다음을 검토해야 한다.

### 1. 인증/권한

- 현재 명세에는 **인증 헤더가 명시되어 있지 않음** → 운영 적용 전 API Key/토큰 방식 확인 필요
- 임의 사용자가 남의 계정(`ids`)을 조작할 수 있으므로, **반드시 요청자 본인의 그룹웨어 ID만 허용**하는 서버 사이드 검증 필요
  - 패턴: MailWorker처럼 `context["user_id"]`(사번)에서 그룹웨어 ID를 조회해 강제 주입

### 2. 대상 Worker 설계

기존 Worker 구조 기준 다음 두 가지 선택지가 있다.

- **옵션 A**: 신규 `AccountMgmtWorker` 생성 → 계정 관리 전용 MCP 서버(`lfon_mgmt_server.py`) 연동
- **옵션 B**: 기존 `ITSupportWorker`에 기능 추가 → IT VOC의 "패스워드 초기화" 요청을 실제 실행까지 연결

권장: **옵션 A** — 보안 민감도가 높은 destructive 액션(패스워드/OTP 리셋)은 별도 Worker로 격리하고, Intent classifier에서 명확한 키워드만 라우팅.

### 3. Destructive Action 가드

OTP/패스워드 초기화는 **사용자에게 즉시 영향**을 미치는 destructive 작업이다.

- 실행 전 확인 절차 필수: "정말 초기화하시겠습니까?" 확인 후 실행
- 채팅 로그에 실행 이력 명시 저장 (감사 추적)
- Rate limit 적용 (동일 ID 단시간 반복 차단)

### 4. 환경 변수 (제안)

```env
LFON_API_BASE_URL=https://api.landf.co.kr:44818
LFON_API_KEY=<필요 시>
ACCOUNT_MGMT_WORKER_ENABLED=true
```

### 5. 사용자 ID 매핑

현재 챗봇 사용자 식별자는 **사번(employee_number)** 이지만, 본 API는 **그룹웨어 ID**(정수)를 요구한다. 매핑 테이블/VIEW가 필요하다.

- 참고: MailWorker가 `v_mail_user_mapping`(사번→message_store) 매핑 VIEW를 사용 중
- 유사 패턴: `v_groupware_user_mapping(employee_number, groupware_id)` VIEW 생성 권장 (DBA 요청)

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-04-21 | 최초 작성 (원문 API 정의서 기반) |
