# Database Schema

LFChatbot 프로젝트의 MySQL 데이터베이스 스키마 정의서입니다.

## 테이블 구조

### 1. chat_sessions

채팅 세션 메타데이터를 저장합니다.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| session_id | VARCHAR(36) | PRIMARY KEY | 세션 UUID |
| user_id | VARCHAR(50) | NOT NULL | 사용자 ID |
| title | VARCHAR(255) | | 채팅 제목 |
| chat_mode | VARCHAR(20) | | 채팅 모드 (normal/corp) |
| message_count | INT | DEFAULT 0 | 메시지 수 |
| workspace_id | INT | NULL, FK | 워크스페이스 참조 |
| is_pinned | BOOLEAN | DEFAULT FALSE | 고정 여부 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 생성일시 |
| updated_at | DATETIME | ON UPDATE CURRENT_TIMESTAMP | 수정일시 |

**인덱스:**
- `idx_user_id` (user_id)
- `idx_workspace_id` (workspace_id)
- `idx_created_at` (created_at)

**외래키:**
- `fk_chat_sessions_workspace`: workspace_id → workspaces(id) ON DELETE SET NULL

---

### 2. chat_log_new

채팅 메시지를 저장합니다.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INT | AUTO_INCREMENT, PRIMARY KEY | 메시지 ID |
| session | VARCHAR(36) | NOT NULL | 세션 ID |
| role | VARCHAR(20) | NOT NULL | 역할 (user/assistant) |
| content | TEXT | NOT NULL | 메시지 내용 |
| metadata | JSON | DEFAULT NULL | 이미지, 출처 등 메타데이터 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 생성일시 |

**인덱스:**
- `idx_session` (session)

---

### 3. workspaces

워크스페이스(작업 공간) 정보를 저장합니다.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INT | AUTO_INCREMENT, PRIMARY KEY | 워크스페이스 ID |
| uuid | VARCHAR(36) | NOT NULL, UNIQUE | 워크스페이스 UUID |
| user_id | VARCHAR(50) | NOT NULL | 소유자 ID |
| name | VARCHAR(100) | NOT NULL | 워크스페이스 이름 |
| description | TEXT | | 설명 |
| system_prompt | TEXT | | 커스텀 시스템 프롬프트 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 생성일시 |
| updated_at | DATETIME | ON UPDATE CURRENT_TIMESTAMP | 수정일시 |

**인덱스:**
- `idx_uuid` (uuid)
- `idx_user_id` (user_id)

---

### 4. youtube_summaries

YouTube 요약 캐시를 저장합니다.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INT | AUTO_INCREMENT, PRIMARY KEY | 요약 ID |
| video_id | VARCHAR(20) | NOT NULL, UNIQUE | YouTube 비디오 ID |
| title | TEXT | NOT NULL | 비디오 제목 |
| original_link | VARCHAR(500) | NOT NULL | 원본 URL |
| summary | TEXT | NOT NULL | 요약 내용 |
| insight | TEXT | | 핵심 인사이트 |
| keywords | JSON | | 키워드 배열 |
| segments | JSON | | 타임스탬프별 세그먼트 |
| user_id | VARCHAR(100) | | 요청자 ID |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 생성일시 |
| updated_at | DATETIME | ON UPDATE CURRENT_TIMESTAMP | 수정일시 |

**인덱스:**
- `idx_video_id` (video_id)
- `idx_user_id` (user_id)
- `idx_created_at` (created_at)

---

### 5. anonymous_feedback

익명 피드백을 저장합니다.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INT | AUTO_INCREMENT, PRIMARY KEY | 피드백 ID |
| feedback_id | VARCHAR(36) | NOT NULL, UNIQUE | 클라이언트 UUID |
| message | TEXT | NOT NULL | 피드백 내용 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 생성일시 |

**인덱스:**
- `idx_feedback_id` (feedback_id)
- `idx_created_at` (created_at DESC)

---

## ER 다이어그램

```
┌─────────────────┐       ┌─────────────────┐
│   workspaces    │       │  chat_sessions  │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │◄──────│ workspace_id(FK)│
│ uuid            │       │ session_id (PK) │
│ user_id         │       │ user_id         │
│ name            │       │ title           │
│ description     │       │ chat_mode       │
│ system_prompt   │       │ message_count   │
│ created_at      │       │ is_pinned       │
│ updated_at      │       │ created_at      │
└─────────────────┘       │ updated_at      │
                          └────────┬────────┘
                                   │
                                   │ session
                                   ▼
                          ┌─────────────────┐
                          │  chat_log_new   │
                          ├─────────────────┤
                          │ id (PK)         │
                          │ session         │
                          │ role            │
                          │ content         │
                          │ metadata        │
                          │ created_at      │
                          └─────────────────┘

┌─────────────────┐       ┌─────────────────┐
│youtube_summaries│       │anonymous_feedback│
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ video_id        │       │ feedback_id     │
│ title           │       │ message         │
│ original_link   │       │ created_at      │
│ summary         │       └─────────────────┘
│ insight         │
│ keywords        │
│ segments        │
│ user_id         │
│ created_at      │
│ updated_at      │
└─────────────────┘
```

---

## 마이그레이션 파일

| 파일 | 설명 |
|------|------|
| `migrations/add_metadata_column.sql` | chat_log_new에 metadata 컬럼 추가 |
| `migrations/add_message_count.py` | chat_sessions에 message_count 컬럼 추가 |
| `migrations/add_youtube_summaries.py` | youtube_summaries 테이블 생성 |
| `migrations/create_anonymous_feedback.sql` | anonymous_feedback 테이블 생성 |
| `scripts/init_project_db.py` | workspaces 테이블 초기 생성 |
| `scripts/add_pinned_column.py` | is_pinned 컬럼 추가 |

---

## 데이터베이스 설정

```
Engine: InnoDB
Charset: utf8mb4
Collation: utf8mb4_unicode_ci
```
