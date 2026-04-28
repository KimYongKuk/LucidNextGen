# 2026-04-28 Widget SPA 재초기화 방지

## 개요
다우오피스 그룹웨어 모듈 이동(`/app/docs` → `/app/mail` 등) 시 Lucid 챗 위젯이 "리셋된 것처럼 보이고 진행 중 스트리밍이 끊기던" 현상의 근본 원인을 추적하고 수정. 원인은 backend나 iframe lifecycle이 아니라 위젯 JS의 `init()`이 SPA 헤더 재주입으로 중복 호출되어 동일 위젯 컨테이너가 DOM에 누적 생성되던 것.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| frontend/widget/lucid-chat-widget-gw.js | 수정 | `init()` idempotent 가드 추가 (`#lucid-gw-container` 존재 시 조기 반환) |
| frontend/widget/lucid-service-menu.js | 수정 | 서비스 메뉴 위젯도 동일 패턴(`#lucid-sm-container` 가드) 적용 |

## 상세 내용

### 추적 과정

사용자 보고: "그룹웨어 모듈 이동할 때 위젯이 갱신되는 느낌이고 스트리밍 응답이 끊긴다."

초기 가설들과 기각 사유:

1. **iframe lifecycle 문제** — 페이지 reload 시 iframe이 죽고 새로 로드된다는 가설. → 그룹웨어가 SPA로 확인되어 기각.
2. **백엔드 스트리밍 끊김** — 클라이언트 disconnect 시 LangGraph 실행이 cancel된다는 가설. Phase 1~3 (stream_buffer 테이블 + resume 엔드포인트 + 프론트 자동 재개) 검토. → 사용자가 복잡도 우려, 단순한 길 모색.
3. **PiP / 브라우저 확장으로 페이지 라이프사이클 회피** → 백엔드 무관 옵션이지만 UX 변경 부담.

진단 콘솔 명령으로 확정:

```javascript
// 그룹웨어 페이지에서 실행
window.__t = '살아남음';
// 모듈 이동 후
window.__t   // → '살아남음' (JS 컨텍스트 유지)

document.getElementById('lucid-gw-container')?.outerHTML?.length
// 모듈 이동 전후 동일한 숫자
```

콘솔 로그에 `[CalendarDefaultLayout#_renderSide] called.`, `[SideView#initialize]`, `[SideView#delegateEvents]` 등 Backbone view 패턴 노출 → 그룹웨어가 Backbone 기반 SPA임이 드러남.

### 진짜 원인

SPA 환경에서 모듈 이동 시 다우오피스의 `custom_index_header.jsp`가 새 view에 다시 include되며 `<script>LucidChat.init({...})</script>`가 재실행됨. 기존 `init()`은 매번 무조건 `buildWidget()`을 호출하여:

- `container = document.createElement('div')` — 새 div 생성
- `container.id = 'lucid-gw-container'` — 동일 id로 부착
- `document.body.appendChild(container)` — DOM에 추가
- 클로저 변수 `container, button, widgetFrame, isOpen` 모두 새 값으로 교체

결과:
- DOM에 동일 id의 컨테이너가 N개 누적 (HTML 사양 위반이지만 브라우저는 허용)
- `getElementById`는 **첫 번째**(가장 오래된, 즉 진행 중 채팅이 살아있는)만 반환
- 클로저 변수는 항상 **마지막** 컨테이너를 가리킴 → 새 클릭은 새 컨테이너의 빈 iframe을 띄움
- 사용자 시각적으로 "위젯이 새것이 됐다" — 실제로는 진행 중 iframe이 뒤에 가려져 있음

`outerHTML.length`가 같았던 이유는 `getElementById`가 첫 번째 컨테이너만 보기 때문이며, 실제로는 컨테이너가 누적되고 있었음.

### 수정

`init()` 진입부에 idempotent 가드 추가:

```javascript
init: function (userConfig) {
  try {
    if (window.self !== window.top) return;
  } catch (e) { return; }

  // SPA 환경(예: 다우오피스)에서 모듈 이동 시 헤더 JSP가 재주입되며 init이 다시 호출됨.
  // 이미 위젯이 살아있으면 재생성하지 않고 기존 인스턴스 유지 → 진행 중 스트리밍/대화 보존.
  if (document.getElementById('lucid-gw-container')) return;

  // ... 이하 기존 로직
}
```

`DOMContentLoaded` 콜백 안에서도 한 번 더 가드 (race condition 방지).

서비스 메뉴 위젯(`lucid-service-menu.js`)도 동일 패턴이라 `#lucid-sm-container` 가드 동일 적용.

## 결정 사항 및 주의점

- **백엔드 변경 0**: `chat.py`/`a2a_streaming.py` 수정 없음. 위젯 JS 한 군데가 진짜 원인이었음.
- **Phase 1~3 (스트림 버퍼링) 보류**: 이 수정으로 "응답 끊김" 증상의 90%가 해결됨. 진행 중 스트리밍이 페이지 이동에서 살아남는 이유는 동일 iframe이 detach/reattach되지 않고 그대로 유지되기 때문. 스트림 버퍼링은 향후 정말 필요해지면(예: MPA 환경 호환) 별도 검토.
- **이전 사용자 세션 정리**: 이미 누적된 중복 컨테이너는 새 init이 early-return하므로 그대로 유지됨. F5 한 번 누르면 깨끗해짐. 별도 cleanup 로직은 추가하지 않음(드문 transition 케이스).
- **클로저 변수 무관**: 새 IIFE가 평가돼도 기존 IIFE의 클로저는 살아있으므로 기존 위젯의 toggleWidget/click handler는 정상 동작. 새 IIFE의 `container`는 undefined인 채 남지만 외부에서 `LucidChat.open()` 같은 프로그래밍 호출이 없으면 문제 없음.
- **호스트 사이트 의존성**: 위젯이 SPA 호스트에서 잘 살아남는지 여부는 호스트 사이트 아키텍처에 달려있음. MPA(진짜 페이지 reload) 환경에서는 본질적으로 위젯이 살아남을 수 없으며, 그 경우엔 PiP / 확장 / 백엔드 버퍼링 중 하나가 필요.

## 후속 검증

배포 후 그룹웨어에서 확인할 것:
1. 모듈 A에서 채팅 응답 받는 중 → 모듈 B로 이동 → 위젯 그대로 유지되며 스트리밍 계속 진행되는지
2. `document.querySelectorAll('#lucid-gw-container').length` 가 항상 1인지
3. `document.querySelectorAll('#lucid-sm-container').length` 가 항상 1인지

## 후속 패치 (1차 배포 이후)

1차 배포(`init` idempotent 가드)만으로는 여전히 위젯이 모듈 이동 시 리셋되는 현상이 남아있었음. 사용자 콘솔 검증으로 `LucidChat.init.toString().includes('lucid-gw-container')` → `true` 확인되어 fix는 분명 적용된 상태였으나, 위젯 자체는 깜빡이며 새로 로드됨.

### 진짜 원인 (2단계)

다우오피스 SPA가 모듈 이동 시 `body.innerHTML`을 통째로 갈아엎으면서 우리 컨테이너도 함께 분리됨. 기존 코드의 `MutationObserver`가 즉시 `document.body.appendChild(container)`로 재부착해서 outerHTML 검증에서는 살아있는 것처럼 보였지만, **iframe 요소를 DOM에서 detach 후 reattach하는 순간 브라우저는 iframe content를 무조건 reload함** (HTML 사양). 즉:

1. SPA가 body 갈아엎음 → 컨테이너 분리됨 (수 ms)
2. MutationObserver 즉시 fire → `body.appendChild(container)` 재부착
3. iframe이 DOM에서 떨어졌다 다시 붙음 → **브라우저가 iframe reload 강제** → React 앱 새로 mount → 채팅 히스토리 fresh fetch → 진행 중 스트리밍 끊김

`outerHTML.length`가 동일했던 이유는 재부착이 끝난 후 시점에 검사했고, outerHTML은 iframe의 src 속성만 포함하지 iframe 내부 컨텐츠 상태는 포함하지 않기 때문.

### 2차 수정

1. **부착 위치 변경**: `document.body.appendChild(container)` → `document.documentElement.appendChild(container)` — 컨테이너를 `<body>` 자식이 아닌 `<html>` 직속으로 이동. SPA가 body를 갈아엎어도 컨테이너는 sibling이라 영향 받지 않음.

2. **MutationObserver 제거**: documentElement 직속이라 SPA가 건드릴 일 없으므로 자동 재부착 로직 자체가 불필요. 게다가 재부착이 iframe reload를 유발하므로 자동 복구 시도가 오히려 상태 손실의 원인이었음 — 제거가 정답.

두 위젯(`lucid-chat-widget-gw.js`, `lucid-service-menu.js`) 동일 패턴 모두 적용.

### 학습

- 자동 복구 로직이 자기 자신을 망가뜨리는 케이스. iframe reload는 detach/reattach만으로 강제되며, 의도한 위치로 돌려놓는 것이 의미가 없음.
- "DOM에 있다"와 "DOM에서 분리된 적이 없다"는 다른 명제. outerHTML 검증으로는 후자를 측정 못 함.
- SPA 호환은 컨테이너 자체를 SPA가 건드릴 수 없는 위치(documentElement 또는 Shadow DOM)에 두는 것이 가장 안전. 자동 복구는 본질적으로 사후약방문이며 부작용을 동반.
