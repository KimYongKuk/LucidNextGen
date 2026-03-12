# 2026-03-12 Bedrock 리전 폴백 (Region Fallback)

## 개요
AWS Bedrock 일일 토큰 한도(~5M) 초과 시 us-east-1(cross-region)에서 us-west-2(on-demand)로 자동 전환하는 리전 폴백 시스템 구현. 쓰로틀링 감지 기반 반응형 전환 + 쿨다운 후 자동 복구.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/core/region_fallback.py` | 신규 | RegionFallbackManager 싱글톤 — 폴백 상태 관리, 모델 ID 변환, 쿨다운 자동 복구 |
| `backend/app/services/bedrock_service.py` | 수정 | primary/fallback 2개 boto3 client, 리전별 model ID 자동 변환 |
| `backend/app/agents/workers/base_worker.py` | 수정 | ChatBedrockConverse에 region_name 파라미터 동적 전달 |
| `backend/app/agents/intent_classifier.py` | 수정 | 싱글톤 LLM 리전 변경 시 재생성 (_ensure_correct_region) |
| `backend/.env` | 수정 | AWS_FALLBACK_REGION, REGION_FALLBACK_COOLDOWN_SEC 추가 |

## 상세 내용

### 폴백 흐름
```
[요청] → us-east-1 (us.anthropic.* cross-region)
         ↓ 쓰로틀링 (모든 모델+리트라이 소진)
[RegionFallbackManager] activate_fallback()
         ↓
[다음 요청부터] → us-west-2 (anthropic.* on-demand, 별도 quota)
         ↓ 다음 날 자정 (UTC 00:00 = KST 09:00) — AWS 일일 한도 리셋 시점
[자동 복구] → us-east-1로 복귀
```

### 모델 ID 변환
- cross-region: `us.anthropic.claude-sonnet-4-6` → on-demand: `anthropic.claude-sonnet-4-6`
- `us.`, `eu.`, `apac.`, `global.` prefix 자동 제거

### 영향 범위
- **BedrockService**: `self.client` property가 폴백 상태에 따라 적절한 boto3 client 반환
- **Workers (BaseWorker)**: 요청마다 LLM 생성 시 `region_name` 동적 결정
- **IntentClassifier**: 싱글톤이므로 `_ensure_correct_region()`으로 상태 변경 감지 후 LLM 재생성
- **Fallback client**: lazy 생성 — 폴백이 한 번도 발생하지 않으면 client 생성 비용 없음

### 환경변수
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AWS_FALLBACK_REGION` | `us-west-2` | 폴백 리전 |
| `ADMIN_ALERT_EMAIL` | (비어있음) | 폴백 전환/복구 시 알림 메일 수신 주소 |

### 관리자 메일 알림
- 폴백 활성화/복구 시 `ADMIN_ALERT_EMAIL`로 자동 메일 발송
- `_send_fallback_notification()` — 별도 `threading.Thread`에서 발송 (메인 요청 지연 없음)
- 기존 `EmailService` 싱글톤 재사용 (SMTP 설정 공유)
- 메일 내용: 발생 시각(KST), 전환 방향, 원인, 복구 예정 시각

## 결정 사항 및 주의점
- **반응형 전환**: 쓰로틀링 에러 발생 시에만 폴백 (선제형 X) — 단순하고 안정적
- **자정 복구**: AWS 일일 한도는 UTC 자정에 리셋되므로, UTC 00:00 (KST 09:00)에 primary 자동 복귀
- **cross-region vs on-demand**: `us.*` prefix 모델은 US 내 cross-region quota, prefix 없는 모델은 리전별 on-demand quota — 별도 한도
- **us-west-2 모델 접근**: Bedrock 콘솔에서 해당 리전의 모델 access 사전 활성화 필수
- **수동 복구**: `reset_to_primary()` 메서드로 즉시 primary 복귀 가능 (한도 증가 등 상황)
