# 2026-03-20 브리핑 수신문서 접수대기 정확도 개선

## 개요
브리핑 팝업의 "수신문서" 섹션이 그룹웨어 전자결재 "접수대기" 탭과 일치하지 않는 문제를 수정. 3가지 근본 원인을 단계적으로 해결.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/services/notice_service.py | 수정 | 수신문서 쿼리 전면 개선 |
| backend/metadata/MCP_GW_APPR.md | 수정 | v_appr_dept_received 섹션 업데이트, accessible_depts 추가 |
| backend/metadata/MCP_GW_APPR_ACCESSIBLE.md | 추가 | 부서 문서함 접근 권한 및 수신 상태 가이드 |

## 상세 내용

### 문제 1: CANCEL/RETURN 문서가 최상단 표시
- **원인**: `appr_status != 'TEMPSAVE'`만 제외, NULL received_at이 DESC에서 최상단
- **수정**: 불필요 상태 제외 + `NULLS LAST` 정렬

### 문제 2: 단일 부서(dept_id)만 조회
- **원인**: `v_user_info_mapping`의 dept_id(소속 부서)만 사용
- **실제**: 사용자는 소속 부서 외에 "부서 문서함 담당자"로 지정된 타 부서 문서함도 접근 가능
- **수정**: `v_appr_user_accessible_depts` VIEW로 접근 가능 부서 목록 조회 후 `ANY($1)` 쿼리

### 문제 3: 접수 완료 문서가 "접수대기"에 포함
- **원인**: `is_assigned` 컬럼이 실제 접수 상태를 반영하지 않음 (레거시)
- **실제**: `go_appr_actionlogs` 테이블의 `RECEIVED` 액션으로 접수 완료 판단
- **수정**: VIEW에 `reception_status` 컬럼 추가 (DBA), 쿼리에서 `reception_status = 'WAITING'` 필터 사용

### 최종 쿼리 구조
```python
# 1. 접근 가능 부서 조회
dept_rows = await conn.fetch("""
    SELECT DISTINCT dept_id FROM v_appr_user_accessible_depts
    WHERE employee_number = $1 AND use_reception = true
""", employee_number)

# 2. 접수대기 문서 조회
rows = await conn.fetch("""
    SELECT doc_id, title, ... FROM v_appr_dept_received
    WHERE dept_id = ANY($1) AND reception_status = 'WAITING'
    ORDER BY received_at DESC NULLS LAST LIMIT 3
""", dept_ids)
```

### VIEW 변경 사항 (DBA 적용)
- `v_appr_dept_received`: `is_received`, `received_by_name`, `received_confirmed_at`, `reception_status` 컬럼 추가
- `v_appr_user_accessible_depts`: 신규 VIEW (MEMBER + SUBSCRIBER_MASTER 기반)

## 결정 사항 및 주의점
- `is_assigned` 컬럼은 레거시로 접수 판단에 사용 금지 — `reception_status` 사용
- 상위 부서라고 자동 접근 불가, 반드시 `go_appr_doc_subscriber_masters`에 담당자 지정 필요
- `reception_status` 값: WAITING(접수대기), RECEIVED(접수완료), RECV_RETURNED(접수반려)