# 🏗️ Frontend 아키텍처 가이드

> **프로젝트**: LFChatbot Next.js Frontend  
> **작성일**: 2025-12-10  
> **대상**: 비기너 개발자를 위한 완전한 구조 설명서

---

## 📋 목차

1. [프로젝트 개요](#-프로젝트-개요)
2. [디렉토리 구조 전체 맵](#-디렉토리-구조-전체-맵)
3. [중요도별 분류](#-중요도별-분류)
4. [라우팅 구조](#-라우팅-구조)
5. [상세 디렉토리 설명](#-상세-디렉토리-설명)
6. [파일 간 의존성 관계](#-파일-간-의존성-관계)
7. [잠재적 문제점 및 개선사항](#-잠재적-문제점-및-개선사항)

---

## 🎯 프로젝트 개요

### 기본 정보
- **프레임워크**: Next.js 16.0.7 (App Router)
- **언어**: TypeScript 5.6.3
- **스타일링**: Tailwind CSS 4.1.13
- **상태관리**: React 19.0.1 + Custom Hooks
- **백엔드 연동**: FastAPI (http://localhost:8000)

### 프로젝트 특징
이 프로젝트는 Vercel의 `ai-chatbot`에서 UI만 추출한 독립형 챗봇 프론트엔드입니다.
- ✅ 데이터베이스 의존성 제거 (Drizzle, Postgres 제거됨)
- ✅ 인증 시스템 제거 (Auth.js 제거됨)
- ✅ 클라이언트 사이드 채팅 히스토리
- ✅ FastAPI 백엔드와 스트리밍 통신

---

## 📁 디렉토리 구조 전체 맵

```
frontend/
├── 📂 app/                          # Next.js App Router 핵심 디렉토리
│   ├── 📂 (auth)/                   # 인증 관련 라우트 그룹
│   ├── 📂 (chat)/                   # 채팅 관련 라우트 그룹
│   │   ├── 📂 api/                  # API 라우트 핸들러
│   │   ├── 📂 chat/[id]/            # 동적 채팅 세션 페이지
│   │   ├── actions.ts               # Server Actions
│   │   ├── layout.tsx               # 채팅 레이아웃
│   │   └── page.tsx                 # 메인 채팅 페이지
│   ├── favicon.ico                  # 파비콘
│   ├── globals.css                  # 전역 스타일
│   └── layout.tsx                   # 루트 레이아웃
│
├── 📂 components/                   # React 컴포넌트
│   ├── 📂 ui/                       # shadcn/ui 기본 컴포넌트
│   ├── 📂 elements/                 # 커스텀 UI 요소
│   └── *.tsx                        # 비즈니스 로직 컴포넌트
│
├── 📂 lib/                          # 유틸리티 및 설정
│   ├── 📂 ai/                       # AI 관련 로직
│   ├── 📂 editor/                   # 에디터 관련
│   ├── 📂 artifacts/                # 아티팩트 처리
│   └── *.ts                         # 공통 유틸리티
│
├── 📂 hooks/                        # Custom React Hooks
├── 📂 public/                       # 정적 파일
├── 📂 tests/                        # Playwright 테스트
├── 📂 artifacts/                    # 생성된 아티팩트 저장소
│
├── 📂 .next/                        # Next.js 빌드 출력 (자동생성)
├── 📂 node_modules/                 # npm 패키지 (자동생성)
│
├── 📄 next.config.ts                # Next.js 설정
├── 📄 tsconfig.json                 # TypeScript 설정
├── 📄 tailwind.config.js            # Tailwind CSS 설정
├── 📄 package.json                  # 프로젝트 의존성
├── 📄 biome.jsonc                   # Biome 린터/포매터 설정
├── 📄 playwright.config.ts          # E2E 테스트 설정
└── 📄 .env.example                  # 환경변수 예시
```

---

## ⭐ 중요도별 분류

### 🔴 필수 (매일 작업하는 핵심 파일)

| 경로 | 역할 | 이유 |
|------|------|------|
| `app/(chat)/page.tsx` | 메인 채팅 페이지 | 사용자가 처음 보는 화면 |
| `app/(chat)/api/chat/route.ts` | 채팅 API 엔드포인트 | 백엔드와 통신하는 핵심 로직 |
| `components/chat.tsx` | 채팅 UI 컨테이너 | 전체 채팅 인터페이스 관리 |
| `components/multimodal-input.tsx` | 메시지 입력 컴포넌트 | 사용자 입력 처리 |
| `components/messages.tsx` | 메시지 목록 렌더링 | 대화 내용 표시 |
| `lib/ai/models.ts` | AI 모델 설정 | 사용할 AI 모델 정의 |
| `hooks/use-simple-chat.ts` | 채팅 상태 관리 훅 | 메시지 전송/수신 로직 |

### 🟡 중요 (기능 추가/수정 시 필요)

| 경로 | 역할 |
|------|------|
| `app/layout.tsx` | 전역 레이아웃 및 메타데이터 |
| `app/globals.css` | 전역 스타일 및 CSS 변수 |
| `components/app-sidebar.tsx` | 사이드바 네비게이션 |
| `components/sidebar-history.tsx` | 채팅 히스토리 목록 |
| `components/message.tsx` | 개별 메시지 컴포넌트 |
| `lib/utils.ts` | 공통 유틸리티 함수 |
| `lib/ai/prompts.ts` | AI 프롬프트 템플릿 |

### 🟢 참고 (설정 및 보조 파일)

| 경로 | 역할 |
|------|------|
| `next.config.ts` | Next.js 빌드 설정 |
| `tsconfig.json` | TypeScript 컴파일러 옵션 |
| `package.json` | 프로젝트 의존성 관리 |
| `biome.jsonc` | 코드 린팅/포매팅 규칙 |
| `components/ui/*` | shadcn/ui 재사용 가능 컴포넌트 |
| `components/elements/*` | 커스텀 UI 요소 |

### ⚪ 자동생성 (직접 수정 금지)

| 경로 | 설명 |
|------|------|
| `.next/` | Next.js 빌드 캐시 및 출력 |
| `node_modules/` | npm 패키지 저장소 |
| `next-env.d.ts` | Next.js TypeScript 타입 정의 |
| `pnpm-lock.yaml` | 패키지 잠금 파일 |

---

## 🛣️ 라우팅 구조

### Next.js App Router 패턴

Next.js 13+ App Router는 **파일 시스템 기반 라우팅**을 사용합니다.

```
app/
├── layout.tsx                    → 모든 페이지에 적용되는 루트 레이아웃
├── (chat)/                       → 라우트 그룹 (URL에 포함 안됨)
│   ├── layout.tsx                → /에 적용되는 채팅 레이아웃
│   ├── page.tsx                  → / (홈페이지)
│   ├── chat/[id]/                → /chat/:id (동적 라우트)
│   │   └── page.tsx              → 특정 채팅 세션 페이지
│   └── api/                      → API 라우트
│       ├── chat/route.ts         → POST /api/chat
│       ├── document/route.ts     → /api/document
│       ├── files/route.ts        → /api/files
│       ├── history/route.ts      → /api/history
│       ├── suggestions/route.ts  → /api/suggestions
│       └── vote/route.ts         → /api/vote
└── (auth)/                       → 인증 라우트 그룹
    └── auth.ts                   → /auth (현재 미사용)
```

### 실제 URL 매핑

| URL | 파일 경로 | 설명 |
|-----|-----------|------|
| `/` | `app/(chat)/page.tsx` | 메인 채팅 페이지 |
| `/chat/abc123` | `app/(chat)/chat/[id]/page.tsx` | 특정 채팅 세션 |
| `/api/chat` | `app/(chat)/api/chat/route.ts` | 채팅 API 엔드포인트 |
| `/api/history` | `app/(chat)/api/history/route.ts` | 히스토리 API |

### 라우트 그룹 `(chat)`, `(auth)`의 의미

- **괄호로 감싼 폴더**는 URL 경로에 포함되지 않습니다
- 관련 라우트를 논리적으로 그룹화하는 용도
- 각 그룹마다 별도의 `layout.tsx`를 가질 수 있음

---

## 📖 상세 디렉토리 설명

### 1️⃣ `app/` - Next.js App Router 핵심

#### `app/layout.tsx` 🔴
**역할**: 전체 애플리케이션의 루트 레이아웃  
**주요 기능**:
- HTML 문서 구조 정의
- 전역 폰트 설정 (Geist, Geist Mono)
- 테마 프로바이더 (다크/라이트 모드)
- Toast 알림 컴포넌트
- 메타데이터 설정 (타이틀, 설명)

**의존성**: `ThemeProvider`, `Toaster`, `globals.css`

---

#### `app/globals.css` 🟡
**역할**: 전역 CSS 스타일 및 Tailwind 설정  
**주요 내용**:
- Tailwind CSS 레이어 (`@tailwind base, components, utilities`)
- CSS 변수 정의 (색상, 간격, 폰트)
- 다크 모드 변수
- 커스텀 애니메이션
- 스크롤바 스타일

---

#### `app/(chat)/page.tsx` 🔴
**역할**: 메인 채팅 페이지 (홈페이지)  
**주요 로직**:
1. 새로운 채팅 세션 ID 생성 (`generateUUID()`)
2. 쿠키에서 마지막 사용 모델 확인
3. `<Chat>` 컴포넌트 렌더링
4. `<DataStreamHandler>` 마운트 (스트림 데이터 처리)

**Props 전달**:
- `id`: 채팅 세션 ID
- `initialChatModel`: 사용할 AI 모델
- `initialMessages`: 빈 배열 (새 채팅)
- `autoResume`: false (자동 재개 비활성화)

---

#### `app/(chat)/layout.tsx` 🟡
**역할**: 채팅 페이지 전용 레이아웃  
**주요 기능**:
- 사이드바 (`AppSidebar`) 포함
- 반응형 레이아웃 (모바일/데스크톱)
- 채팅 히스토리 표시

---

#### `app/(chat)/api/chat/route.ts` 🔴
**역할**: 채팅 메시지 처리 API 엔드포인트  
**HTTP 메서드**: POST, DELETE  
**주요 로직**:
1. 클라이언트에서 메시지 수신
2. FastAPI 백엔드로 스트리밍 요청 (`http://localhost:8000/api/v1/chat/message/stream`)
3. SSE(Server-Sent Events) 형식으로 응답 스트리밍
4. `createUIMessageStream`으로 UI 업데이트 이벤트 생성

**백엔드 통신 구조**:
```typescript
POST http://localhost:8000/api/v1/chat/message/stream
Body: {
  message: string,
  user_id: "anonymous",
  session_id: string,
  chat_mode: "normal"
}
```

**응답 형식**:
- `data-appendMessage`: 새 메시지 추가
- `text-delta`: 텍스트 스트리밍 청크

---

#### `app/(chat)/api/*/route.ts` 🟢
기타 API 엔드포인트들:

| 파일 | 엔드포인트 | 역할 |
|------|-----------|------|
| `document/route.ts` | `/api/document` | 문서 생성/수정 |
| `files/route.ts` | `/api/files` | 파일 업로드 처리 |
| `history/route.ts` | `/api/history` | 채팅 히스토리 조회 |
| `suggestions/route.ts` | `/api/suggestions` | AI 제안 생성 |
| `vote/route.ts` | `/api/vote` | 메시지 평가 (좋아요/싫어요) |

---

### 2️⃣ `components/` - React 컴포넌트

#### 핵심 채팅 컴포넌트 🔴

##### `chat.tsx`
**역할**: 채팅 인터페이스의 최상위 컨테이너  
**주요 기능**:
- `useSimpleChat` 훅으로 채팅 상태 관리
- 메시지 목록 렌더링
- 입력창 (`MultimodalInput`) 통합
- 사이드바 토글
- 스크롤 자동 하단 이동

**Props**:
- `id`: 채팅 세션 ID
- `initialMessages`: 초기 메시지 배열
- `initialChatModel`: 사용할 AI 모델
- `isReadonly`: 읽기 전용 모드 여부

---

##### `multimodal-input.tsx`
**역할**: 사용자 입력 처리 (텍스트, 파일, 이미지)  
**주요 기능**:
- Textarea 자동 높이 조절
- 파일 첨부 (이미지, 문서)
- Enter 키로 전송 (Shift+Enter는 줄바꿈)
- 전송 버튼 활성화/비활성화
- 첨부 파일 미리보기

**의존성**: `PreviewAttachment`, `SubmitButton`

---

##### `messages.tsx`
**역할**: 메시지 목록 렌더링  
**주요 로직**:
- 메시지 배열을 순회하며 `<Message>` 컴포넌트 생성
- 스트리밍 중인 메시지 처리
- 메시지 그룹화 (같은 역할 연속 메시지)

---

##### `message.tsx`
**역할**: 개별 메시지 렌더링  
**주요 기능**:
- 사용자/AI 메시지 구분 스타일
- 마크다운 렌더링
- 코드 블록 하이라이팅 (Shiki)
- 메시지 액션 (복사, 편집, 재생성)
- 아바타 표시

**의존성**: `MessageActions`, `MessageEditor`, `CodeBlock`

---

#### UI 컴포넌트 (`components/ui/`) 🟢

shadcn/ui 기반 재사용 가능 컴포넌트들:

| 컴포넌트 | 용도 |
|---------|------|
| `button.tsx` | 버튼 (variant: default, outline, ghost 등) |
| `input.tsx` | 텍스트 입력 필드 |
| `textarea.tsx` | 여러 줄 텍스트 입력 |
| `card.tsx` | 카드 레이아웃 |
| `dropdown-menu.tsx` | 드롭다운 메뉴 |
| `tooltip.tsx` | 툴팁 |
| `avatar.tsx` | 아바타 이미지 |
| `sidebar.tsx` | 사이드바 레이아웃 |
| `sheet.tsx` | 모달 시트 |
| `alert-dialog.tsx` | 확인 대화상자 |
| `scroll-area.tsx` | 커스텀 스크롤 영역 |
| `skeleton.tsx` | 로딩 스켈레톤 |
| `badge.tsx` | 배지/태그 |
| `separator.tsx` | 구분선 |
| `progress.tsx` | 진행 바 |

**특징**: 모두 Radix UI 기반, Tailwind로 스타일링, 접근성 준수

---

#### Elements 컴포넌트 (`components/elements/`) 🟡

커스텀 UI 요소들:

| 컴포넌트 | 역할 |
|---------|------|
| `code-block.tsx` | 코드 블록 (복사 버튼 포함) |
| `loader.tsx` | 로딩 애니메이션 |
| `branch.tsx` | 대화 분기 표시 |
| `context.tsx` | 컨텍스트 정보 표시 |
| `inline-citation.tsx` | 인라인 인용 |
| `reasoning.tsx` | AI 추론 과정 표시 |
| `source.tsx` | 출처 표시 |
| `task.tsx` | 작업 진행 상태 |
| `tool.tsx` | 도구 사용 표시 |
| `web-preview.tsx` | 웹 미리보기 |

---

#### 기타 중요 컴포넌트 🟡

| 컴포넌트 | 역할 |
|---------|------|
| `app-sidebar.tsx` | 애플리케이션 사이드바 (히스토리, 설정) |
| `sidebar-history.tsx` | 채팅 히스토리 목록 |
| `sidebar-history-item.tsx` | 개별 히스토리 항목 |
| `chat-header.tsx` | 채팅 헤더 (모델 선택, 설정) |
| `model-selector.tsx` | AI 모델 선택 드롭다운 |
| `suggested-actions.tsx` | 제안 액션 버튼들 |
| `greeting.tsx` | 초기 인사 메시지 |
| `weather.tsx` | 날씨 위젯 (예시) |
| `artifact.tsx` | 생성된 아티팩트 표시 |
| `document.tsx` | 문서 편집기 |
| `code-editor.tsx` | 코드 에디터 (CodeMirror) |
| `image-editor.tsx` | 이미지 편집기 |
| `sheet-editor.tsx` | 스프레드시트 에디터 |

---

### 3️⃣ `lib/` - 유틸리티 및 설정

#### `lib/ai/` - AI 관련 로직 🔴

##### `models.ts`
**역할**: 사용 가능한 AI 모델 정의  
**내용**:
```typescript
export const DEFAULT_CHAT_MODEL = "gpt-4o-mini";
```

---

##### `prompts.ts`
**역할**: AI 프롬프트 템플릿  
**주요 프롬프트**:
- 시스템 프롬프트
- 문서 생성 프롬프트
- 코드 생성 프롬프트
- 제안 생성 프롬프트

---

##### `providers.ts`
**역할**: AI 제공자 설정 (OpenAI, Anthropic 등)  
**기능**: 환경변수에서 API 키 로드, 제공자 초기화

---

##### `tools/` - AI 도구
| 파일 | 역할 |
|------|------|
| `create-document.ts` | 문서 생성 도구 |
| `update-document.ts` | 문서 수정 도구 |
| `get-weather.ts` | 날씨 조회 도구 (예시) |
| `request-suggestions.ts` | 제안 요청 도구 |

---

#### `lib/utils.ts` 🟡
**역할**: 공통 유틸리티 함수  
**주요 함수**:
- `cn()`: Tailwind 클래스 병합 (clsx + tailwind-merge)
- `generateUUID()`: UUID 생성
- `formatDate()`: 날짜 포맷팅
- `sanitizeUIMessages()`: 메시지 정제

---

#### `lib/types.ts` 🟡
**역할**: TypeScript 타입 정의  
**주요 타입**:
- `ChatMessage`: 채팅 메시지 구조
- `Attachment`: 첨부 파일
- `UIState`: UI 상태
- `Document`: 문서 타입

---

#### `lib/errors.ts` 🟢
**역할**: 커스텀 에러 클래스  
**주요 에러**:
- `ChatSDKError`: 채팅 SDK 에러
- `bad_request:api`: 잘못된 요청
- `offline:chat`: 오프라인 상태

---

### 4️⃣ `hooks/` - Custom React Hooks 🔴

| Hook | 역할 |
|------|------|
| `use-simple-chat.ts` | 채팅 상태 관리 (메시지 전송/수신) |
| `use-artifact.ts` | 아티팩트 상태 관리 |
| `use-messages.tsx` | 메시지 목록 관리 |
| `use-scroll-to-bottom.tsx` | 자동 스크롤 하단 이동 |
| `use-chat-visibility.ts` | 채팅 공개/비공개 설정 |
| `use-mobile.ts` | 모바일 감지 |
| `use-auto-resume.ts` | 자동 재개 기능 |

**가장 중요**: `use-simple-chat.ts`
- 메시지 전송 로직
- 스트리밍 응답 처리
- 에러 핸들링
- 로딩 상태 관리

---

### 5️⃣ `public/` - 정적 파일 🟢

```
public/
└── images/
    └── (이미지 파일들)
```

**역할**: 정적 파일 제공 (이미지, 아이콘 등)  
**접근**: `/images/example.png` → `public/images/example.png`

---

### 6️⃣ 설정 파일들 🟡

#### `package.json`
**역할**: 프로젝트 의존성 및 스크립트 정의  
**주요 스크립트**:
- `npm run dev`: 개발 서버 실행
- `npm run build`: 프로덕션 빌드
- `npm run start`: 프로덕션 서버 실행
- `npm run lint`: 코드 린팅
- `npm run test`: Playwright 테스트

**주요 의존성**:
- `next`: 16.0.7
- `react`: 19.0.1
- `ai`: 5.0.26 (Vercel AI SDK)
- `tailwindcss`: 4.1.13
- `typescript`: 5.6.3

---

#### `next.config.ts`
**역할**: Next.js 빌드 설정  
**현재 설정**:
- 이미지 원격 패턴 허용 (`avatar.vercel.sh`, Vercel Blob Storage)

---

#### `tsconfig.json`
**역할**: TypeScript 컴파일러 옵션  
**주요 설정**:
- `strict: true`: 엄격 모드
- `paths: { "@/*": ["./*"] }`: 절대 경로 임포트
- `jsx: "react-jsx"`: JSX 변환

---

#### `biome.jsonc`
**역할**: Biome 린터/포매터 설정  
**기능**: ESLint + Prettier 대체, 빠른 린팅/포매팅

---

#### `playwright.config.ts`
**역할**: E2E 테스트 설정  
**테스트 브라우저**: Chromium, Firefox, WebKit

---

### 7️⃣ 기타 디렉토리

#### `.next/` ⚪
**역할**: Next.js 빌드 출력 및 캐시  
**주의**: Git에 커밋하지 않음 (`.gitignore`에 포함)

---

#### `node_modules/` ⚪
**역할**: npm 패키지 저장소  
**주의**: 직접 수정 금지, `package.json`으로 관리

---

#### `artifacts/` 🟢
**역할**: AI가 생성한 아티팩트 저장 (문서, 코드, 이미지 등)  
**구조**: 세션별로 폴더 생성

---

#### `tests/` 🟢
**역할**: Playwright E2E 테스트 파일  
**실행**: `npm run test`

---

## 🔗 파일 간 의존성 관계

### 데이터 흐름도

```
사용자 입력
    ↓
MultimodalInput.tsx
    ↓
useSimpleChat.ts (메시지 전송)
    ↓
POST /api/chat (route.ts)
    ↓
FastAPI Backend (http://localhost:8000)
    ↓
SSE 스트리밍 응답
    ↓
useSimpleChat.ts (응답 수신)
    ↓
Messages.tsx → Message.tsx
    ↓
화면에 렌더링
```

---

### 주요 의존성 체인

#### 1. 채팅 페이지 렌더링
```
app/(chat)/page.tsx
  → components/chat.tsx
    → hooks/use-simple-chat.ts
      → app/(chat)/api/chat/route.ts
        → FastAPI Backend
```

---

#### 2. 메시지 표시
```
components/messages.tsx
  → components/message.tsx
    → components/elements/code-block.tsx
    → components/message-actions.tsx
```

---

#### 3. 사이드바
```
app/(chat)/layout.tsx
  → components/app-sidebar.tsx
    → components/sidebar-history.tsx
      → components/sidebar-history-item.tsx
```

---

#### 4. 스타일링
```
app/layout.tsx
  → app/globals.css
    → Tailwind CSS
      → components/ui/* (모든 UI 컴포넌트)
```

---

## ⚠️ 잠재적 문제점 및 개선사항

### 🔴 심각한 문제

#### 1. **하드코딩된 백엔드 URL**
**위치**: `app/(chat)/api/chat/route.ts:66`
```typescript
const backendResponse = await fetch("http://localhost:8000/api/v1/chat/message/stream", {
```

**문제점**:
- 환경에 따라 URL이 달라져야 함 (개발/프로덕션)
- 배포 시 작동하지 않음

**해결책**:
```typescript
// .env.local
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000

// route.ts
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const backendResponse = await fetch(`${backendUrl}/api/v1/chat/message/stream`, {
```

---

#### 2. **인증 시스템 미완성**
**위치**: `app/(auth)/auth.ts`

**문제점**:
- README에서는 인증이 제거되었다고 하지만 `(auth)` 폴더가 남아있음
- `auth.ts` 파일이 존재하지만 사용되지 않음

**해결책**:
- 사용하지 않는다면 `app/(auth)` 폴더 완전 삭제
- 또는 실제 인증 구현 (NextAuth.js 등)

---

#### 3. **에러 처리 부족**
**위치**: `hooks/use-simple-chat.ts`

**문제점**:
- 네트워크 에러 시 사용자에게 명확한 피드백 없음
- 백엔드 다운 시 무한 로딩

**해결책**:
```typescript
try {
  // 채팅 로직
} catch (error) {
  toast.error("메시지 전송에 실패했습니다. 다시 시도해주세요.");
  console.error(error);
}
```

---

### 🟡 개선 권장사항

#### 4. **중복 파일 존재**
**위치**: `proxy.ts.bak`

**문제점**:
- `.bak` 파일이 프로젝트에 포함됨
- Git에 커밋되어 있음

**해결책**:
- 필요 없다면 삭제
- `.gitignore`에 `*.bak` 추가

---

#### 5. **패키지 매니저 혼용**
**발견**:
- `package-lock.json` (npm)
- `pnpm-lock.yaml` (pnpm)

**문제점**:
- 두 개의 잠금 파일이 동시에 존재
- 팀원마다 다른 패키지 매니저 사용 가능

**해결책**:
- 하나의 패키지 매니저로 통일 (권장: pnpm)
- 사용하지 않는 잠금 파일 삭제
- `.npmrc`에 `package-manager=pnpm@9.12.3` 추가

---

#### 6. **타입 안정성 부족**
**위치**: `app/(chat)/api/chat/route.ts:30`
```typescript
.filter((part: any) => part.type === "text")
```

**문제점**:
- `any` 타입 사용으로 타입 안정성 저하

**해결책**:
```typescript
interface MessagePart {
  type: "text" | "image";
  text?: string;
  url?: string;
}

.filter((part: MessagePart) => part.type === "text")
```

---

#### 7. **환경변수 관리 미흡**
**위치**: `.env.example`

**문제점**:
- 실제 사용되는 환경변수와 예시가 다를 수 있음
- 백엔드 URL이 환경변수로 관리되지 않음

**해결책**:
```bash
# .env.example에 추가
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_API_TIMEOUT=30000
```

---

#### 8. **불필요한 AI 도구**
**위치**: `lib/ai/tools/get-weather.ts`

**문제점**:
- 날씨 API가 실제로 사용되지 않음
- 예시 코드로 보임

**해결책**:
- 사용하지 않는다면 삭제
- 또는 실제 날씨 API 연동 (OpenWeatherMap 등)

---

#### 9. **테스트 커버리지 부족**
**위치**: `tests/`

**문제점**:
- E2E 테스트만 존재
- 단위 테스트 없음

**해결책**:
- Jest + React Testing Library 추가
- 주요 컴포넌트 및 훅 단위 테스트 작성

---

#### 10. **접근성 (a11y) 개선 필요**
**위치**: 전체 컴포넌트

**문제점**:
- 키보드 네비게이션 부족
- 스크린 리더 지원 미흡

**해결책**:
- `aria-label`, `role` 속성 추가
- 키보드 단축키 구현 (Ctrl+Enter로 전송 등)

---

### 🟢 최적화 제안

#### 11. **번들 크기 최적화**
**문제점**:
- 많은 의존성 (102개 패키지)
- 사용하지 않는 라이브러리 포함 가능성

**해결책**:
```bash
# 번들 분석
npm run build
npx @next/bundle-analyzer
```

---

#### 12. **코드 스플리팅 개선**
**위치**: `components/artifact.tsx` (16,960 bytes)

**문제점**:
- 큰 컴포넌트가 초기 로드에 포함됨

**해결책**:
```typescript
import dynamic from 'next/dynamic';

const Artifact = dynamic(() => import('@/components/artifact'), {
  loading: () => <ArtifactSkeleton />,
});
```

---

#### 13. **이미지 최적화**
**위치**: `app/favicon.ico` (12,141 bytes)

**문제점**:
- 파비콘이 너무 큼 (일반적으로 1-2KB)

**해결책**:
- 이미지 압축 도구 사용 (TinyPNG 등)
- Next.js Image 컴포넌트 활용

---

## 📚 추가 학습 자료

### Next.js App Router
- [공식 문서](https://nextjs.org/docs/app)
- [라우팅 가이드](https://nextjs.org/docs/app/building-your-application/routing)

### Vercel AI SDK
- [AI SDK 문서](https://sdk.vercel.ai/docs)
- [스트리밍 가이드](https://sdk.vercel.ai/docs/ai-sdk-ui/streaming)

### TypeScript
- [TypeScript 핸드북](https://www.typescriptlang.org/docs/handbook/intro.html)

### Tailwind CSS
- [공식 문서](https://tailwindcss.com/docs)
- [shadcn/ui](https://ui.shadcn.com/)

---

## 🎓 비기너를 위한 팁

### 1. 어디서부터 시작할까?
1. `app/(chat)/page.tsx` 읽기 → 진입점 이해
2. `components/chat.tsx` 읽기 → 메인 로직 파악
3. `hooks/use-simple-chat.ts` 읽기 → 상태 관리 이해
4. `app/(chat)/api/chat/route.ts` 읽기 → 백엔드 통신 이해

### 2. 컴포넌트 수정 시 주의사항
- `components/ui/*`는 직접 수정하지 말고 래핑해서 사용
- 타입 정의는 `lib/types.ts`에 추가
- 공통 함수는 `lib/utils.ts`에 추가

### 3. 디버깅 팁
- 브라우저 콘솔에서 `[ROUTE]` 로그 확인
- React DevTools로 컴포넌트 상태 확인
- Network 탭에서 API 요청 확인

### 4. 자주 사용하는 명령어
```bash
npm run dev          # 개발 서버 실행
npm run build        # 빌드 (에러 확인용)
npm run lint         # 코드 검사
```

---

## 📞 문의 및 기여

이 문서에 대한 질문이나 개선 사항이 있다면:
1. 프로젝트 README.md 참고
2. 팀 리드에게 문의
3. 이슈 트래커에 등록

---

**마지막 업데이트**: 2025-12-10  
**작성자**: Antigravity AI Assistant  
**버전**: 1.0.0
