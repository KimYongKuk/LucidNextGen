# Gamma API 도입을 통한 PPT Agent 개선 검토

> 작성일: 2026-02-27
> 상태: 검토 중 (Pro 플랜 구매 후 PoC 예정)

---

## 1. 배경

### 현재 PPT Worker 문제점
- `python-pptx` 기반으로 LLM이 슬라이드 JSON을 직접 설계하는 구조
- **콘텐츠 품질 편차가 큼** — 테마(색상/폰트/배경)는 일치하나, 콘텐츠 구성 퀄리티가 부족
- 시각 요소가 테이블 + matplotlib 이미지 차트로 제한됨
- Timeline, 피라미드, 컬럼 등 스마트 레이아웃 미지원

### 개선 목표
- PPT 콘텐츠 생성 품질 향상
- 다양한 시각적 레이아웃 지원
- 사내 템플릿(LF 브랜딩) 유지

---

## 2. Gamma API 개요

### 기본 정보
| 항목 | 내용 |
|------|------|
| API 버전 | v1.0 GA (2025.11.05~) |
| Generate API | GA (2026.01~) |
| Create from Template API | Beta |
| 베이스 URL | `https://public-api.gamma.app/v1.0/` |
| 인증 | API Key (`X-API-KEY` 헤더), OAuth 미지원 |
| 입력 한도 | 최대 100,000 토큰 (~400,000자) |
| 출력 | Gamma URL + PPTX/PDF export |
| 언어 | 60+ 언어 지원 (한국어 포함) |

### 주요 API 엔드포인트

#### Generate API (`POST /v1.0/generations`)
| 파라미터 | 설명 | 값 |
|---------|------|-----|
| `inputText` | 콘텐츠 입력 (필수) | 최대 100k 토큰 |
| `textMode` | 텍스트 변환 모드 | `generate`, `condense`, `preserve` |
| `format` | 출력 형식 | `presentation`, `document`, `social`, `webpage` |
| `numCards` | 슬라이드 수 | Pro: 1-60장 |
| `cardSplit` | 카드 분할 방식 | `auto`, `inputTextBreaks` |
| `cardOptions.dimensions` | 비율 | `fluid`, `16x9`, `4x3` |
| `textOptions.amount` | 텍스트 양 | `brief`, `medium`, `detailed`, `extensive` |
| `textOptions.tone` | 톤 | 자유 텍스트 (1-500자) |
| `textOptions.audience` | 대상 | 자유 텍스트 (1-500자) |
| `textOptions.language` | 언어 | `ko` 등 |
| `imageOptions.source` | 이미지 소스 | `aiGenerated`, `pexels`, `noImages` 등 |
| `themeId` | 테마 ID | Gamma에서 사전 생성 필요 |
| `exportAs` | 내보내기 | `pdf`, `pptx` |
| `additionalInstructions` | 추가 지시 | 자유 텍스트 (1-2000자) |

#### Create from Template API (`POST /v1.0/generations/from-template`) — Beta
| 파라미터 | 설명 |
|---------|------|
| `gammaId` (필수) | 템플릿으로 사용할 기존 Gamma 프레젠테이션 ID |
| `prompt` (필수) | 콘텐츠 커스터마이징 지시 (최대 100k 토큰) |
| `themeId` | 테마 ID (생략 시 템플릿 테마 사용) |
| `exportAs` | `pdf`, `pptx` |

#### 기타 API
- `GET /v1.0/themes` — 워크스페이스 테마 목록 조회
- `GET /v1.0/generations/{generationId}` — 생성 상태 확인

---

## 3. 가격 분석

### 플랜 비교
| 구분 | Free | Plus | Pro | Ultra |
|------|------|------|-----|-------|
| 가격 (월간) | $0 | $10/월 | **$25/월** | $100/월 |
| 가격 (연간) | $0 | $96/년 | **$216/년 ($18/월)** | - |
| 월간 크레딧 | 400 (1회성) | 1,000/월 | **4,000/월** | 20x (추정 20,000/월) |
| AI 모델 | 기본 | 고급 | 최상위 프리미엄 | 최고급 |
| 카드 수 제한 | 10장/프롬프트 | 20장 | **60장** | 75장 |
| API 접근 | X | X | **O (Beta)** | O |
| Workspace Templates | X | X | **O (Beta)** | O |
| Custom branding/fonts | X | X | **O** | O |
| 워터마크 | 'Made with Gamma' | 제거 가능 | 제거 가능 | 제거 가능 |

### 크레딧 소모
| 항목 | 크레딧 |
|------|--------|
| 카드 생성 | 1-5 cr/card |
| AI 이미지 (Basic) | 2 cr/image |
| AI 이미지 (Advanced) | 7-20 cr/image |
| AI 이미지 (Premium) | 20-70 cr/image |
| AI 이미지 (Ultra) | 30-125 cr/image |

> 미사용 크레딧은 플랜 한도의 2배까지 이월 (Pro: 최대 8,000 cr 축적 가능)

### 월간 비용 시뮬레이션 (Pro 기준)
| 시나리오 | PPT 건수 | 슬라이드 수 | 예상 크레딧 | 4,000 cr 대비 |
|---------|---------|-----------|-----------|-------------|
| 가벼운 사용 | ~10건/월 | 10장/건 | 100-500 cr | 충분 |
| 보통 사용 | ~30건/월 | 10장/건 | 300-1,500 cr | 충분 |
| 헤비 사용 | ~100건/월 | 10장/건 | 1,000-5,000 cr | 대부분 충분 |

> 사내 PPT (텍스트+표+차트, AI 이미지 미사용) 기준. AI 이미지 사용 시 크레딧 소모 급증.

### 현재 비용과 비교
| 항목 | 현재 (Bedrock only) | Gamma Pro 추가 시 |
|------|-------------------|-----------------|
| LLM 비용 | Sonnet per-token | 동일 (인텐트 분류 등) |
| PPT 생성 | Sonnet 토큰 (~$0.01-0.05/건) | Gamma 크레딧 소모 |
| 월 고정비 추가 | $0 | **+$25/월 (~35,000원)** |
| 연간 고정비 추가 | $0 | **+$216/년 (~300,000원)** |

---

## 4. 사내 템플릿 적용 방안

### 테마 (Theme) vs 템플릿 (Template)

| 구분 | 테마 | 템플릿 |
|------|------|--------|
| 역할 | 색상, 폰트, 로고, 강조색 | 슬라이드 구조/레이아웃 |
| 생성 방법 | Theme Editor에서 PPTX Import | 기존 Gamma 프레젠테이션을 등록 |
| API 사용 | `themeId` 파라미터 | `gammaId` 파라미터 (from-template) |
| Pro 필요 | 커스텀 테마 생성 가능 | Pro 필수 |

### LF 브랜드 매핑

| LF 템플릿 요소 | Gamma 테마 대응 |
|---------------|---------------|
| accent2 `ED7D31` (오렌지) | 기본 강조 색상 → 버튼, 콜아웃, 스마트 레이아웃 |
| accent1 `4472C4` (파란) | 보조 강조 색상 → 카드 배경, 텍스트 스타일 |
| 헤더 배경 `182F54` (다크 네이비) | 보조 강조 색상 (커스텀 지정) |
| 폰트 "맑은 고딕" (Malgun Gothic) | 글꼴 그룹 설정 (지원 여부 확인 필요) |
| LF 로고 | 로고 설정 → 구석 또는 헤더/바닥글 배치 |

### 예상 워크플로우

```
[1회성 셋업]
1. Gamma Pro 구매
2. PPT_Public.pptx → Theme Editor에서 Import → LF 테마 생성 (themeId 확보)
3. Gamma에서 LF 표준 프레젠테이션 수동 제작:
   ├── 표지 카드 (LF 로고, 제목 구조)
   ├── 목차 카드
   ├── 내용 카드 (테이블)
   ├── 내용 카드 (차트)
   ├── 내용 카드 (스마트 레이아웃)
   └── E.O.D 카드
4. Workspace Template으로 등록 (gammaId 확보)

[런타임 — API 호출]
POST /v1.0/generations/from-template
{
  "gammaId": "LF_템플릿_ID",
  "prompt": "사용자 요청 콘텐츠...",
  "themeId": "LF_테마_ID",
  "exportAs": "pptx"
}
→ generationId 수신 → 폴링 → PPTX 다운로드
```

---

## 5. Gamma가 제공하는 것 (현재 python-pptx 대비)

### 스마트 레이아웃
| 레이아웃 | 설명 | 현재 대체 방식 |
|---------|------|--------------|
| Timeline | 단계/프로세스 시각 표현 | 테이블로 대체 |
| 피라미드 | 계층 구조 시각화 | 불가능 |
| 컬럼 레이아웃 | 다단 배치, 반응형 | 좌표 수동 계산 |
| 갤러리 | 이미지/카드 그리드 | 불가능 |
| 콜아웃 박스 | 강조 영역 | textbox + 배경색 |
| 블록 인용 | 스타일링된 인용문 | 불가능 |

### 전체 비교
| 영역 | python-pptx (현재) | Gamma API |
|------|-------------------|-----------|
| 레이아웃 | 5개 고정 | 카드별 자유 + 스마트 레이아웃 |
| 시각 요소 | 테이블, matplotlib 차트 | 테이블 + 네이티브 차트 + 스마트 레이아웃 |
| 콘텐츠 생성 | LLM이 JSON 직접 설계 (실수 多) | Gamma AI 콘텐츠 배치 최적화 |
| 이미지 | matplotlib만 | AI 생성, Pexels, Giphy 등 |
| 톤/오디언스 | 프롬프트 의존 | 전용 파라미터 |
| 용도별 템플릿 | 1개 (범용) | 보고서/제안서/교육 등 복수 가능 |
| 사내 규격 제어 | 완전 제어 (좌표, 색상, 폰트) | 테마 + 템플릿으로 간접 제어 |

---

## 6. PPTX Export 품질 관련

### Gamma 공식 인정 제한사항
- 그라디언트 헤딩: 단색으로 대체될 수 있음
- 폰트: PC에 미설치 폰트는 다르게 표시 가능
- Export는 Present Mode 기준 (Edit Mode와 차이 가능)

### 서드파티 리뷰 (검증 필요)
- 텍스트 박스 겹침, 레이아웃 깨짐 보고 (출처: Alai Blog, Plus AI — 경쟁사/리뷰 사이트)
- 애니메이션/트랜지션 유실
- **공식 리포트가 아닌 서드파티 주장이므로 직접 테스트로 검증 필요**

---

## 7. PoC 확인 항목

Pro 구매 후 아래 항목을 순차적으로 확인:

### Step 1: 테마 셋업
- [ ] PPT_Public.pptx를 Theme Editor에 Import
- [ ] 색상 매핑 확인: ED7D31(오렌지), 4472C4(파란), 182F54(네이비)
- [ ] **맑은 고딕(Malgun Gothic) 폰트 지원 여부 확인** (가장 중요)
- [ ] LF 로고 배치 확인

### Step 2: 템플릿 제작
- [ ] LF 표준 보고서 형태로 Gamma 프레젠테이션 수동 제작
- [ ] 표지/목차/내용(테이블)/내용(차트)/E.O.D 구성
- [ ] Workspace Template으로 등록

### Step 3: PPTX Export 품질 검증
- [ ] 테마 적용된 프레젠테이션 PPTX export
- [ ] 색상/폰트/로고/레이아웃 유지 여부 확인
- [ ] 스마트 레이아웃(Timeline, 피라미드)의 PPTX 변환 형태 확인
- [ ] 테이블 스타일 (182F54 헤더 + E7EAEE 교대행) 재현 가능 여부

### Step 4: API 테스트
- [ ] Generate API로 기본 PPT 생성 + PPTX export
- [ ] from-template API로 LF 템플릿 기반 생성
- [ ] 크레딧 실제 소모량 측정
- [ ] 응답 시간 측정 (생성 → export 완료까지)

### Step 5: 통합 설계 판단
- [ ] PPTX 품질이 수용 가능한가?
- [ ] 기존 python-pptx 대체 vs 하이브리드 (Gamma + python-pptx)
- [ ] PPTWorker에 Gamma 모드 추가 설계

---

## 8. 참고 링크

- [Gamma Developer Docs](https://developers.gamma.app/docs/getting-started)
- [Generate API Parameters](https://developers.gamma.app/docs/generate-api-parameters-explained)
- [Create from Template API](https://developers.gamma.app/docs/create-from-template-parameters-explained)
- [API Pricing & Access](https://developers.gamma.app/docs/get-access)
- [Custom Theme 생성](https://help.gamma.app/en/articles/11029150-can-i-create-a-custom-theme-for-my-gamma-workspace)
- [Workspace Templates](https://help.gamma.app/en/articles/12590858-how-do-i-use-workspace-templates)
- [PPTX Export 안내](https://help.gamma.app/en/articles/8022861-what-s-the-easiest-way-to-export-my-gamma)
- [Gamma 공식 가격표](https://gamma.app/pricing)
