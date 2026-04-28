# 2026-04-28 그룹웨어 위젯 iframe 중복 렌더링 차단

## 개요
다우오피스 그룹웨어의 `custom_index_header.jsp`가 메일 주소록 등 팝업 iframe 페이지에도 동일하게 include되어, Lucid 챗 위젯과 서비스 메뉴 위젯이 부모 창과 iframe 양쪽에 중복 렌더링되는 문제를 해결.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| frontend/widget/lucid-chat-widget-gw.js | 수정 | `init()` 진입 시 iframe 내부 감지 후 조기 반환 |
| frontend/widget/lucid-service-menu.js | 수정 | 동일한 iframe 가드 추가 |

## 상세 내용

### 증상
- 메일 작성 화면에서 "주소록" 버튼 클릭 시 열리는 팝업(`#mail_write_address_add_popup` 안의 `iframe[src="/app/contact/connector/all"]`) 우측 하단에 챗봇/서비스 메뉴 버튼이 한 번 더 표시됨.
- 부모 창에 이미 떠 있는 위젯 위로 iframe 내부 위젯이 겹쳐 보임.

### 원인
`custom_index_header.jsp`는 다우오피스 공통 헤더 include 대상이라, 일반 페이지 뿐 아니라 동일 origin으로 로드되는 팝업 iframe(주소록, 결재 팝업 등)에도 그대로 주입됨. 위젯 스크립트가 매번 평가되며 `LucidChat.init()` / `LucidServiceMenu.init()`이 호출되어 iframe 자체에 또 한 벌 렌더링됨.

### 픽스
두 위젯 모두 `init()` 진입부에 `window.self !== window.top` 체크를 두고, iframe 내부면 조기 반환:

```js
init: function (userConfig) {
  try {
    if (window.self !== window.top) return;
  } catch (e) {
    // cross-origin 접근 차단 시에도 iframe 안으로 간주하여 스킵
    return;
  }
  // ... 기존 초기화 로직
}
```

`try/catch`는 cross-origin iframe에서 `window.top` 접근 시 SecurityError 발생할 수 있는 케이스 방어용. 어차피 cross-origin 이라면 부모 페이지가 우리 위젯을 직접 띄우는 정상 시나리오가 아니므로 안전하게 스킵.

### 영향 범위 점검
- 본체 페이지(top-level): `window.self === window.top` 이므로 정상 동작 (변화 없음).
- 우리 측 `/embed/gw` iframe: 다른 origin(lucid.landf.co.kr)이고 `custom_index_header.jsp` 미적용이므로 위젯 스크립트 자체가 로드되지 않음 → 영향 없음.
- 그룹웨어 동일 origin 팝업 iframe(주소록 등): `init()` 진입 즉시 반환 → DOM 조작/이벤트 등록 없음 → 위젯 사라짐.

## 결정 사항 및 주의점
- JSP 측에서 URL 패턴(`/app/contact/`, `/popup/` 등)으로 include 분기하는 방식도 고려했으나, 다우오피스 팝업 경로가 다양하고 향후 추가 시마다 JSP를 손봐야 해서 위젯 JS 한 곳에서 일괄 차단하는 방식 채택.
- `LucidChat.init()`이 큐 패턴(stub)으로 변경될 경우, stub 측에도 동일 가드를 두지 않으면 큐에만 쌓이고 실제 init은 스킵되는 정상 동작이 유지됨 — 큐를 비우는 본 위젯 코드에서 한 번 막으면 충분.
- 배포: 캐시(`Cache-Control: max-age=3600`)로 인해 사용자에게 반영되기까지 최대 1시간 지연 가능. 즉시 검증 시 강력 새로고침(Ctrl+F5).
