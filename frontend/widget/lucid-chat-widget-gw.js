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
    userId: '',
    position: 'bottom-right',
    zIndex: 99999,
    widgetWidth: 420,
    widgetHeight: 640,
    buttonSize: 58,
    buttonMargin: 24,
    embedPath: '/embed/gw',
  };

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
        width: ' + config.widgetWidth + 'px; \
        height: ' + config.widgetHeight + 'px; \
        max-height: calc(100vh - 100px); \
        background: #ffffff; \
        border-radius: 16px; \
        box-shadow: 0 8px 40px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.08); \
        display: none; \
        overflow: hidden; \
        border: 1px solid rgba(0,0,0,0.06); \
        position: absolute; \
        bottom: ' + (config.buttonSize + 12) + 'px; \
        ' + (config.position === 'bottom-left' ? 'left' : 'right') + ': 0; \
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

  function buildWidget() {
    container = document.createElement('div');
    container.id = 'lucid-gw-container';

    // 플로팅 버튼
    button = document.createElement('button');
    button.id = 'lucid-gw-button';
    button.innerHTML = '<span class="lucid-gw-icon-chat">' + ICONS.chat + '</span><span class="lucid-gw-icon-close" style="display:none">' + ICONS.close + '</span>';
    button.addEventListener('click', toggleWidget);

    // iframe 래퍼
    var frameWrap = document.createElement('div');
    frameWrap.id = 'lucid-gw-frame-wrap';

    // iframe
    var iframeSrc = config.apiUrl + config.embedPath + '?empno=' + encodeURIComponent(config.userId);
    widgetFrame = document.createElement('iframe');
    widgetFrame.id = 'lucid-gw-frame';
    widgetFrame.src = iframeSrc;
    widgetFrame.setAttribute('allow', 'clipboard-write');

    frameWrap.appendChild(widgetFrame);
    container.appendChild(frameWrap);
    container.appendChild(button);
    document.body.appendChild(container);

    // SPA 환경: body 자식 변경 시 위젯이 사라지면 다시 붙이기
    if (typeof MutationObserver !== 'undefined') {
      new MutationObserver(function () {
        if (!document.body.contains(container)) {
          document.body.appendChild(container);
        }
      }).observe(document.body, { childList: true });
    }
  }

  function toggleWidget() {
    isOpen = !isOpen;
    var frameWrap = document.getElementById('lucid-gw-frame-wrap');
    var chatIcon = button.querySelector('.lucid-gw-icon-chat');
    var closeIcon = button.querySelector('.lucid-gw-icon-close');

    if (isOpen) {
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
