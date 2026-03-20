# 2026-03-20 SVG 시각화 + Mermaid 다이어그램

## 개요
시각화 도구를 2종 추가했다:
1. **SVG Visual** — LLM이 인포그래픽, KPI 대시보드, 비교 시각화 등 자유도 높은 SVG를 생성하여 채팅 인라인으로 표시
2. **Mermaid Diagram** — 마크다운 ```mermaid 코드 블록으로 플로우차트, 시퀀스, 간트, ER 다이어그램을 자동 렌더링

기존 차트(Recharts)는 정량 데이터에 특화되어 있어, 정성적/구조적 시각화를 커버하지 못하는 한계를 보완한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/svg_generator/server.py` | 신규 | SVG 생성 MCP 서버 (regex 기반 정제) |
| `backend/mcp_config.json` | 수정 | svg_generator 서버 등록 |
| `backend/app/agents/a2a_streaming.py` | 수정 | svg_visual SSE 이벤트 감지/전송 |
| `backend/app/agents/workers/visualization_worker.py` | 수정 | SVG/Mermaid 도구 추가, 선택 가이드 |
| `backend/app/api/routes/chat.py` | 수정 | svg_data 메타데이터 저장 |
| `backend/app/services/chat_log_service.py` | 수정 | DB에서 svg_data 복원 |
| `backend/app/agents/intent_classifier.py` | 수정 | 인포그래픽/플로우차트 등 키워드 추가 |
| `frontend/components/svg-display.tsx` | 신규 | SVG 렌더링 (DOMPurify, 확대/다운로드) |
| `frontend/components/mermaid-diagram.tsx` | 신규 | Mermaid 렌더링 (확대/다운로드/코드복사) |
| `frontend/components/elements/response.tsx` | 수정 | ```mermaid 코드 블록 감지→렌더링 |
| `frontend/hooks/use-simple-chat.ts` | 수정 | svg_visual SSE 이벤트 핸들링 |
| `frontend/components/message.tsx` | 수정 | svg-visual 파트 타입 렌더링 |
| `frontend/app/(chat)/api/messages/route.ts` | 수정 | 히스토리에서 svg_data 복원 |

## 상세 내용

### 시각화 도구 3종 체계

| 도구 | 용도 | 방식 | 우선순위 |
|------|------|------|---------|
| Charts (Recharts) | 정량 데이터 (추이, 비교, 비율) | MCP tool → JSON → Recharts 렌더링 | 1순위 |
| Mermaid | 구조화된 다이어그램 (플로우차트, 시퀀스, 간트) | 마크다운 코드 블록 → Mermaid.js 렌더링 | 2순위 |
| SVG Visual | 커스텀 시각화 (인포그래픽, KPI, 비교) | MCP tool → SVG 코드 → DOMPurify 렌더링 | 3순위 |

### SVG Visual 아키텍처
```
VisualizationWorker → create_svg_visual MCP tool
    ↓
MCP Server: regex 기반 보안 정제 (script/on*/javascript: 제거)
    ↓
a2a_streaming.py: svg_visual SSE 이벤트
    ↓
Frontend: DOMPurify SVG 프로파일로 이중 정제 → 인라인 렌더링
```

### Mermaid 아키텍처
```
어떤 Worker든 → 응답에 ```mermaid 코드 블록 포함
    ↓
response.tsx: language-mermaid 감지
    ↓
MermaidDiagram 컴포넌트: mermaid.render() → SVG 인라인 렌더링
```

- Mermaid.js v11.12.2 (streamdown 의존성으로 이미 설치됨)
- neutral 테마, Malgun Gothic 폰트
- 스트리밍 중에는 코드 블록으로 표시, 완료 후 렌더링
- 에러 시 코드 블록으로 폴백

### SVG 보안 (이중 방어)
- **백엔드**: regex로 script/foreignObject/on*/javascript: 제거 (XML 파서는 CSS를 파괴하므로 미사용)
- **프론트엔드**: DOMPurify 3.3.3 SVG 프로파일 (feDropShadow 등 필터 허용)
- **LLM 프롬프트**: `<style>` 태그 대신 인라인 style 속성만 사용하도록 지시

## 결정 사항 및 주의점
- **XML 파서 미사용**: `xml.etree.ElementTree`는 SVG 내 `<style>` CSS를 파괴 → regex 기반 정제 채택
- **Mermaid = 마크다운 통합**: MCP 도구 패턴 대신 코드 블록 감지 방식 → 모든 Worker에서 자연스럽게 사용 가능
- **선택 우선순위**: Charts > Mermaid > SVG (단순한 도구를 우선, SVG는 최후 수단)
- **DOMPurify 직접 설치**: transitive dependency(mermaid) 대신 직접 의존성으로 추가 (`dompurify@3.3.3`)
