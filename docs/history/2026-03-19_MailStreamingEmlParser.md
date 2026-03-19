# 2026-03-19 메일 본문 스트리밍 파서 (5MB 제한 해제)

## 개요
.eml 파일 전체를 메모리에 로드하던 방식을 스트리밍 방식으로 전환하여, 첨부파일 크기와 무관하게 메일 본문을 추출할 수 있도록 개선.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/data/jsp/lucid_mail.jsp | 수정 | `extractBodyFromEml()` 스트리밍 방식 재작성, 헬퍼 3개 추가 |

## 상세 내용

### 문제
- `extractBodyFromEml()`이 `.eml` 파일 전체를 `byte[]`로 메모리에 로드
- OOM 방지를 위해 `file.length() > 5MB` 시 `"[파일 크기 초과 (5MB 제한)]"` 반환
- 첨부파일이 큰 메일(엑셀, 이미지 등)은 `.eml` 자체가 5MB 초과 → 본문 텍스트 추출 불가
- LLM이 이를 "첨부파일 크기 초과"로 사용자에게 안내하는 문제 발생

### 해결: 스트리밍 파서
파일 전체를 메모리에 올리지 않고, 헤더와 text 파트만 선택적으로 읽는 방식으로 전환:

1. **`extractBodyFromEml()`** — `BufferedInputStream`으로 헤더만 먼저 읽고, single-part이면 본문 200KB까지 읽기, multipart이면 `scanMultipartStream()` 호출
2. **`readStreamLine()`** — 스트림에서 한 줄 읽기 (CRLF/LF 처리, 1줄 최대 1MB 제한으로 바이너리 파트에서도 메모리 안전)
3. **`readStreamLimited()`** — single-part 본문용 제한 읽기
4. **`scanMultipartStream()`** — boundary 기반으로 파트 순회, `text/plain`과 `text/html` 파트만 버퍼링(각 최대 500KB), 첨부/이미지 파트는 읽고 즉시 폐기

### 메모리 사용량
- 기존: 파일 전체 크기 (최대 5MB, 동시 요청 시 N배)
- 변경: 헤더(~4KB) + 텍스트 파트(~수십KB) = **수십KB 고정** (파일 크기 무관)

### 기존 `parseMultipartBody()` 메서드
호출처가 없어졌으나, 코드에 잔존 (향후 정리 가능). 실행 경로에서 제외됨.

## 결정 사항 및 주의점
- JSP 파일은 그룹웨어 서버에 수동 배포 필요 (자동 배포 대상 아님)
- `readStreamLine()`은 `BufferedInputStream.mark(1)`을 사용하므로 반드시 BufferedInputStream으로 감싸야 함
- 바이너리 첨부(base64 아닌 raw binary)는 줄바꿈이 없을 수 있으나, boundary 앞의 CRLF로 줄 구분 가능
