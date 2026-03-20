# 전자결재 뷰 사용 가이드

> ⚠️ **필수**: 모든 쿼리 실행 전 `SET DateStyle = 'ISO, YMD';` 실행.

## 사용자 식별
뷰 조회 전 반드시 `get_user_approval_info` 도구 호출하여 `user_id`, `login_id`, `dept_id` 확인.
> ⚠️ `execute_approval_query`는 `v_appr_*` 뷰만 접근 가능. 내부 테이블 직접 조회 금지.
> ⚠️ `employee_number`(사번)와 `login_id`(결재 시스템 ID)는 **다른 값**. 뷰 조회 시 반드시 `login_id` 사용.

## 공통 컬럼 (모든 뷰)
| 컬럼 | 설명 |
|------|------|
| doc_id | 문서 ID |
| title | 문서 제목 |
| form_name | 양식명 |
| drafted_at | 기안 일시 |
| doc_body | 문서 본문 HTML. ⚠️ **단건 상세(doc_id 지정) 시에만 SELECT. 목록 조회 시 제외. SELECT * 금지** |

아래 각 뷰 설명에서는 공통 컬럼을 생략하고 **추가 컬럼만** 기술.

---

### 1. v_appr_user_drafted (개인 기안함)
내가 기안한 문서. 필터: `login_id`/`user_id`
추가 컬럼: `doc_num`, `appr_status`, `doc_status`, `drafter_name`, `drafter_dept_name`, `is_emergency`, `completed_at`
```sql
SELECT doc_id, title, form_name, appr_status, drafted_at
FROM v_appr_user_drafted
WHERE login_id = 'wg0403' AND appr_status != 'TEMPSAVE'
ORDER BY drafted_at DESC LIMIT 10;
-- 단건 본문 조회
SELECT doc_id, title, form_name, appr_status, drafted_at, doc_body
FROM v_appr_user_drafted WHERE login_id = 'wg0403' AND doc_id = 12345;
```

### 2. v_appr_user_pending (개인 결재 대기함)
내 차례에서 결재/합의 대기중인 문서. 필터: `login_id`/`user_id`
추가 컬럼: `drafter_name`, `drafter_dept_name`, `is_emergency`, `activity_type`(APPROVAL=결재/AGREEMENT=합의), `activity_status`(항상 WAITING)
```sql
SELECT doc_id, title, form_name, drafter_name, activity_type, drafted_at
FROM v_appr_user_pending WHERE login_id = 'wg0403'
ORDER BY drafted_at ASC;
-- 건수
SELECT COUNT(*) AS pending_count FROM v_appr_user_pending WHERE login_id = 'wg0403';
```

### 3. v_appr_user_approved (개인 결재 완료함)
내가 결재/합의 완료한 문서. 필터: `login_id`/`user_id`
추가 컬럼: `appr_status`, `doc_status`, `drafter_name`, `drafter_dept_name`, `activity_type`(APPROVAL/AGREEMENT), `completed_at`, `approved_at`(내 결재 시점, actionlogs 기반)
> ⚠️ `approved_at` 정렬 시 `NULLS LAST` 추가 권장 (극소수 NULL 가능)
```sql
SELECT doc_id, title, form_name, drafter_name, activity_type, approved_at
FROM v_appr_user_approved WHERE login_id = 'wg0403'
ORDER BY approved_at DESC NULLS LAST LIMIT 10;
-- 기간별 건수
SELECT COUNT(*) FROM v_appr_user_approved
WHERE login_id = 'wg0403' AND approved_at >= '2026-02-17';
```

### 4. v_appr_user_referenced (개인 참조함)
나에게 참조 지정된 문서. 필터: `login_id`/`user_id`
추가 컬럼: `appr_status`, `drafter_name`, `drafter_dept_name`, `is_read`(읽음 여부), `received_at`, `read_at`
```sql
SELECT doc_id, title, form_name, drafter_name, is_read, drafted_at
FROM v_appr_user_referenced WHERE login_id = 'wg0403'
ORDER BY drafted_at DESC LIMIT 10;
-- 안 읽은 참조
SELECT doc_id, title, drafter_name, drafted_at
FROM v_appr_user_referenced WHERE login_id = 'wg0403' AND is_read = false
ORDER BY drafted_at DESC;
```

### 5. v_appr_dept_completed (부서 기안 완료함)
부서원이 기안하여 결재 완료된 문서. 필터: `dept_id`
추가 컬럼: `doc_num`, `drafter_name`, `drafter_dept_name`, `dept_id`, `dept_name`, `completed_at`
```sql
SELECT doc_id, title, form_name, drafter_name, drafted_at, completed_at
FROM v_appr_dept_completed WHERE dept_id = 507
ORDER BY completed_at DESC LIMIT 10;
```

### 6. v_appr_dept_received (부서 수신함)
다른 부서에서 우리 부서로 수신된 문서. 필터: `dept_id`
추가 컬럼: `appr_status`, `doc_status`, `drafter_name`, `drafter_dept_name`, `dept_id`, `dept_name`, `is_assigned`(⚠️ 레거시, 접수 판단에 사용 금지), `is_reception_returned`(접수 반려), `reception_return_comment`, `received_at`, **`reception_status`**(WAITING/RECEIVED/RECV_RETURNED/기타), **`is_received`**(접수 완료 여부), **`received_by_name`**(접수 처리자), **`received_confirmed_at`**(접수 처리 시점)
> ⚠️ **`is_assigned` 사용 금지**: `is_assigned=false`인데 실제 접수 완료된 문서가 존재. 반드시 `reception_status` 사용.
> ⚠️ **부서별 독립 접수**: 동일 문서가 여러 부서에 수신될 때, 각 부서는 독립적으로 접수 처리. A부서 접수 완료해도 B부서는 여전히 WAITING. `reception_status`는 해당 수신부서 기준으로 정확히 판단됨.
> ⚠️ **부서 접근 권한**: 사용자는 소속 부서 외에 담당자 지정된 부서 문서함도 접근 가능. `v_appr_user_accessible_depts` 참조.
```sql
-- 접수 대기
SELECT doc_id, title, form_name, drafter_name, drafted_at
FROM v_appr_dept_received WHERE dept_id = 507 AND reception_status = 'WAITING'
ORDER BY received_at DESC NULLS LAST LIMIT 10;
-- 접수 완료
SELECT doc_id, title, drafter_name, received_by_name, received_confirmed_at
FROM v_appr_dept_received WHERE dept_id = 507 AND reception_status = 'RECEIVED'
ORDER BY received_confirmed_at DESC LIMIT 10;
-- 사용자 접근 가능한 모든 부서 수신 접수대기
SELECT r.doc_id, r.title, r.drafter_name, r.received_at
FROM v_appr_dept_received r
JOIN v_appr_user_accessible_depts a ON r.dept_id = a.dept_id
WHERE a.employee_number = 'A2304013' AND a.use_reception = true
  AND r.reception_status = 'WAITING'
ORDER BY r.received_at DESC NULLS LAST LIMIT 10;
```

### 6-1. v_appr_user_accessible_depts (부서 문서함 접근 권한)
사용자별 접근 가능한 부서 문서함 목록. 필터: `employee_number`
컬럼: `user_id`, `user_name`, `employee_number`, `dept_id`, `dept_name`, `dept_code`, `dept_path`, `access_type`(MEMBER/SUBSCRIBER_MASTER), `use_reception`, `use_doc_folder`, `use_official_doc_send`
> 상세 가이드: `MCP_GW_APPR_ACCESSIBLE.md` 참조
```sql
SELECT dept_id, dept_name, access_type, use_reception
FROM v_appr_user_accessible_depts WHERE employee_number = 'A2304013'
ORDER BY access_type, dept_name;
```

### 7. v_appr_dept_referenced (부서 참조함)
부서에 참조 지정된 문서. 필터: `dept_id`
추가 컬럼: `appr_status`, `doc_status`, `drafter_name`, `drafter_dept_name`, `dept_id`, `dept_name`, `completed_at`
```sql
SELECT doc_id, title, form_name, drafter_name, drafter_dept_name, drafted_at
FROM v_appr_dept_referenced WHERE dept_id = 507
ORDER BY drafted_at DESC LIMIT 10;
```

### 8. v_appr_doc_progress (결재 병목 분석)
내가 기안한 진행중 문서가 누구한테 멈춰있는지. 필터: `drafter_login_id`/`drafter_id`
추가 컬럼: `drafter_login_id`, `drafter_name`, `is_emergency`, `waiting_approver`, `waiting_dept`, `waiting_activity_type`(APPROVAL/AGREEMENT), `days_pending`(경과 일수, NOW() 실시간 계산)
> ⚠️ `days_pending`은 기안일~현재 경과일. 결재선 중간 단계 시간도 포함.
```sql
SELECT doc_id, title, waiting_approver, waiting_dept,
       waiting_activity_type, days_pending, drafted_at
FROM v_appr_doc_progress WHERE drafter_login_id = 'wg0403'
ORDER BY days_pending DESC;
-- 3일 초과 대기
SELECT doc_id, title, waiting_approver, days_pending
FROM v_appr_doc_progress
WHERE drafter_login_id = 'wg0403' AND days_pending > 3
ORDER BY days_pending DESC;
```

### 9. v_appr_user_redrafted (재기안 문서)
반려 후 재기안한 문서. 필터: `login_id`/`user_id`
추가 컬럼: `appr_status`, `doc_status`, `drafter_name`, `completed_at`, `last_redraft_at`, `redraft_count`
```sql
SELECT doc_id, title, form_name, appr_status, last_redraft_at, redraft_count
FROM v_appr_user_redrafted WHERE login_id = 'wg0403'
ORDER BY last_redraft_at DESC;
```

---

## 상태값 참고

**appr_status**: APPROVAL(결재완료), TEMPSAVE(임시저장), INPROGRESS(진행중), RETURN(반려), CANCEL(취소)
**doc_status**: COMPLETE(완료), TEMPSAVE(임시저장), RECEIVED(접수됨), RECV_WAITING(접수대기), RETURN(반려)
**activity_type**: DRAFT(기안), APPROVAL(결재), AGREEMENT(합의), CHECK(확인), INSPECTION(검토)

---

## 성능 주의사항
1. **WHERE 필수**: `login_id`/`user_id`/`dept_id` 없이 전체 조회 금지
2. **LIMIT 10~50** 권장
3. **날짜 범위** 추가 권장
4. **DateStyle 필수**: `SET DateStyle = 'ISO, YMD';`
> ⚠️ **doc_body**: 최대 ~76KB HTML. 목록 조회 시 반드시 제외, 단건(doc_id 지정) 시에만 포함. `SELECT *` 절대 금지.

## 권한 범위
- **개인 뷰** (v_appr_user_*): 본인 데이터만. login_id/user_id 필터
- **부서 뷰** (v_appr_dept_*): 부서 문서함 단위 조회. dept_id 필터
  - 사용자의 접근 가능 부서 확인: `v_appr_user_accessible_depts` (소속 부서 + 담당자 지정 부서)
- 보안등급(극비) 열람 제한, 역할별 접근 차이는 뷰 미반영 -- 극비 문서 조회 시 주의
