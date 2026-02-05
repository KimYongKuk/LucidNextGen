# 일정(Calendar) 관련 데이터베이스 스키마 가이드 v2

## 개요
이 문서는 캘린더 및 일정 관리를 위한 주요 테이블들의 스키마와 관계를 정의합니다.

---

## ⚠️ 중요: 반복 일정(Recurring Events) 처리 방법

### 반복 일정의 구조
반복 일정은 **원본 일정(Master Event)** 하나만 데이터베이스에 저장되며, 개별 발생 인스턴스는 기본적으로 별도 레코드로 생성되지 않습니다.

#### 반복 일정 식별 방법
```sql
-- 원본 반복 일정 확인
SELECT * FROM go_calendar_events 
WHERE recurrence IS NOT NULL AND parent_id IS NULL

-- 특정 날짜의 반복 일정을 찾을 때 주의!
-- ❌ 잘못된 방법: start_time으로 특정 날짜만 조회
SELECT * FROM go_calendar_events 
WHERE start_time::date = '2025-10-16'

-- ✅ 올바른 방법: 반복 규칙을 포함하여 조회
SELECT * FROM go_calendar_events 
WHERE (start_time::date = '2025-10-16')
   OR (recurrence IS NOT NULL 
       AND start_time::date <= '2025-10-16' 
       AND (recur_until IS NULL OR recur_until::date >= '2025-10-16'))
```

#### 반복 규칙 해석
- `recurrence` 컬럼: RFC 5545 형식의 RRULE 저장
  - 예: `FREQ=WEEKLY;BYDAY=TH` → 매주 목요일
  - 예: `FREQ=DAILY;INTERVAL=2` → 2일마다
  - 예: `FREQ=MONTHLY;BYMONTHDAY=1` → 매월 1일
- `recur_until`: 반복 종료 날짜
- `ex_dates`: 제외할 날짜 목록 (쉼표로 구분)

#### 반복 일정의 예외 인스턴스
수정되거나 삭제된 개별 인스턴스만 별도 레코드로 생성됩니다:
```sql
-- 반복 일정의 예외 인스턴스 조회
SELECT * FROM go_calendar_events 
WHERE parent_id = :master_event_id
```

---

## 주요 테이블 스키마

### 1. go_calendars (캘린더)
**목적**: 사용자의 캘린더 정보 저장

**주요 컬럼**:
- `id` (bigint, PK): 캘린더 고유 식별자
- `name` (varchar): 캘린더 이름
- `type` (varchar): 캘린더 타입
- `color` (varchar): 캘린더 색상
- `default_calendar` (boolean): 기본 캘린더 여부
- `visibility` (varchar): 공개 범위
- `seq` (int): 정렬 순서
- `owner_id` (bigint, FK): 소유자 사용자 ID
- `company_id` (bigint, FK): 소속 회사 ID
- `access_target_id` (bigint): 접근 대상 ID
- `created_at` (timestamp): 생성 일시
- `updated_at` (timestamp): 수정 일시

**인덱스**:
- UNIQUE: (id)

---

### 2. go_calendar_events (일정/이벤트)
**목적**: 캘린더의 개별 일정 정보 저장

**주요 컬럼**:
- `id` (bigint, PK): 이벤트 고유 식별자
- `summary` (varchar, NOT NULL): 일정 제목
- `description` (text): 일정 설명
- `location` (varchar): 장소
- `start_time` (timestamp, NOT NULL): 시작 시간
- `end_time` (timestamp, NOT NULL): 종료 시간
- `time_type` (varchar, NOT NULL): 시간 타입 (TIMED/ALLDAY)
- `time_zone` (varchar): 시간대 (기본값: '+09:00')
- `type` (varchar, NOT NULL): 이벤트 타입
- `visibility` (varchar, NOT NULL): 공개 범위
- `phase` (varchar): 단계/상태
- `recurrence` (varchar): **반복 규칙 (RRULE)** ⭐
- `recur_count` (int): 반복 횟수
- `recur_until` (timestamp): **반복 종료일** ⭐
- `ex_dates` (varchar): **제외 날짜** ⭐
- `html_link` (varchar): HTML 링크
- `reference_id` (varchar): 참조 ID
- `creator_id` (bigint, FK): 생성자 사용자 ID
- `own_company_id` (bigint, FK): 소속 회사 ID
- `parent_id` (bigint, FK): **부모 이벤트 ID (반복 일정의 예외 인스턴스용)** ⭐
- `created_at` (timestamp): 생성 일시
- `updated_at` (timestamp): 수정 일시

**인덱스**:
- UNIQUE: (id)
- INDEX: (parent_id)

**반복 일정 관련 중요 사항**:
- `recurrence`가 NOT NULL이고 `parent_id`가 NULL → 원본 반복 일정
- `parent_id`가 NOT NULL → 반복 일정의 수정/삭제된 개별 인스턴스
- 정상적인 반복 인스턴스는 별도 레코드로 생성되지 않음

---

### 3. go_calendar_event_mappings (이벤트-캘린더 매핑)
**목적**: 이벤트와 캘린더 간의 다대다 관계 저장

**주요 컬럼**:
- `event_id` (bigint, PK): 이벤트 ID
- `calendar_id` (bigint, PK): 캘린더 ID

**인덱스**:
- UNIQUE: (event_id, calendar_id)
- INDEX: (calendar_id)

**관계**:
- go_calendar_event_mappings.event_id → go_calendar_events.id (N:1)
- go_calendar_event_mappings.calendar_id → go_calendars.id (N:1)

**중요**: 하나의 이벤트(반복 일정 포함)가 여러 사용자의 캘린더에 동시에 매핑될 수 있음

---

### 4. go_calendar_attendees (참석자)
**목적**: 일정의 참석자 정보 저장

**주요 컬럼**:
- `id` (bigint, PK): 참석자 고유 식별자
- `event_id` (bigint, FK): 이벤트 ID
- `user_id` (bigint, FK): 사용자 ID (내부 사용자)
- `name` (varchar): 참석자 이름
- `email` (varchar): 참석자 이메일
- `created_at` (timestamp): 생성 일시
- `updated_at` (timestamp): 수정 일시

**인덱스**:
- UNIQUE: (id)
- INDEX: (event_id)

**관계**:
- go_calendar_attendees.event_id → go_calendar_events.id (N:1)
- go_calendar_attendees.user_id → go_users.id (N:1)

---

## 일반적인 조회 패턴

### 1. 특정 사용자의 캘린더 목록 조회
```sql
SELECT 
    c.id,
    c.name,
    c.color,
    c.type,
    c.default_calendar,
    c.visibility,
    c.seq
FROM go_calendars c
WHERE c.owner_id = :user_id
  OR c.access_target_id = :user_id
ORDER BY c.seq, c.name
```

### 2. ⭐ 특정 기간의 일정 조회 (반복 일정 포함)
```sql
-- 방법 1: 단순 조회 (단일 일정 + 반복 일정 원본)
SELECT 
    e.id,
    e.summary,
    e.description,
    e.location,
    e.start_time,
    e.end_time,
    e.time_type,
    e.type,
    e.visibility,
    e.recurrence,
    e.recur_until,
    e.parent_id,
    c.name as calendar_name,
    c.color as calendar_color,
    u.name as creator_name
FROM go_calendar_events e
JOIN go_calendar_event_mappings cem ON e.id = cem.event_id
JOIN go_calendars c ON cem.calendar_id = c.id
LEFT JOIN go_users u ON e.creator_id = u.id
WHERE c.owner_id = :user_id
  AND (
    -- 단일 일정 또는 반복 일정의 예외 인스턴스
    (e.start_time >= :start_date AND e.start_time <= :end_date)
    OR
    -- 원본 반복 일정 (조회 기간과 겹치는 것만)
    (e.recurrence IS NOT NULL 
     AND e.parent_id IS NULL
     AND e.start_time <= :end_date
     AND (e.recur_until IS NULL OR e.recur_until >= :start_date))
  )
ORDER BY e.start_time
```

### 3. ⭐ 특정 사용자의 특정 날짜 일정 조회
```sql
-- 특정 날짜(예: 2025-10-16)의 모든 일정
SELECT 
    e.id,
    e.summary,
    e.description,
    e.location,
    e.start_time::text as start_time,
    e.end_time::text as end_time,
    e.time_type,
    e.recurrence,
    e.recur_until::text as recur_until,
    e.parent_id,
    c.name as calendar_name
FROM go_calendar_events e
JOIN go_calendar_event_mappings cem ON e.id = cem.event_id
JOIN go_calendars c ON cem.calendar_id = c.id
WHERE c.owner_id = :user_id
  AND (
    -- 해당 날짜의 단일 일정
    e.start_time::date = :target_date
    OR
    -- 해당 날짜를 포함하는 반복 일정
    (e.recurrence IS NOT NULL 
     AND e.parent_id IS NULL
     AND e.start_time::date <= :target_date
     AND (e.recur_until IS NULL OR e.recur_until::date >= :target_date))
  )
ORDER BY e.start_time
```

### 4. 특정 제목의 일정 검색 (반복 일정 고려)
```sql
-- 제목으로 일정 검색
SELECT 
    e.id,
    e.summary,
    e.start_time::text as start_time,
    e.end_time::text as end_time,
    e.recurrence,
    e.recur_until::text as recur_until,
    e.parent_id,
    COUNT(cem.calendar_id) as shared_calendar_count
FROM go_calendar_events e
LEFT JOIN go_calendar_event_mappings cem ON e.id = cem.event_id
WHERE e.summary LIKE '%검색어%'
GROUP BY e.id, e.summary, e.start_time, e.end_time, e.recurrence, e.recur_until, e.parent_id
ORDER BY e.start_time DESC
```

### 5. 반복 일정의 상세 정보 및 공유자 조회
```sql
-- 반복 일정이 공유된 모든 사용자 조회
SELECT 
    e.id,
    e.summary,
    e.start_time::text as start_time,
    e.end_time::text as end_time,
    e.recurrence,
    e.recur_until::text as recur_until,
    c.id as calendar_id,
    c.name as calendar_name,
    u.id as user_id,
    u.name as user_name,
    u.login_id as user_login_id
FROM go_calendar_events e
JOIN go_calendar_event_mappings cem ON e.id = cem.event_id
JOIN go_calendars c ON cem.calendar_id = c.id
LEFT JOIN go_users u ON c.owner_id = u.id
WHERE e.id = :event_id
ORDER BY u.name
```

### 6. 일정의 참석자 조회
```sql
SELECT 
    a.id,
    a.name,
    a.email,
    u.id as user_id,
    u.name as user_name,
    u.employee_number
FROM go_calendar_attendees a
LEFT JOIN go_users u ON a.user_id = u.id
WHERE a.event_id = :event_id
ORDER BY a.name
```

### 7. 반복 일정과 예외 인스턴스 함께 조회
```sql
-- 원본 반복 일정
SELECT 
    e.id,
    e.summary,
    e.start_time::text as start_time,
    e.end_time::text as end_time,
    e.recurrence,
    e.recur_count,
    e.recur_until::text as recur_until,
    e.ex_dates,
    'MASTER' as instance_type
FROM go_calendar_events e
WHERE e.id = :event_id
  AND e.recurrence IS NOT NULL

UNION ALL

-- 예외 인스턴스 (수정/삭제된 발생)
SELECT 
    e.id,
    e.summary,
    e.start_time::text as start_time,
    e.end_time::text as end_time,
    e.recurrence,
    e.recur_count,
    e.recur_until::text as recur_until,
    e.ex_dates,
    'EXCEPTION' as instance_type
FROM go_calendar_events e
WHERE e.parent_id = :event_id
ORDER BY start_time
```

---
