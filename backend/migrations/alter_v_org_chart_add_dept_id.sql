-- v_org_chart 뷰에 부서ID 컬럼 추가
-- 목적: 조직도 계층 조회 시 형제 부서 간 정확한 구분을 위해 부서 고유 ID 필요
-- 영향: 기존 쿼리에 영향 없음 (컬럼 추가만, 기존 컬럼 변경 없음)
-- 요청일: 2026-03-10

CREATE OR REPLACE VIEW v_org_chart AS
WITH ranked_dept AS (
    SELECT dm.user_id,
        dm.department_id,
        dm.duty_id,
        dm.type,
        row_number() OVER (PARTITION BY dm.user_id ORDER BY (
            CASE dm.type
                WHEN 2 THEN 1
                WHEN 0 THEN 2
                ELSE 3
            END), dm.sort_order, dm.id) AS rn
    FROM go_dept_members dm
        JOIN go_departments d_1 ON dm.department_id = d_1.id AND d_1.deleted_at IS NULL
    WHERE dm.deleted_at IS NULL
)
SELECT u.id AS user_id,
    u.name AS "이름",
    u.status AS "상태",
    dc.ko_name AS "직책",
    d.id AS "부서ID",               -- ★ 추가된 컬럼
    d.name AS "부서",
    d.path AS "부서경로",
    up.job AS "직무",
    up.memo AS "메모_근무지"
FROM go_users u
    LEFT JOIN go_user_profiles up ON u.user_profile_id = up.id
    LEFT JOIN ranked_dept rd ON u.id = rd.user_id AND rd.rn = 1
    LEFT JOIN go_departments d ON rd.department_id = d.id
    LEFT JOIN go_domain_codes dc ON rd.duty_id = dc.id AND dc.code_type::text = 'DUTY'::text
WHERE u.deleted_at IS NULL AND u.status::text <> 'STOP'::text;

-- ai_reader 권한 재부여 (CREATE OR REPLACE 후 필요할 수 있음)
GRANT SELECT ON v_org_chart TO ai_reader;
