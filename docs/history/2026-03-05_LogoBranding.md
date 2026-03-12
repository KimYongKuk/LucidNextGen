# 2026-03-05 로고 브랜딩 적용

## 개요
커스텀 SVG/PNG 로고를 사이드바 헤더, AI 응답 아이콘, 브라우저 favicon에 적용하여 브랜드 아이덴티티를 강화했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `frontend/public/logo.svg` | 추가 | 애니메이션 로고 SVG (보라/파랑/민트 구체 삼각형 회전) |
| `frontend/public/logo.png` | 추가 | 정적 로고 PNG |
| `frontend/components/app-sidebar.tsx` | 수정 | 사이드바 헤더 `✨Lucid AI` → 로고 이미지 + 텍스트 |
| `frontend/components/message.tsx` | 수정 | AI 응답 아이콘: 로딩 중 SVG(애니메이션), 완료 후 PNG(정적) |
| `frontend/app/layout.tsx` | 수정 | metadata.icons에 `/logo.png` favicon 설정 |
| `frontend/app/favicon.ico` | 삭제 | 기존 L&F favicon 제거 (PNG로 대체) |

## 상세 내용

### 로고 파일
- **SVG** (`logo.svg`): 200x200 viewBox, 보라/파랑/민트 3색 구체가 삼각형 꼭짓점을 순환하는 SMIL 애니메이션 (3.6s 주기), glow 필터 + 파티클 효과
- **PNG** (`logo.png`): 정적 버전, favicon 및 응답 완료 후 아이콘으로 사용

### 사이드바 헤더 (`app-sidebar.tsx`)
- `✨Lucid AI` 텍스트 → `<img src="/logo.svg" className="size-7" />` + `Lucid AI` 텍스트
- flex + gap-2 레이아웃으로 로고-텍스트 정렬

### AI 응답 아이콘 (`message.tsx`)
- `isLoading` prop 기반 조건부 이미지 전환:
  - 로딩 중: `/logo.svg` (애니메이션 활성)
  - 완료 후: `/logo.png` (정적)
- 기존 `SparklesIcon` 컴포넌트 및 import 제거
- 로딩 인디케이터(`ThinkingMessage`)도 동일하게 SVG 적용
- 아이콘 위치: `-mt-1` → `mt-1`로 조정 (텍스트 정렬 개선)

### Favicon (`layout.tsx`)
- `metadata.icons.icon = "/logo.png"` 설정
- 기존 `favicon.ico` 삭제 (Next.js app 디렉토리 자동 favicon 방지)

## 결정 사항 및 주의점
- SVG는 SMIL 애니메이션 사용 — 모든 모던 브라우저 지원, IE 미지원 (대상 아님)
- favicon은 PNG 사용 — SVG favicon은 일부 브라우저 미지원이므로 PNG가 안전
- 로딩 상태에서만 애니메이션 로고를 보여주어 시각적 피드백과 성능 균형 유지
