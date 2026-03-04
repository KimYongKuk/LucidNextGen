# 2026-03-03 AWS Bedrock 리전별 모델 ID 및 Inference Profile 정리

## 개요
Sonnet 4.6 도입 검토 과정에서 AWS Bedrock의 리전별 모델 호출 방식(Inference Profile 프리픽스)을 조사하고 정리한 문서.

## Inference Profile 프리픽스 체계

AWS Bedrock에서 최신 모델(Sonnet 4 이상)은 **직접 모델 ID 호출(ON_DEMAND)이 불가**하고, 반드시 **Inference Profile**을 통해 호출해야 한다.

| 프리픽스 | 라우팅 범위 | 예시 |
|---------|-----------|------|
| `us.` | US 리전 전용 (us-east-1, us-east-2, us-west-2) | `us.anthropic.claude-sonnet-4-6` |
| `eu.` | EU 리전 전용 | `eu.anthropic.claude-sonnet-4-...` |
| `apac.` | 아시아-태평양 (서울+도쿄+싱가포르+시드니 등) | `apac.anthropic.claude-sonnet-4-20250514-v1:0` |
| `global.` | 전 세계 모든 가용 리전 | `global.anthropic.claude-sonnet-4-6` |
| (없음) ON_DEMAND | 호출한 리전에서만 실행 (리전 고정) | `anthropic.claude-3-5-sonnet-20240620-v1:0` |

### 핵심 포인트
- **`global.`은 서울 전용이 아님** — AWS가 부하/가용성에 따라 다른 리전으로 라우팅할 수 있음
- **`apac.`도 서울 전용이 아님** — 도쿄, 싱가포르, 시드니 등 APAC 전체에 걸쳐 라우팅
- **진짜 리전 고정**은 ON_DEMAND 타입만 가능하나, 최신 모델은 ON_DEMAND 미지원

## 서울 리전(ap-northeast-2) 모델별 사용 가능 프리픽스 (2026-03-03 기준)

### Sonnet 계열

| 모델 | ON_DEMAND (서울 고정) | `apac.` (아태) | `global.` (글로벌) | `us.` (미국) |
|------|:---:|:---:|:---:|:---:|
| **Sonnet 4.6** | X | X | O | X (us-east-1에서는 O) |
| **Sonnet 4.5** | X | X | O | X (us-east-1에서는 O) |
| **Sonnet 4** | X | O | O | X (us-east-1에서는 O) |
| **Sonnet 3.7** | X | O | X | X |
| **Sonnet 3.5 v2** | X | O | X | X |
| **Sonnet 3.5 (초기)** | **O** | O | X | X |

### Haiku / Opus 계열

| 모델 | ON_DEMAND (서울 고정) | `apac.` | `global.` |
|------|:---:|:---:|:---:|
| **Haiku 4.5** | X | X | O |
| **Haiku 3** | **O** | O | X |
| **Opus 4.6** | X | X | O |
| **Opus 4.5** | X | X | O |

## 실제 모델 ID 목록

### us-east-1 (미국 동부)
```
# Sonnet
us.anthropic.claude-sonnet-4-6                    # Sonnet 4.6 (US cross-region)
us.anthropic.claude-sonnet-4-5-20250929-v1:0      # Sonnet 4.5
us.anthropic.claude-sonnet-4-20250514-v1:0        # Sonnet 4
us.anthropic.claude-3-7-sonnet-20250219-v1:0      # Sonnet 3.7

# Haiku
us.anthropic.claude-haiku-4-5-20251001-v1:0       # Haiku 4.5 (현재 서비스 fallback)
```

### ap-northeast-2 (서울)
```
# global 프리픽스 (서울 포함 글로벌 라우팅)
global.anthropic.claude-sonnet-4-6                # Sonnet 4.6
global.anthropic.claude-sonnet-4-5-20250929-v1:0  # Sonnet 4.5
global.anthropic.claude-haiku-4-5-20251001-v1:0   # Haiku 4.5
global.anthropic.claude-opus-4-6-v1               # Opus 4.6
global.anthropic.claude-opus-4-5-20251101-v1:0    # Opus 4.5

# apac 프리픽스 (아태 리전 라우팅)
apac.anthropic.claude-sonnet-4-20250514-v1:0      # Sonnet 4
apac.anthropic.claude-3-7-sonnet-20250219-v1:0    # Sonnet 3.7
apac.anthropic.claude-3-5-sonnet-20241022-v2:0    # Sonnet 3.5 v2
apac.anthropic.claude-3-haiku-20240307-v1:0       # Haiku 3

# ON_DEMAND (서울 리전 고정)
anthropic.claude-3-5-sonnet-20240620-v1:0         # Sonnet 3.5 초기 (서울 고정 가능)
anthropic.claude-3-haiku-20240307-v1:0            # Haiku 3 (서울 고정 가능)
```

## Sonnet 4.5 vs 4.6 성능 비교 (테스트 결과)

### us-east-1 테스트

| 테스트 | 모델 | 시간(s) | 입력 토큰 | 출력 토큰 |
|--------|------|---------|----------|----------|
| 간단 질문 | 4.5 | 2.50 | 37 | 23 |
| 간단 질문 | **4.6** | **1.05** | 37 | 22 |
| 코드 생성 | 4.5 | 6.17 | 56 | 512 |
| 코드 생성 | **4.6** | **5.74** | 56 | 512 |
| 분석/추론 | **4.5** | **9.70** | 93 | 616 |
| 분석/추론 | 4.6 | 17.05 | 93 | 959 |

### ap-northeast-2 (서울) 테스트

| 테스트 | 모델 | 시간(s) | 입력 토큰 | 출력 토큰 |
|--------|------|---------|----------|----------|
| 코드 생성 | 4.5 | 5.91 | 56 | 512 |
| 코드 생성 | 4.6 | 6.58 | 56 | 512 |
| 분석/추론 | **4.5** | **10.62** | 93 | 673 |
| 분석/추론 | 4.6 | 17.07 | 93 | 1024 |
| 한국어 자연어 | 4.5 | 9.36 | 52 | 512 |
| 한국어 자연어 | 4.6 | 9.51 | 52 | 512 |

### 관찰 사항
- **간단한 질문**: 4.6이 TTFT(첫 토큰)와 총 응답 시간 모두 빠름
- **코드 생성**: 비슷한 수준 (출력 토큰이 같을 때)
- **분석/추론**: 4.6이 더 상세한 답변(토큰 많음) → 시간은 더 걸림
- **응답 스타일**: 4.6이 표/마크다운 구조화를 더 적극 사용
- **스트리밍 TTFT**: 0.88s (서울, global 프리픽스)

## 서비스 적용 시 설정

### us-east-1 유지 (현재)
```env
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6
```

### 서울 리전 전환 시
```env
AWS_REGION=ap-northeast-2
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-6
BEDROCK_FALLBACK_MODEL_ID=global.anthropic.claude-haiku-4-5-20251001-v1:0
```

> **주의**: 서울 리전에서는 `global.` 프리픽스만 가능하므로, 트래픽이 다른 리전으로 라우팅될 수 있음.
> 서울 전용 `apac.anthropic.claude-sonnet-4-6` 프리픽스가 AWS에서 추가되면 변경 권장.

## 결정 사항 및 주의점
- 2026-03-03 기준 Sonnet 4.6은 서울 전용(리전 고정) 호출 불가
- 서울에서 사용하려면 `global.` 프리픽스 필수 (다른 리전 라우팅 가능성 있음)
- `apac.` 프리픽스는 Sonnet 4까지만 지원, 4.5/4.6 미지원
- 이 정보는 AWS Bedrock API(`list_foundation_models`, `list_inference_profiles`)를 직접 호출하여 확인한 결과
- AWS에서 프리픽스를 추가할 수 있으므로 주기적으로 재확인 필요
