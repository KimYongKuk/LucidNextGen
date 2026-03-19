# 2026-03-19 PPTX 생성 퀄리티 개선

## 개요
PPT 생성 산출물의 레이아웃 다양성, 차트/시각요소 활용, 디자인 완성도를 대폭 개선. MCP 서버에 새로운 Shape 렌더러 3종(callout_box, kpi_card, divider)을 추가하고, 차트 스타일링 옵션(시리즈 색상, 데이터 라벨, 범례 위치)을 강화하며, 시스템 프롬프트를 레이아웃 패턴 10종 + 차트 JSON 예시 + 디자인 규칙으로 전면 개편했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/mcp_servers/ppt_generator/server.py | 수정 | Shape 렌더러 3종 추가, textbox fill/border 옵션, 차트 스타일 강화, dispatch/스키마 업데이트 |
| backend/app/agents/workers/ppt_worker.py | 수정 | 시스템 프롬프트 대폭 개선 — 레이아웃 패턴 10종, 차트 JSON 예시, 디자인 규칙, 패턴 선택 가이드 |

## 상세 내용

### Phase 1: Shape 렌더러 확장 (server.py)

#### 1A. textbox 강화
- `fill_color`, `border_color`, `border_width` 옵션 파라미터 추가
- fill/border 지정 시 `add_shape(ROUNDED_RECTANGLE)` + text frame 사용 (모서리 둥글게)
- 내부 여백 자동 설정 (margin 0.15"/0.08")
- 기존 textbox와 100% 역호환

#### 1B. 신규: render_callout_box
강조 박스 — 인사이트, 경고, 요약 등을 시각적으로 부각.
- ROUNDED_RECTANGLE 배경 + 좌측 accent bar(0.06") + 아이콘 텍스트
- 4개 프리셋 스타일: insight(파랑), warning(오렌지), success(초록), summary(회색)
- 커스텀 fill_color/accent_color/icon 오버라이드 가능

#### 1C. 신규: render_kpi_card
KPI 카드 — 대시보드용 핵심 수치 표시.
- 배경 ROUNDED_RECTANGLE + 상단 accent line + value(36pt bold) + label(10pt) + trend(▲/▼ 색상)
- accent_color로 카드별 색상 지정 (테마 키 또는 HEX)
- value_size 조정으로 카드 크기에 맞는 글자 크기

#### 1D. 신규: render_divider
시각 구분선 — 콘텐츠 영역 사이 분리.
- 얇은 RECTANGLE (기본 1.5pt), 색상/두께 조절 가능

#### 1E. 차트 스타일 강화
- `series_colors`: HEX 배열로 시리즈별 색상 (pie/doughnut은 포인트별)
- `data_labels`: true/false → 데이터 값 표시 (9pt)
- `legend_position`: bottom/right/top/left/none
- `number_format`: "#,##0" 등 숫자 포맷
- line 계열은 선 색상도 동시 설정

#### 1F/1G. dispatch + 스키마
- render_slide() dispatch에 callout_box, kpi_card, divider 추가
- Tool description에 7종 shape 파라미터 전체 문서화
- type enum 업데이트

### Phase 2: 시스템 프롬프트 개선 (ppt_worker.py)

#### 레이아웃 패턴 4개 → 10개
| 패턴 | 용도 | 핵심 shape |
|------|------|-----------|
| A. 테이블+인사이트 | 데이터 비교/나열 | table + callout_box |
| B. 차트 전폭+콜아웃 | 트렌드/추이 | chart + callout_box |
| C. 2단 컬럼 | A vs B 비교 | textbox/table x2 |
| D. KPI 대시보드 | 실적/현황 요약 | kpi_card x3-4 + chart |
| E. 차트+텍스트 | 차트 해석 | chart + textbox |
| F. 프로세스 플로우 | 절차/로드맵 | callout_box x3-5 |
| G. 데이터 하이라이트 | 핵심 수치 강조 | kpi_card + table |
| H. 섹션 오프너 | 섹션 도입 | textbox + divider |
| I. 테이블+차트 | 데이터+시각화 동시 | table + chart |
| J. 텍스트 전용 | 결론/권고 | textbox + callout_box |

#### 추가된 프롬프트 섹션
- 차트 JSON 예시 (column, line, pie 완전한 예시)
- 차트 선택 가이드 (데이터 유형 → 차트 타입 매핑)
- 새 시각 요소 예시 (kpi_card, callout_box, divider)
- 패턴 선택 가이드 (콘텐츠 성격 → 추천 패턴 테이블)
- 디자인 규칙 (색상 사용, 여백, 시각 위계)
- 콘텐츠 밀도 규칙 (테이블 8행, 불릿 5-6개, 같은 패턴 3장 연속 금지)

### 버그 수정 (테스트 중 발견)
- **흰색 텍스트 상속 방지**: `_set_font()`에서 color 미지정 시 기본 #333333 적용. 템플릿 테마가 흰색 기본이라 모든 텍스트가 안 보이는 문제 해결. 간지처럼 명시적으로 `color=white`를 넘긴 경우만 흰색 유지.
- **Scatter 차트 XyChartData**: scatter 차트는 `CategoryChartData`가 아닌 `XyChartData`를 사용해야 함. chart_type이 scatter일 때 분기 처리 추가.

## 결정 사항 및 주의점
- 외부 라이브러리 추가 없음 — python-pptx만으로 구현
- KPI 카드는 python-pptx 그룹 생성 불가 → 겹치는 독립 shape로 구현 (삽입 순서 = Z-order)
- pie/doughnut 차트는 series가 아닌 point별 색상 설정
- scatter 차트는 XyChartData 사용 (CategoryChartData 호환 불가)
- `_set_font` 기본 색상 #333333 — 템플릿 테마 흰색 상속 방지
- 프롬프트 토큰 ~2K → ~4-5K 증가 예상, CachedChatBedrockConverse로 캐싱되므로 비용 영향 미미
- LLM 준수 강화: "MUST", "같은 패턴 3장 연속 금지" 등 강제 지시
