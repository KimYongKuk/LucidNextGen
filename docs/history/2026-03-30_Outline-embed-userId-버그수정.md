# 2026-03-30 Outline 임베드 userId anonymous 버그 수정

## 개요
Outline Wiki 임베드 채팅에서 사용자 로그가 "anonymous"로 기록되는 버그를 수정. `embed-chat.tsx`에서 URL 파라미터로 추출한 사번(`empno`)을 `useSimpleChat` 훅에 전달하지 않아 발생.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| frontend/hooks/use-simple-chat.ts | 수정 | `UseSimpleChatOptions`에 `userId` 옵션 추가, 우선순위: 외부주입 > SSO쿠키 > "anonymous" |
| frontend/components/embed-chat.tsx | 수정 | `userId` prop을 `useSimpleChat` 훅에 전달 |

## 상세 내용

### 문제 원인
1. `embed/page.tsx`에서 URL의 `empno` 파라미터로 사번을 정상 추출하여 `EmbedChat`에 prop으로 전달
2. `embed-chat.tsx`가 `userId` prop을 받지만 `useSimpleChat()` 호출 시 전달하지 않음
3. `useSimpleChat`은 `getUserId()`(SSO 쿠키)로 폴백하지만, iframe 환경에서는 쿠키 접근 불가
4. 최종적으로 "anonymous"가 백엔드에 전달되어 채팅 로그에 기록

### 수정 내용
- `UseSimpleChatOptions` 인터페이스에 `userId?: string` 필드 추가
- 훅 내부 userId 결정 로직: `externalUserId || getUserId() || "anonymous"` (외부 주입 최우선)
- `embed-chat.tsx`에서 `useSimpleChat({ ..., userId })` 전달

## 결정 사항 및 주의점
- 기존 `useSimpleChat` 사용처(일반 채팅)는 `userId` 옵션을 전달하지 않으므로 기존 동작(SSO 쿠키 기반)에 영향 없음
- Outline iframe 환경에서는 cross-origin 쿠키 정책으로 SSO 쿠키 접근이 불가능하므로 URL 파라미터 방식이 유일한 방법
