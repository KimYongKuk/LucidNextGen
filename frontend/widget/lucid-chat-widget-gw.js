/**
 * Lucid AI Groupware Widget v1.0
 * 다우오피스 그룹웨어 플로팅 챗 위젯 (iframe 방식)
 *
 * 사용법:
 * <script src="https://lucid.landf.co.kr/widget/lucid-chat-widget-gw.js"></script>
 * <script>
 *   LucidChat.init({
 *     apiUrl: 'https://lucid.landf.co.kr',
 *     userId: '로그인ID',
 *     position: 'bottom-right'
 *   });
 * </script>
 */
(function (global) {
  'use strict';

  var DEFAULT_CONFIG = {
    apiUrl: '',
    userId: '',              // legacy: 평문 사번 (deprecated, authToken으로 대체)
    authToken: '',           // AES 암호화 토큰 (JSP가 생성)
    position: 'bottom-right',
    zIndex: 99999,
    widgetWidth: '30vw',
    widgetMinWidth: 400,
    widgetMaxWidth: 560,
    widgetHeight: 'calc(100vh - 120px)',
    buttonSize: 58,
    buttonMargin: 24,
    embedPath: '/embed/gw',
  };

  var STORAGE_KEY = 'lucid_gw_session_id';
  var config = {};
  var isOpen = false;
  var container, button, widgetFrame;

  function injectStyles() {
    if (document.getElementById('lucid-gw-styles')) return;

    var css = '\
      #lucid-gw-container * { box-sizing: border-box; margin: 0; padding: 0; } \
      #lucid-gw-container { \
        font-family: "Pretendard", "Noto Sans KR", "Malgun Gothic", -apple-system, sans-serif; \
        position: fixed; \
        z-index: ' + config.zIndex + '; \
        bottom: ' + config.buttonMargin + 'px; \
        ' + (config.position === 'bottom-left' ? 'left' : 'right') + ': ' + config.buttonMargin + 'px; \
      } \
      #lucid-gw-button { \
        width: ' + config.buttonSize + 'px; \
        height: ' + config.buttonSize + 'px; \
        border-radius: 50%; \
        border: none; \
        cursor: pointer; \
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%); \
        box-shadow: 0 4px 20px rgba(26,115,232,0.4), 0 2px 8px rgba(0,0,0,0.1); \
        display: flex; \
        align-items: center; \
        justify-content: center; \
        transition: transform 0.2s ease, box-shadow 0.2s ease; \
      } \
      #lucid-gw-button:hover { \
        transform: scale(1.08); \
        box-shadow: 0 6px 28px rgba(26,115,232,0.5), 0 3px 12px rgba(0,0,0,0.15); \
      } \
      #lucid-gw-button:active { transform: scale(0.95); } \
      #lucid-gw-button svg { width: 28px; height: 28px; } \
      #lucid-gw-frame-wrap { \
        width: ' + config.widgetWidth + '; \
        min-width: ' + config.widgetMinWidth + 'px; \
        max-width: ' + config.widgetMaxWidth + 'px; \
        height: ' + config.widgetHeight + '; \
        background: #ffffff; \
        border-radius: 16px; \
        box-shadow: 0 8px 40px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.08); \
        display: none; \
        overflow: hidden; \
        border: 1px solid rgba(0,0,0,0.06); \
        position: fixed; \
        bottom: ' + (config.buttonMargin + config.buttonSize + 12) + 'px; \
        ' + (config.position === 'bottom-left' ? 'left' : 'right') + ': ' + config.buttonMargin + 'px; \
      } \
      #lucid-gw-frame-wrap.lucid-gw-visible { \
        display: block; \
        animation: lucid-gw-slide-up 0.3s ease-out; \
      } \
      #lucid-gw-frame { \
        width: 100%; \
        height: 100%; \
        border: none; \
        border-radius: 16px; \
      } \
      @keyframes lucid-gw-slide-up { \
        from { opacity: 0; transform: translateY(12px); } \
        to { opacity: 1; transform: translateY(0); } \
      } \
    ';

    var style = document.createElement('style');
    style.id = 'lucid-gw-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  var ICONS = {
    chat: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    close: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
  };

  function getEmpno() {
    // GO.session()에서 사번 자동 추출 (다우오피스 전역 객체)
    if (typeof GO !== 'undefined' && typeof GO.session === 'function') {
      var sess = GO.session();
      if (sess && sess.employeeNumber) {
        return sess.employeeNumber;
      }
    }
    return config.userId;
  }

  function buildIframeSrc() {
    // 인증 파라미터: authToken(암호화) 우선, 없으면 legacy empno(평문)
    var sid = getSessionId();
    var gosso = getGossoCookie();
    var src = config.apiUrl + config.embedPath + '?sid=' + encodeURIComponent(sid);
    if (config.authToken) {
      src += '&token=' + encodeURIComponent(config.authToken);
    } else {
      // Legacy fallback (JSP 업데이트 전 과도기 호환)
      var empno = getEmpno();
      if (empno) src += '&empno=' + encodeURIComponent(empno);
    }
    if (gosso) src += '&gosso=' + encodeURIComponent(gosso);
    return src;
  }

  function getGossoCookie() {
    // 그룹웨어 페이지의 GOSSOcookie 추출 (HttpOnly 아니면 접근 가능)
    // iframe에 전달하여 캘린더/일정 쓰기 작업 인증에 사용.
    try {
      var m = document.cookie.match(/(?:^|;\s*)GOSSOcookie=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : '';
    } catch (e) {
      return '';
    }
  }

  function getSessionId() {
    // sessionStorage에서 기존 세션 복원, 없으면 새로 생성
    try {
      var existing = sessionStorage.getItem(STORAGE_KEY);
      if (existing) return existing;
    } catch (e) { /* sessionStorage 접근 불가 시 무시 */ }
    var id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
    try { sessionStorage.setItem(STORAGE_KEY, id); } catch (e) { /* 무시 */ }
    return id;
  }

  function resetSession() {
    // 새 대화 시 세션 초기화
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* 무시 */ }
    widgetFrame = null;
  }

  function buildWidget() {
    container = document.createElement('div');
    container.id = 'lucid-gw-container';

    // 플로팅 버튼
    button = document.createElement('button');
    button.id = 'lucid-gw-button';
    button.title = 'Lucid AI';
    button.innerHTML = '<span class="lucid-gw-icon-chat">' + ICONS.chat + '</span><span class="lucid-gw-icon-close" style="display:none">' + ICONS.close + '</span>';
    button.addEventListener('click', toggleWidget);

    // iframe 래퍼 (iframe은 첫 클릭 시 생성 — GO.session() 초기화 대기)
    var frameWrap = document.createElement('div');
    frameWrap.id = 'lucid-gw-frame-wrap';

    container.appendChild(frameWrap);
    container.appendChild(button);
    // SPA(다우오피스 등)가 body.innerHTML을 갈아엎어도 영향 받지 않도록
    // body가 아닌 documentElement(<html>) 직속에 부착.
    // body 자식이면 SPA가 분리·재부착하는 순간 iframe이 reload되어
    // 진행 중인 채팅/스트리밍 상태가 통째로 날아감.
    document.documentElement.appendChild(container);

    // iframe에서 새 대화 요청 시 세션 리셋
    window.addEventListener('message', function (e) {
      if (e.data && e.data.type === 'lucid-new-chat') {
        resetSession();
        var frameWrap = document.getElementById('lucid-gw-frame-wrap');
        if (frameWrap) frameWrap.innerHTML = '';
        // 다음 열기 시 새 iframe 생성됨
        if (isOpen) {
          var iframeSrc = buildIframeSrc();
          widgetFrame = document.createElement('iframe');
          widgetFrame.id = 'lucid-gw-frame';
          widgetFrame.src = iframeSrc;
          widgetFrame.setAttribute('allow', 'clipboard-write');
          widgetFrame.style.cssText = 'width:100%;height:100%;border:none;border-radius:16px;';
          frameWrap.appendChild(widgetFrame);
        }
      }
    });

    // 과거: body 자식 변경 시 자동 재부착 MutationObserver 운영했으나,
    // 재부착 자체가 iframe을 detach→reattach시켜 무조건 iframe reload를
    // 유발하던 것이 SPA 환경 스트리밍 끊김의 진짜 원인이었음.
    // documentElement에 부착하는 현재 방식에서는 SPA가 컨테이너를 건드리지
    // 않으므로 observer 자체를 제거 (자동복구 시도가 오히려 상태 손실 유발).
  }

  function toggleWidget() {
    isOpen = !isOpen;
    var frameWrap = document.getElementById('lucid-gw-frame-wrap');
    var chatIcon = button.querySelector('.lucid-gw-icon-chat');
    var closeIcon = button.querySelector('.lucid-gw-icon-close');

    if (isOpen) {
      // 서비스 메뉴가 열려있으면 닫기
      if (global.LucidServiceMenu && typeof global.LucidServiceMenu.close === 'function') {
        global.LucidServiceMenu.close();
      }
      // 첫 열기 시 iframe 생성 (이 시점에 GO.session() 확실히 준비됨)
      if (!widgetFrame) {
        var iframeSrc = buildIframeSrc();
        widgetFrame = document.createElement('iframe');
        widgetFrame.id = 'lucid-gw-frame';
        widgetFrame.src = iframeSrc;
        widgetFrame.setAttribute('allow', 'clipboard-write');
        widgetFrame.style.cssText = 'width:100%;height:100%;border:none;border-radius:16px;';
        frameWrap.appendChild(widgetFrame);
      }
      frameWrap.classList.add('lucid-gw-visible');
      chatIcon.style.display = 'none';
      closeIcon.style.display = 'flex';
    } else {
      frameWrap.classList.remove('lucid-gw-visible');
      chatIcon.style.display = 'flex';
      closeIcon.style.display = 'none';
    }
  }

  // ─── Public API ───
  global.LucidChat = {
    init: function (userConfig) {
      // iframe 내부(메일 주소록 등 팝업 페이지)에서는 위젯 렌더링 스킵
      // custom_index_header.jsp가 팝업 iframe에도 include되어 중복 표시되는 것 방지
      try {
        if (window.self !== window.top) return;
      } catch (e) {
        // cross-origin 접근 차단 시에도 iframe 안으로 간주하고 스킵
        return;
      }

      // SPA 환경(예: 다우오피스)에서 모듈 이동 시 헤더 JSP가 재주입되며 init이 다시 호출됨.
      // 이미 위젯이 살아있으면 재생성하지 않고 기존 인스턴스 유지 → 진행 중 스트리밍/대화 보존.
      if (document.getElementById('lucid-gw-container')) return;

      config = {};
      for (var key in DEFAULT_CONFIG) {
        config[key] = DEFAULT_CONFIG[key];
      }
      if (userConfig) {
        for (var key2 in userConfig) {
          config[key2] = userConfig[key2];
        }
      }

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
          if (document.getElementById('lucid-gw-container')) return;
          injectStyles();
          buildWidget();
        });
      } else {
        injectStyles();
        buildWidget();
      }
    },

    open: function () { if (!isOpen) toggleWidget(); },
    close: function () { if (isOpen) toggleWidget(); },
    toggle: function () { toggleWidget(); },

    destroy: function () {
      if (container && container.parentNode) {
        container.parentNode.removeChild(container);
      }
      var style = document.getElementById('lucid-gw-styles');
      if (style) style.remove();
    },
  };

})(typeof window !== 'undefined' ? window : this);
