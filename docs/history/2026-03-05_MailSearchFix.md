# 2026-03-05 메일 검색 한국어 제목 매칭 + Inbox 하위폴더 포함

## 개요
메일 키워드 검색 시 한국어 제목이 매칭되지 않는 문제와, 받은편지함 조회 시 Inbox 하위폴더 메일이 누락되는 문제를 수정.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/data/jsp/lucid_mail.jsp | 수정 | search: v4 하이브리드 검색, inbox: 하위폴더 포함 |

## 상세 내용

### 1. 검색(search) — 하이브리드 2단계 검색 (v4)

**원인 (v3까지)**: 최근 500건만 fetch → Java MIME 디코딩 매칭. 오래된 메일이나 하위 폴더의 메일이 500건 밖에 있으면 검색 불가.

**v4 수정 — 2단계 하이브리드**:
1. **1차 SQL LIKE**: `msg_preview LIKE '%keyword%'`로 전체 메일함 검색 (건수 제한 없이 `limit`건 반환)
   - 미리보기 본문에 키워드가 있는 메일을 전 메일함에서 찾음
   - MIME 인코딩 무관 (preview는 평문 저장)
2. **2차 Java MIME**: 최근 1000건 fetch → `decodeMime()` 후 제목/발신자 `contains()` 매칭
   - 1차에서 못 찾은 제목-only 매칭 보완
   - 기존 500건 → 1000건으로 확대
3. **결과 병합**: `LinkedHashMap<uid_no, cols>` — uid_no 기준 중복 제거, SQL결과 우선

```
[키워드 입력]
    ├── 1차: SQL LIKE on msg_preview (전체 메일함, 제한 없음)
    │   → preview 본문에 키워드가 있는 메일 발견
    ├── 2차: Java MIME decode (최근 1000건)
    │   → 제목에만 키워드가 있는 메일 보완
    └── 병합 + 중복제거 → limit건 반환
```

**SQL injection 방지**: `keyword.replace("'", "''")` — SQLite CLI 사용이므로 prepared statement 불가, 단일따옴표 이스케이프로 대응.

### 2. 받은편지함(inbox) — Inbox 하위폴더 누락

**원인**: inbox 쿼리가 `folder_name = 'Inbox'`만 조회 → 메일 규칙으로 `Inbox.하위폴더`에 분류된 메일 누락.

**수정**: `unread` 쿼리와 동일하게 `(f.folder_name = 'Inbox' OR f.folder_name LIKE 'Inbox.%')` 적용.

## 결정 사항 및 주의점
- `lucid_mail.jsp`는 그룹웨어 서버에 배포된 파일. `backend/data/jsp/`는 로컬 참조본 → **서버 배포 필요**
- 1차 SQL LIKE는 전체 메일함 대상이므로 preview 본문 매칭은 메일 수에 관계없이 동작
- 2차 Java MIME 디코딩은 최근 1000건 한정 — 1000건 밖의 제목-only 매칭은 여전히 불가 (preview에도 없는 경우)
- inbox/unread/search 3개 액션 모두 하위폴더 포함으로 통일됨
