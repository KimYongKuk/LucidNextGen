# 2026-03-05 Worker 마커 텍스트 노출 버그 수정

## 개요
`<!--WORKER:CorpRAGWorker-->` 같은 내부 마커가 간헐적으로 채팅 UI에 텍스트로 노출되는 버그를 수정. workerName을 텍스트 콘텐츠에 HTML 주석으로 삽입하는 방식에서, 메시지 객체의 별도 필드로 분리하여 근본적으로 해결.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `frontend/lib/types.ts` | 수정 | `ChatMessage` 타입에 `workerName?: string` 필드 추가 |
| `frontend/hooks/use-simple-chat.ts` | 수정 | 텍스트 마커 삽입 제거, `workerName`을 메시지 객체에 별도 저장 |
| `frontend/components/message.tsx` | 수정 | `message.workerName`을 `Response` 컴포넌트에 prop으로 전달 |
| `frontend/components/elements/response.tsx` | 수정 | `workerName` prop 수신, 레거시 텍스트 마커 fallback 유지 |

## 상세 내용

### 기존 방식 (문제)
1. `use-simple-chat.ts`에서 `intent_classified` 이벤트로 `workerName` 캡처
2. 텍스트 콘텐츠 앞에 `<!--WORKER:name-->` HTML 주석 마커 삽입
3. `response.tsx`에서 `^<!--WORKER:(\w+)-->` regex로 추출 후 제거
4. react-markdown이 HTML 주석을 텍스트로 렌더링하거나, React 렌더링 타이밍에 따라 간헐적 노출

### 새로운 방식 (해결)
1. `ChatMessage` 타입에 `workerName?: string` 필드 추가
2. `use-simple-chat.ts`에서 텍스트 마커 삽입 제거, 대신 `msg.workerName` 설정
3. `message.tsx`에서 `message.workerName`을 `Response`에 prop으로 전달
4. `response.tsx`에서 prop으로 `workerName` 수신 (레거시 텍스트 마커도 fallback으로 처리)

### 하위 호환
- DB에서 로드된 기존 메시지에는 `workerName` 필드가 없으므로 `undefined` → 모든 아티팩트 패턴 활성화 (기존 동작 유지)
- `response.tsx`에서 레거시 `<!--WORKER:-->` 마커도 여전히 fallback으로 처리하므로, 혼합 버전에서도 안전

### 부수 수정
- `use-simple-chat.ts`: FOLLOW_UP 마커 regex의 `/s` 플래그를 `[\s\S]`로 대체 (ES2018 미만 타겟 호환)

## 결정 사항 및 주의점
- 텍스트 콘텐츠에 내부 마커를 삽입하는 패턴은 본질적으로 렌더링 누출 위험이 있으므로, 메타데이터는 항상 별도 채널로 전달하는 것이 안전
- `memo` 비교 함수에 `workerName` prop 추가하여 변경 시 재렌더링 보장
