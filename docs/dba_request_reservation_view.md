# DBA 요청: 예약 시스템 연동용 VIEW 생성

## 배경
Lucid AI 챗봇에서 그룹웨어(GO) 회의실 예약 기능을 연동합니다.
AI가 GO의 자산예약 REST API를 호출하는데, API에 필요한 사용자 식별자가 **GO 내부 user.id** (정수)입니다.
우리 시스템은 사용자를 **사번(employee_number)** 으로 식별하므로, 사번 → GO user.id 매핑 VIEW가 필요합니다.

## 기존 참고 VIEW
기존에 동일한 GO DB에 아래 VIEW를 생성해주신 바 있습니다:
```sql
-- 메일 연동용 (기 생성 완료)
CREATE VIEW v_mail_user_mapping AS
SELECT gu.employee_number, mu.message_store
FROM go_users gu
JOIN mail_user mu ON gu.login_id = mu.mail_uid
WHERE mu.message_store IS NOT NULL;
```

## 요청 사항

### 1. VIEW 생성

```sql
CREATE VIEW v_reservation_user_mapping AS
SELECT
    gu.employee_number,          -- 사번 (우리 시스템 식별자)
    gu.id AS go_user_id,         -- GO 내부 user.id (예약 API 필요)
    gu.name AS user_name,        -- 사용자 이름 (로깅/검증용)
    gu.company_id,               -- 회사 ID (멀티 회사 구분)
    gu.position_name             -- 직급명 (표시용, 선택)
FROM go_users gu
WHERE gu.employee_number IS NOT NULL
  AND gu.employee_number != '';
```

> **참고**: `go_users` 테이블의 실제 컬럼명이 위와 다를 수 있습니다.
> 핵심은 **사번 → GO user.id** 매핑이며, 아래 컬럼이 필요합니다:
> - 사번 (employee_number 또는 유사 컬럼)
> - GO 내부 사용자 ID (PK, 정수형 — 예약 API에서 `user.id`로 사용되는 값)
> - 사용자 이름
> - (선택) 회사 ID, 직급명

### 2. 권한 부여

```sql
GRANT SELECT ON v_reservation_user_mapping TO ai_reader;
```

기존 `v_mail_user_mapping`과 동일한 `ai_reader` 계정에 SELECT 권한을 부여해주세요.

### 3. 검증 쿼리

VIEW 생성 후 아래 쿼리로 정상 동작을 확인할 수 있습니다:

```sql
-- 특정 사번으로 GO user.id 조회 (예: 사번 A2304013)
SELECT * FROM v_reservation_user_mapping WHERE employee_number = 'A2304013';

-- 전체 건수 확인
SELECT COUNT(*) FROM v_reservation_user_mapping;
```

기대 결과 예시:
| employee_number | go_user_id | user_name | company_id | position_name |
|-----------------|------------|-----------|------------|---------------|
| A2304013        | 1367       | 김용국    | 10         | 파트장        |

> **참고**: 사번(A2304013 형태)과 go_user_id(정수)는 별개의 값입니다.
> VIEW를 통해 정확히 매핑해야 합니다.
> **UPDATE**: DBA에 의해 VIEW 생성 완료 (2026-03-31). 927건 확인, ai_reader 권한 부여됨.

## 용도
- **읽기 전용**: SELECT만 수행 (INSERT/UPDATE/DELETE 없음)
- **호출 빈도**: 사용자당 1회 조회 후 프로세스 수명 캐싱 (부하 최소)
- **대상 DB**: GO 그룹웨어 PostgreSQL (v_mail_user_mapping과 동일 서버)
