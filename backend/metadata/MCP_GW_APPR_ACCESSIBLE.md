# 전자결재 부서 문서함 접근 권한 및 수신 상태 가이드

## 개요

이 문서는 전자결재 부서 문서함과 관련된 두 가지 핵심 뷰를 다룹니다.

1. **`v_appr_user_accessible_depts`** — 사용자별 접근 가능한 부서 문서함 목록
2. **`v_appr_dept_received`** — 부서 수신함 문서 (부서별 독립 접수 상태 구분 포함)

---

## 1. v_appr_user_accessible_depts (부서 문서함 접근 권한)

### 접근 권한의 두 가지 유형

#### MEMBER (소속 부서)
- 사용자가 `go_dept_members`를 통해 소속된 부서
- 모든 사용자는 자기 소속 부서의 문서함에 기본 접근 가능
- 겸직(type=0) 및 주소속(type=2) 모두 포함

#### SUBSCRIBER_MASTER (부서 문서함 담당자 지정)
- `go_appr_doc_subscriber_masters` 테이블에 명시적으로 담당자로 지정된 경우
- 소속 부서가 아닌 다른 부서의 문서함에 접근해야 할 때 사용
- 예: DA파트 소속이지만 IT운영팀 부서 문서함 담당자로 지정 → IT운영팀 문서함 접근 가능

> **주의**: 상위 부서라고 자동으로 접근 가능한 것이 아닙니다. 반드시 `go_appr_doc_subscriber_masters`에 담당자로 지정되어야만 타 부서 문서함에 접근할 수 있습니다.

### 스키마

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| user_id | bigint | 사용자 ID |
| user_name | varchar | 사용자 이름 |
| employee_number | varchar | 사번 |
| dept_id | bigint | 부서 ID |
| dept_name | varchar | 부서명 |
| dept_code | varchar | 부서 코드 |
| dept_path | varchar | 부서 계층 경로 (콜론 구분) |
| access_type | text | 접근 유형 (`MEMBER` 또는 `SUBSCRIBER_MASTER`) |
| use_reception | boolean | 부서 수신함 사용 여부 |
| use_doc_folder | boolean | 부서 문서함 사용 여부 |
| use_official_doc_send | boolean | 공문 발송 사용 여부 |

### DDL

```sql
CREATE OR REPLACE VIEW v_appr_user_accessible_depts AS
-- 1. 본인 소속 부서 (기본 접근)
SELECT 
    u.id AS user_id,
    u.name AS user_name,
    u.employee_number,
    d.id AS dept_id,
    d.name AS dept_name,
    d.code AS dept_code,
    d.path AS dept_path,
    'MEMBER' AS access_type,
    ds.use_reception,
    ds.use_doc_folder,
    ds.use_official_doc_send
FROM go_dept_members dm
JOIN go_users u ON dm.user_id = u.id
JOIN go_departments d ON dm.department_id = d.id
JOIN go_appr_department_settings ds ON ds.department_id = d.id
WHERE dm.deleted_at IS NULL
  AND u.deleted_at IS NULL
  AND u.status = 'ONLINE'
  AND d.deleted_at IS NULL

UNION

-- 2. 부서 문서함 담당자 지정 (추가 접근)
SELECT 
    u.id AS user_id,
    u.name AS user_name,
    u.employee_number,
    d.id AS dept_id,
    d.name AS dept_name,
    d.code AS dept_code,
    d.path AS dept_path,
    'SUBSCRIBER_MASTER' AS access_type,
    ds.use_reception,
    ds.use_doc_folder,
    ds.use_official_doc_send
FROM go_appr_doc_subscriber_masters sm
JOIN go_users u ON sm.user_id = u.id
JOIN go_departments d ON sm.dept_id = d.id
JOIN go_appr_department_settings ds ON ds.department_id = d.id
WHERE u.deleted_at IS NULL
  AND u.status = 'ONLINE'
  AND d.deleted_at IS NULL;
```

---

## 2. v_appr_dept_received (부서 수신함 — 부서별 독립 접수 상태 포함)

### 접수 상태(reception_status) 구분 로직

부서 수신함 문서는 아래 상태로 분류됩니다.

| reception_status | 의미 | 판단 기준 |
|-----------------|------|----------|
| `WAITING` | 접수대기 | 결재 완료(`appr_status='APPROVAL'`)되었으나 **해당 부서에서** 아직 접수 처리 안 됨 |
| `RECEIVED` | 접수완료 | `go_appr_actionlogs`에 `RECEIVED` 기록이 존재하며, **접수자가 해당 수신부서의 담당자 또는 소속 멤버** |
| `RECV_RETURNED` | 접수반려 | `reception_return_comment`가 존재 |
| 기타 | 진행중 등 | `appr_status` 값 그대로 사용 |

### ⚠️ 부서별 독립 접수 핵심 로직

동일 문서가 여러 부서(예: IT인프라팀, IT운영팀, 보안기술팀)에 동시 수신될 수 있습니다. 각 부서는 **독립적으로** 접수 처리하므로, 접수 완료 판단 시 반드시 **접수자(actor)가 해당 수신부서와 관련된 사람인지** 확인해야 합니다.

`go_appr_actionlogs` 테이블에는 부서 컬럼이 없기 때문에, 접수자가 수신부서의 담당자(`go_appr_doc_subscriber_masters`)이거나 소속 멤버(`go_dept_members`)인 경우에만 해당 부서의 접수로 인정합니다.

**실제 예시** (문서 1171249):

| 수신부서 | reception_status | 접수자 | 접수시점 |
|---------|-----------------|--------|---------|
| IT운영팀 | **WAITING** | — | — |
| IT인프라팀 | **RECEIVED** | 김소연 | 2026-03-19 18:14 |
| 보안기술팀 | **RECEIVED** | 강병준 | 2026-03-19 15:56 |

→ IT인프라팀의 김소연이 접수해도 IT운영팀은 여전히 WAITING 상태.

### ❌ 사용 금지 컬럼

- **`is_assigned`**: 접수 완료 여부 판단에 신뢰할 수 없습니다. `is_assigned=false`인데 실제로는 접수 완료된 문서가 존재합니다. 반드시 `reception_status` 또는 `is_received` 컬럼을 사용하세요.

### 스키마

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| doc_id | bigint | 문서 ID |
| title | varchar | 문서 제목 |
| form_name | varchar | 결재양식명 |
| doc_num | varchar | 문서번호 |
| appr_status | varchar | 결재 상태 (APPROVAL, RETURN 등) |
| doc_status | varchar | 문서 상태 (COMPLETE, RETURN 등) |
| drafter_name | varchar | 기안자 이름 |
| drafter_dept_name | varchar | 기안부서명 |
| dept_id | bigint | 수신부서 ID |
| dept_name | varchar | 수신부서명 |
| is_assigned | boolean | ⚠️ 레거시 — 접수 판단에 사용 금지 |
| reception_return_comment | varchar | 접수반려 코멘트 |
| is_reception_returned | boolean | 접수반려 여부 |
| is_emergency | boolean | 긴급 여부 |
| **is_received** | **boolean** | **해당 부서에서 접수 완료 여부 (신뢰 가능)** |
| **received_by_name** | **varchar** | **접수 처리자 이름** |
| **received_confirmed_at** | **varchar** | **실제 접수 처리 시점** |
| **reception_status** | **text** | **수신 상태: WAITING / RECEIVED / RECV_RETURNED / 기타** |
| doc_body | text | 문서 본문 |
| drafted_at | varchar | 기안일시 |
| completed_at | varchar | 결재완료일시 |
| received_at | varchar | 수신일시 |

### DDL

```sql
CREATE OR REPLACE VIEW v_appr_dept_received AS
SELECT d.id AS doc_id,
    d.title,
    d.form_name,
    d.doc_num,
    d.appr_status,
    d.doc_status,
    d.drafter_name,
    d.drafter_dept_name,
    s.subscriber_id AS dept_id,
    s.subscriber_name AS dept_name,
    s.assigned AS is_assigned,
    s.reception_return_comment,
    CASE
        WHEN s.reception_return_comment IS NOT NULL THEN true
        ELSE false
    END AS is_reception_returned,
    d.is_emergency,
    CASE WHEN recv.id IS NOT NULL THEN true ELSE false END AS is_received,
    recv_user.name AS received_by_name,
    to_char(recv.created_at, 'YYYY-MM-DD HH24:MI') AS received_confirmed_at,
    CASE
        WHEN s.reception_return_comment IS NOT NULL THEN 'RECV_RETURNED'
        WHEN recv.id IS NOT NULL THEN 'RECEIVED'
        WHEN d.appr_status = 'APPROVAL' THEN 'WAITING'
        ELSE d.appr_status
    END AS reception_status,
    b.contents AS doc_body,
    to_char(d.drafted_at, 'YYYY-MM-DD HH24:MI') AS drafted_at,
    to_char(d.completed_at, 'YYYY-MM-DD HH24:MI') AS completed_at,
    to_char(s.received_at, 'YYYY-MM-DD HH24:MI') AS received_at
FROM go_appr_doc_subscribers s
JOIN go_appr_documents d ON s.document_id = d.id
LEFT JOIN go_appr_doc_bodies b ON d.doc_body_id = b.id
LEFT JOIN LATERAL (
    SELECT al.id, al.created_at, al.actor_id
    FROM go_appr_actionlogs al
    WHERE al.document_id = d.id 
      AND al.actionlog_type = 'RECEIVED'
      AND (
          -- 접수자가 해당 수신부서의 문서함 담당자이거나
          EXISTS (SELECT 1 FROM go_appr_doc_subscriber_masters sm 
                  WHERE sm.dept_id = s.subscriber_id AND sm.user_id = al.actor_id)
          OR
          -- 접수자가 해당 수신부서의 소속 멤버이거나
          EXISTS (SELECT 1 FROM go_dept_members dm 
                  WHERE dm.department_id = s.subscriber_id 
                    AND dm.user_id = al.actor_id 
                    AND dm.deleted_at IS NULL)
      )
    ORDER BY al.created_at DESC
    LIMIT 1
) recv ON true
LEFT JOIN go_users recv_user ON recv.actor_id = recv_user.id
WHERE s.type = 'DocReceiver' AND s.subscriber_type = 1 
  AND d.doc_status NOT IN ('DELETE', 'CREATE');
```

---

## 활용 패턴

### 1. 특정 사용자의 접근 가능한 부서 문서함 목록

```sql
SELECT dept_id, dept_name, access_type, use_reception, use_doc_folder
FROM v_appr_user_accessible_depts
WHERE employee_number = 'A2304013'
ORDER BY access_type, dept_name;
```

### 2. 특정 사용자의 부서 수신 접수대기 문서 조회

```sql
SELECT r.doc_id, r.title, r.form_name, r.drafter_name, r.drafter_dept_name,
       r.dept_name, r.drafted_at, r.received_at
FROM v_appr_dept_received r
JOIN v_appr_user_accessible_depts a ON r.dept_id = a.dept_id
WHERE a.employee_number = 'A2511004'
  AND a.use_reception = true
  AND r.reception_status = 'WAITING'
ORDER BY r.received_at DESC;
```

### 3. 특정 사용자의 부서 수신 접수완료 문서 조회

```sql
SELECT r.doc_id, r.title, r.form_name, r.drafter_name,
       r.received_by_name, r.received_confirmed_at,
       r.dept_name, r.drafted_at
FROM v_appr_dept_received r
JOIN v_appr_user_accessible_depts a ON r.dept_id = a.dept_id
WHERE a.employee_number = 'A2511004'
  AND a.use_reception = true
  AND r.reception_status = 'RECEIVED'
ORDER BY r.received_confirmed_at DESC;
```

### 4. 특정 사용자의 부서 참조함 문서 조회

```sql
SELECT r.doc_id, r.title, r.form_name, r.drafter_name, r.dept_name,
       r.drafted_at, a.access_type
FROM v_appr_dept_referenced r
JOIN v_appr_user_accessible_depts a ON r.dept_id = a.dept_id
WHERE a.employee_number = 'A2304013'
ORDER BY r.drafted_at DESC;
```

### 5. 특정 부서 문서함의 담당자 목록 확인

```sql
SELECT user_name, employee_number, access_type
FROM v_appr_user_accessible_depts
WHERE dept_name = 'IT운영팀'
ORDER BY access_type, user_name;
```

---

## 접수 상태 판단 시 주의사항

### ❌ 잘못된 방법 1: is_assigned로 접수 완료 판단
```sql
-- is_assigned=false인데 실제로는 접수 완료된 문서가 존재!
SELECT * FROM v_appr_dept_received WHERE is_assigned = false;
```

### ❌ 잘못된 방법 2: document_id만으로 RECEIVED actionlog JOIN
```sql
-- 다부서 수신 시, A부서 접수가 B부서에도 적용되는 오류 발생!
SELECT * FROM go_appr_actionlogs 
WHERE document_id = :doc_id AND actionlog_type = 'RECEIVED';
```

### ✅ 올바른 방법: reception_status 사용
```sql
-- 접수대기 (해당 부서에서 아직 접수 안 한 문서)
SELECT * FROM v_appr_dept_received WHERE reception_status = 'WAITING';

-- 접수완료 (해당 부서에서 접수 처리 완료된 문서)
SELECT * FROM v_appr_dept_received WHERE reception_status = 'RECEIVED';

-- 접수반려
SELECT * FROM v_appr_dept_received WHERE reception_status = 'RECV_RETURNED';
```

---

## 관련 원본 테이블

| 테이블 | 역할 |
|--------|------|
| `go_dept_members` | 사용자-부서 소속 관계 |
| `go_appr_doc_subscriber_masters` | 부서 문서함 담당자 지정 |
| `go_appr_department_settings` | 부서별 전자결재 기능 활성화 설정 |
| `go_appr_doc_subscribers` | 문서 수신/참조 부서 매핑 |
| `go_appr_actionlogs` | 결재 액션 로그 (접수 완료 판단 핵심, 부서 컬럼 없음) |
| `go_users` | 사용자 기본 정보 |
| `go_departments` | 부서 정보 |

## 관련 뷰

| 뷰 | 용도 | 조합 키 |
|----|------|---------|
| `v_appr_user_accessible_depts` | 사용자별 접근 가능한 부서 목록 | `dept_id`, `employee_number` |
| `v_appr_dept_received` | 부서 수신함 문서 (부서별 독립 접수 상태 포함) | `dept_id` |
| `v_appr_dept_referenced` | 부서 참조함 문서 | `dept_id` |
| `v_appr_dept_completed` | 부서 완료함 문서 | `dept_id` |

---

## 데이터 현황 (2026-03 기준)

### v_appr_user_accessible_depts
- MEMBER: ~989건 (927명, 301개 부서)
- SUBSCRIBER_MASTER: ~166건 (115명, 49개 부서)

### go_appr_actionlogs 주요 타입
- RECEIVED: ~328,246건
- RECV_RETURNED: ~1,883건