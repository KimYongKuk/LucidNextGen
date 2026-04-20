# WORKS IT VOC 첨부파일 자동 등록 설계 (작업 중)

## 배경

기존 `register_works_voc` MCP 도구([2026-03-31 WORKS VOC 자동등록](history/2026-03-31_WORKS-VOC-자동등록.md))는 **텍스트 등록 + 담당자 배정 + 상태 전환**까지 자동화되어 있으나, **첨부파일은 지원하지 않음**. 실제 IT VOC는 스크린샷/로그파일/문서가 동반되는 경우가 잦아 "자동 등록"의 체감 완결성이 떨어짐.

이 문서는 Lucid 채팅에 업로드된 파일을 WORKS VOC 등록 시 함께 밀어넣는 기능 추가를 위한 설계 기록이다.

## 검토한 대안

| # | 방식 | 판단 |
|---|------|------|
| 1 | 링크 리다이렉트 (등록만 자동, 첨부는 Works에서 수동) | 가능하지만 "자동화 체감" 깨짐. fallback 용도로만 유효. |
| 2 | Daou 공개 OpenAPI(`/public/v1/works`) 활용 | **불가** — 파일/첨부 컴포넌트 미지원. 월 1,500회 제한(본 프로젝트는 월 ~1,000건으로 한도 내이긴 함). 응답에 생성된 ID/URL 없음. |
| 3 | 공개 API + 첨부 업로드 위젯 (등록 후 Lucid 채팅에 드래그앤드롭 위젯) | 공개 API에 첨부 엔드포인트 자체가 없어 불가. |
| 4 | **내부 API 리버스 엔지니어링** (등록 + 첨부 한 번에) | **채택** — 기존 SSO 리버싱 자산 재활용 가능, 완전 자동화. |

## 채택안: 내부 API 리버스 엔지니어링

### 포착한 API 플로우 (applet 1445 테스트앱 기준)

**Step 1: 파일 업로드**
```
POST https://lfon.landf.co.kr/api/file?GOSSOcookie=<SSO쿠키>
Content-Type: multipart/form-data
Body: file=<바이너리>

Response: { id: null, path: "/202616/19FE9FF2...", name: "filename.docx", hostId: "TMUzA..." }
```

**Step 2: VOC 등록 (첨부 메타 embed)**
```
POST https://lfon.landf.co.kr/api/works/applets/934/docs
Content-Type: application/json
Cookie: GOSSOcookie=...

Body:
{
  "appletId": "934",
  "values": {
    ...기존 필드들...,
    "_14v07o8vj": [   ← 첨부 필드 (1445 기준, 934는 확인 필요)
      {
        "id": null,
        "path": "/202616/19FE9FF2...",
        "name": "filename.docx",
        "hostId": "TMUzA..."
      }
    ]
  },
  ...body 최상위에도 values의 필드가 중복됨 (브라우저 전송 형태 그대로 유지 권장)...
  "subFormId": "0",
  "privateFlag": false
}
```

### 기존 구현에서 재활용 가능한 자산

`register_works_voc` (works_it_mcp_server.py:489)에 이미 구축된 부분:

- **SSO 쿠키 자동 획득** — `LFON_SSO_USERNAME/PASSWORD`로 로그인, 프로세스 수명 캐싱, 만료 시 재로그인
- **applet 934 필드 매핑** — `_8uzx0pk1u`(담당자), `_awrf64ysv`(회사), `_o9nnudfsi`(시스템), `_njwhedh92`(부서) 등
- **body 구조 및 중복키 형식** — 운영 검증됨
- **담당자/부서 객체 조립** — `v_user_info_mapping` 뷰 기반
- **상태 전환** — 접수(2545) → 담당자지정(2619) 2단계 PUT
- **시스템 → 담당부서 매핑 테이블**
- **보안 래핑** — `prepare_tools()`에서 employee_number 강제 주입
- **OpenAPI 폴백**

즉 **남은 리버싱은 "첨부 필드 ID 한 개 확보 + 파일 업로드 호출 한 함수 추가"** 수준.

## 내일 할 작업

### 0. 선행 확인 (필수)

- [ ] **applet 934의 첨부 필드 ID 확인**
  - 캡처한 `_14v07o8vj`는 테스트 applet **1445** 기준.
  - applet 생성 시 필드 ID가 랜덤 부여되므로 934와 동일 보장 없음.
  - 방법 A: 운영 applet 934에서 IT VOC 작성 시 DevTools로 `/api/works/applets/934/docs` 요청 캡처하여 첨부 필드 키 확인.
  - 방법 B: Works 관리 > applet 934 > 연동항목 관리에서 첨부 필드 파라미터명 확인.

### 1. 파일 업로드 헬퍼 추가

파일: `backend/app/mcp_servers/works_it_mcp_server.py`

```python
async def _upload_file_to_works(sso_cookie: str, file_path: str, file_name: str) -> dict:
    """
    WORKS 내부 파일 업로드 API 호출.
    Returns: {id, path, name, hostId}
    """
    url = f"{LFON_BASE_URL}/api/file?GOSSOcookie={sso_cookie}"
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f, "application/octet-stream")}
            resp = await client.post(
                url,
                files=files,
                cookies={"GOSSOcookie": sso_cookie},
                headers={
                    "Origin": LFON_BASE_URL,
                    "Referer": f"{LFON_BASE_URL}/app/works/applet/934/doc/new/0",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            resp.raise_for_status()
            return resp.json()
```

### 2. `register_works_voc` 파라미터 확장

```python
async def register_works_voc(
    employee_number: str = "auto",
    title: str,
    details: str,
    system_name: str,
    attachments: list[str] = None,  # NEW: Lucid 백엔드의 파일 경로 목록
) -> dict:
    ...
    # 기존 로직 (SSO 로그인, 담당자 조립 등)

    # NEW: 첨부 파일 업로드 + 메타 수집
    attach_meta = []
    if attachments:
        for fp in attachments:
            meta = await _upload_file_to_works(sso_cookie, fp, os.path.basename(fp))
            attach_meta.append(meta)

    # values에 첨부 필드 embed
    body["values"]["<934_첨부필드ID>"] = attach_meta   # 0번 단계에서 확인한 ID
    # 최상위에도 중복 embed (기존 body 구조 유지)
    body["<934_첨부필드ID>"] = attach_meta
```

### 3. Lucid → Works 파일 전달 경로 (결정됨)

**물리적 흐름:**
```
[사용자 업로드 시점]
  브라우저 → Lucid 백엔드 /api/upload → data/user_uploads/{today}/{user_id}/파일.ext
  (기존 플로우, 변경 없음)

[VOC 등록 시점]
  ITSupportWorker → (stdio) → works_it MCP 서버 (같은 머신 자식 프로세스, 디스크 공유)
    ├─ 디스크에서 파일 읽기 (MCP가 직접 접근)
    ├─ HTTPS multipart POST → Works /api/file (파일 바이너리 전송)
    └─ VOC 등록 body의 _14v07o8vj에 업로드 응답 embed
  → Works 서버가 자체 스토리지에 저장 + VOC 레코드와 연결
```

**핵심**: MCP 서버는 백엔드 자식 프로세스라 stdio로 파일 바이너리를 주고받을 필요 없음. LLM은 파일명만 넘기고 MCP가 `session_id`/`user_id`로 디스크에서 resolve.

### 4. 결정사항 (2026-04-20)

**Q1. `attachments` 파라미터 설계 → (b) 파일명 리스트 + 백엔드 resolve 채택**
- LLM은 `attachments: list[str]`로 파일명만 넘김 (예: `["error.log", "스크린샷.png"]`).
- `prepare_tools()`에서 session context 주입해 `data/user_uploads/{user_id}/` 이하에서만 resolve.
- 경로 탈출(`..`, 절대경로) 차단 — xlsx_worker `_validate_filepath` 패턴 재활용.
- 세션/사용자 소유 파일만 접근 가능. 다른 세션/사용자 파일 참조 불가.

**Q2. 자동 vs 명시 첨부 → 명시 첨부 (사용자 확인 플로우)**
- ITSupportWorker 시스템 프롬프트에 "세션에 업로드된 파일 목록"을 주입.
- LLM이 사용자에게 "아래 파일들도 첨부할까요? [파일A, 파일B]" 확인 후 명시 호출.
- ChromaDB 색인 목적으로 올린 파일이 의도치 않게 첨부되는 것 방지.

**Q3. 등록 성공 후 원본 처리 → 그대로 두기**
- `data/user_uploads/` 파일 라이프사이클 건드리지 않음.
- 기존 TTL/청소 정책에 맡김.
- 실패 시 재시도 여지도 보존.

### 5. 테스트 시나리오

- [ ] 첨부 없이 등록 (기존 동작 회귀 확인)
- [ ] 첨부 1개 등록 (이미지/문서)
- [ ] 첨부 여러 개 등록
- [ ] 큰 파일 (Works UI 제한 초과 케이스 — 에러 핸들링)
- [ ] SSO 쿠키 만료 중 업로드 (재로그인 후 재시도)
- [ ] 파일 업로드 성공 + VOC 등록 실패 시 업로드된 파일 처리 (고아 파일 — 일단 방치, Works 쪽 청소 정책에 맡김)

## 주의점 / 오픈 이슈

- **applet 934의 첨부 필드 ID 미확인** — 0번 선행 확인 필수.
- **본 방식은 리버스 엔지니어링** — Daou Works 업데이트로 깨질 수 있음. 정식 API 아님을 팀 내 공유.
- **공식 OpenAPI와 병행 유지** — 기존 폴백 경로(`register_works_voc` SSO 실패 시 OpenAPI) 유지. 다만 OpenAPI는 첨부 지원 안 하므로 폴백 시 "첨부는 수동" 안내 필요.
- **위젯 렌더링 방식은 폐기** — 내부 API에서 등록+첨부가 한 호출로 끝나므로 "Lucid 채팅 내 첨부 위젯" 컴포넌트는 불필요. 사용자가 대화 중 올린 파일을 그대로 embed하는 게 가장 자연스러움.
- **파일 경로 보안** — `attachments` 파라미터에 Lucid 업로드 디렉터리 바깥 경로가 들어오지 않도록 `prepare_tools()`에서 검증 필요 (xlsx_worker의 `_validate_filepath` 패턴 참고).
- **대용량 파일** — Works UI가 허용하는 크기 한도 미확인. 초과 시 `/api/file` 응답 확인해서 사용자에게 명확한 에러 반환.

## 참고

- 관련 기존 문서: [2026-03-31 WORKS VOC 자동등록](history/2026-03-31_WORKS-VOC-자동등록.md)
- SSO 쿠키 패턴: [jsp_sso_gosso_patch.md](jsp_sso_gosso_patch.md)
- 보안 래핑 패턴(object.__setattr__): approval_worker.py, xlsx_worker.py `prepare_tools()`
