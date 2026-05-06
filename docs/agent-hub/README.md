# Agent Hub 설계 문서 세트

루시드AI를 사내 AI Hub로 격상하기 위한 설계 문서 모음. 각 문서는 독립적으로 읽힐 수 있도록 쓰되, 상호 참조 관계를 명시한다.

## 문서 구성

| # | 문서 | 상태 | 역할 |
|---|------|------|------|
| 00 | [비전](00_vision.md) | 보존 (2026-04-06 원본) | 플랫폼 비전 · 방향성 · 레퍼런스 모델 |
| 01 | [용어 정의](01_terminology.md) | ✅ Phase 1 확정 | Agent/Worker/Workspace/Runner/Capability/Platform/Connector |
| 02 | [데이터 모델](02_data_model.md) | ✅ Phase 1 확정 | 8개 테이블 · ER · 마이그레이션 전략 |
| 03 | [매니페스트 명세](03_manifest_spec.md) | ✅ Phase 1 확정 | DB JSON · 플랫폼별 runtime 4종 · `intent_hints` |
| 04 | [등록 플로우](04_registration_flow.md) | ✅ Phase 1 확정 | 라이프사이클 · 페르소나별 위저드 · AI 검증 + 인간 승인 |
| 05 | [라우팅](05_routing.md) | ✅ Phase 1 확정 | Workspace 격리 · 빠른 워크스페이스 · 시스템 프롬프트 합성 |
| 06 | [Runner 프로토콜](06_runner_protocol.md) | ✅ Phase 1 확정 | WebSocket · 메시지 8종 · MySQL 큐 · S3 파일 전달 |
| 07 | [보안](07_security.md) | ✅ Phase 1 확정 | SSM Parameter Store · caller 권한 · 사번 위조 방지 |

## 읽는 순서 (권장)

00 (비전) → 01 (용어) → 02 (데이터) → 03 (매니페스트) → 04~07 (각 도메인)

## 작성 원칙

- **컨센서스 우선**: 각 문서 초안은 "결정된 것"과 "논의 필요"를 명확히 구분한다.
- **최소 단위 갱신**: 이해관계자 합의가 끝난 섹션만 확정 표시(✅). 나머지는 TBD.
- **원본 보존**: `00_vision.md`는 원본 스냅샷. 후속 문서와 충돌하는 내용은 각 문서에서 명시적으로 덮어쓴다.

## 관련 히스토리

- [2026-04-17 Agent Store · Workspace-Agent 연결 · 알림함 분리](../history/2026-04-17_AgentStore_Workspace_Inbox.md) — 프론트 골격 구현 세션
- [2026-03-03 Lucid Service Hub](../history/2026-03-03_LucidServiceHub.md) — 초기 논의
