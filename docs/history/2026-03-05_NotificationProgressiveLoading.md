# 2026-03-05 알림 모달 로딩 개선

## 개요
알림 모달(Today's Briefing)이 모든 데이터를 기다린 후에야 표시되던 구조를, 모달을 즉시 열고 로딩 UI를 보여준 뒤 전체 데이터 준비 완료 시 한꺼번에 표시하는 방식으로 변경. 타이핑 애니메이션 추가, 섹션별 건수 3건 제한.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/api/routes/board.py` | 추가 | `/fast` (공지+결재), `/mail` (메일) 2개 엔드포인트 신설 |
| `backend/app/services/notice_service.py` | 수정 | 전 섹션 LIMIT 5 → 3으로 변경 |
| `frontend/lib/api/notifications.ts` | 추가 | `fetchFastNotifications`, `fetchMailNotifications` 함수 |
| `frontend/components/notice-toast/notice-toast-provider.tsx` | 수정 | `Promise.all` 병렬 fetch, `isDataReady` 단일 플래그, 요약 트리거 분리 |
| `frontend/components/notice-toast/notice-modal.tsx` | 수정 | 타이핑 애니메이션, 로딩 인디케이터, 섹션 순서 변경 (공지→메일→전자결재) |

## 상세 내용

### 백엔드: 엔드포인트 분리 + 건수 제한

기존 `/api/v1/notifications/today`(전체 통합) 유지 + 2개 신규:

- **`GET /fast?user_id=X`**: 공지사항 + 결재(미결/수신/참조) — PostgreSQL만, ~200ms
- **`GET /mail?user_id=X`**: 읽지 않은 메일 — JSP HTTP 호출, ~2-10s
- 모든 쿼리 LIMIT 5 → 3으로 변경

### 프론트엔드: 즉시 모달 + 전체 로딩 후 표시

**새 플로우:**
```
페이지 로드 → 모달 즉시 오픈 (로딩 UI + 타이핑 애니메이션)
├─ fetchFast + fetchMail 병렬 실행 (Promise.all)
└─ 둘 다 완료 → 전체 컨텐츠 한꺼번에 표시 → AI 요약 스트리밍 시작
```

- **타이핑 애니메이션**: "Today's Briefing" 제목이 한 글자씩 타이핑되며 등장 (50ms/글자), 커서 깜빡임 효과
- **로딩 인디케이터**: 데이터 로딩 중 Loader2 스피너 + "공지사항, 메일, 전자결재를 확인하고 있습니다..."
- **섹션 순서**: 공지 → 메일 → 전자결재 (기존 공지→메일→전자결재 유지)
- **`isDataReady`**: 단일 boolean 플래그로 전체 로딩 완료 감지

## 결정 사항 및 주의점
- 기존 `/today` 엔드포인트는 하위 호환을 위해 유지 (향후 정리 가능)
- 요약 스트리밍은 반드시 모든 데이터 도착 후 시작 (전체 맥락 필요)
- `isDismissedToday()` 체크는 모달 오픈 전에 수행하여 기존 동작 유지
- 건수 3건은 notice_service.py의 LIMIT + 슬라이싱에서 제한 (프론트 변경 없음)
