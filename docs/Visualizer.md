## Lucid 시각화 기능

### 개요
Claude(claude.ai)의 Visualizer 컨셉을 참고하여, 챗봇 응답에 시각화를 포함하는 3모드 시각화 체계를 구현했다.
LLM이 맥락에 따라 자율적으로 시각화 모드를 선택하여 응답에 포함한다.

### 시각화 3모드

| 모드 | 판단 기준 | 생성 방식 | 렌더링 |
|------|----------|----------|--------|
| **Recharts** | 축이 있으면 (수치 데이터 추이/비교/분포) | MCP 도구 호출 → JSON 반환 | Recharts 인터랙티브 차트 |
| **SVG** | 화살표가 있으면 (프로세스/구조/관계) | LLM이 `<svg>` 태그 직접 출력 | div + DOMPurify + dangerouslySetInnerHTML |
| **HTML 위젯** | 행/열이 있으면 (비교표/대시보드/복합 레이아웃) | LLM이 `<lucid-html>` 태그로 출력 | iframe sandbox 격리 렌더링 |

### 선택 기준 상세

```
사용자 요청 분석
├─ 수치 데이터 + 비교/추이/분포 (5개+ 포인트) → Recharts 차트 도구
├─ 프로세스/관계/구조/흐름 (박스+화살표) → SVG
├─ 비교표/요약 카드/대시보드/텍스트+구조 혼합 → HTML 위젯
└─ 회색지대:
   ├─ 항목 5개 이하 단순 바 비교 → HTML (CSS width 바)
   ├─ 항목 5개 초과 또는 축/범례 필요 → Recharts
   └─ 애매하면 데이터 비중 높으면 Recharts, 아니면 HTML
```

### 아키텍처

```
응답 스트리밍 → splitVisualBlocks() 파서
├── <svg> 감지 → SVGStreamBlock (div + DOMPurify)
├── <lucid-html> 감지 → HTMLWidgetBlock (iframe sandbox)
├── SSE chart_data 이벤트 → ChartDisplay (Recharts)
└── 그 외 텍스트 → ReactMarkdown
```

### SVG 모드

**렌더링**: `svg-stream-block.tsx`
- div + `dangerouslySetInnerHTML` (DOMPurify 정제)
- `SvgRenderer` memo로 불필요한 DOM 재생성 방지
- DOMPurify 동적 import (SSR 안전)
- 투명 배경 (채팅 UI와 자연스럽게 통합)
- hover 시 `...` 오버레이 메뉴 (Copy SVG / Download / Expand)

**시스템 프롬프트 규칙**:
- `xmlns`, `viewBox` 필수, width/height 생략
- 다크 테마 컬러: `#E2E8F0`(텍스트), `#60A5FA`(파랑), `#34D399`(초록) 등
- `<script>`, `<foreignObject>`, `on*` 이벤트 금지

**제약**: SVG 텍스트는 고정 좌표 배치 → 텍스트 넘침 가능. 다크 테마 하드코딩.

### HTML 위젯 모드

**렌더링**: `html-widget-block.tsx`
- iframe sandbox (`allow-scripts allow-same-origin`) 격리
- `<style>` 충돌 방지, `<script>` 허용 (인터랙티브 가능)
- contentDocument.body.innerHTML RAF 업데이트 (shell 고정, body만 갱신)
- 콘텐츠 주입 직후 scrollHeight 측정 → 실시간 높이 갱신

**CSS 변수 테마 대응**:
- iframe shell에 `--w-bg`, `--w-text`, `--w-card` 등 14개 CSS 변수 정의
- `useTheme()` 감지 → `#theme-vars` style 태그만 갱신 (iframe 재로드 없이 전환)
- LLM은 `var(--w-card)`, `var(--w-positive)` 등 CSS 변수 사용 (하드코딩 금지)
- iframe 최초 로드 시 현재 테마 즉시 적용

**스트리밍 친화 순서**: `<style>` 짧게 먼저 → HTML 구조 → `<script>` 마지막

**LLM 출력 형식**:
```html
<lucid-html>
<style>
  .card { background: var(--w-card); border: 1px solid var(--w-border); border-radius: 12px; }
</style>
<div class="dashboard">
  <div class="card">...</div>
</div>
</lucid-html>
```

### Recharts 차트 모드

**렌더링**: `chart-display.tsx` (기존)
- MCP 차트 도구 → JSON + PNG 자동 저장 → Recharts 인터랙티브 렌더링
- 라인/막대/파이/복합/누적/영역 차트 지원
- 호버 툴팁, 범례, 반응형 컨테이너

**공유 도구함**: DirectWorker, WebSearchWorker, UserFilesWorker, CorpRAGWorker가 차트 도구 사용 가능
(VisualizationWorker 제거 → shared_tool_names로 분배)

### 프론트엔드 컴포넌트 구조
```
ChatMessage
├── TextBlock (ReactMarkdown)
├── SVGStreamBlock (div + DOMPurify, 오버레이 메뉴)
├── HTMLWidgetBlock (iframe sandbox, CSS 변수 테마)
├── ChartDisplay (Recharts 인터랙티브)
└── FileDownloadLink (PDF/DOCX/XLSX/PPT)
```

### 블록 감지 (splitVisualBlocks)
`response.tsx`의 `splitVisualBlocks()` 함수가 텍스트에서 시각 블록을 분리:
- `<svg` ~ `</svg>` → `type: 'svg'`
- `<lucid-html>` ~ `</lucid-html>` → `type: 'html'` (래퍼 태그 제거 후 내부 HTML 추출)
- 스트리밍 중 닫히지 않은 블록 → 해당 타입으로 처리 (점진적 렌더링)
- 나머지 → `type: 'text'` (ReactMarkdown)

### 보안
- SVG: DOMPurify 정제 (`<script>`, `on*`, `javascript:` 제거)
- HTML: iframe sandbox 격리 (`allow-scripts allow-same-origin`)
- 두 모드 모두 hover 시 `...` 오버레이 메뉴 (Copy / Download / Expand)