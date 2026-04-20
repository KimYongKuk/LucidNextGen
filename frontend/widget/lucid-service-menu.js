/**
 * Lucid Service Menu Widget v1.0
 * 그룹웨어 플로팅 서비스 메뉴 위젯
 *
 * 사용법:
 * <script src="https://lucid.landf.co.kr/widget/lucid-service-menu.js"></script>
 * <script>
 *   LucidServiceMenu.init({
 *     apiUrl: 'https://lucid.landf.co.kr'
 *   });
 * </script>
 */
(function (global) {
  'use strict';

  var DEFAULT_CONFIG = {
    apiUrl: '',
    position: 'bottom-right',
    zIndex: 99998,
    buttonSize: 58,
    buttonMargin: 24,
    chatButtonGap: 12,      // 챗봇 버튼과의 간격
    menuWidth: 220,
  };

  var config = {};
  var isOpen = false;
  var container, button, menuPanel;
  var menuItems = [];
  var loaded = false;

  // ─── SVG 아이콘 ───
  var ICONS = {
    grid: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect></svg>',
    close: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
    // 메뉴 아이콘
    users: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
    shield: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>',
    briefcase: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>',
    bot: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"></rect><circle cx="12" cy="5" r="2"></circle><path d="M12 7v4"></path><line x1="8" y1="16" x2="8" y2="16"></line><line x1="16" y1="16" x2="16" y2="16"></line></svg>',
    rocket: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"></path><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"></path><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"></path><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"></path></svg>',
    layout: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>',
    link: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>',
  };

  function getIcon(name) {
    return ICONS[name] || ICONS.link;
  }

  function injectStyles() {
    if (document.getElementById('lucid-sm-styles')) return;

    var side = config.position === 'bottom-left' ? 'left' : 'right';
    // 챗봇 버튼 옆 (왼쪽)에 배치: 챗봇 margin + 챗봇 버튼 + gap
    var sideOffset = config.buttonMargin + config.buttonSize + config.chatButtonGap;

    var css = '\
      #lucid-sm-container * { box-sizing: border-box; margin: 0; padding: 0; } \
      #lucid-sm-container { \
        font-family: "Pretendard", "Noto Sans KR", "Malgun Gothic", -apple-system, sans-serif; \
        position: fixed; \
        z-index: ' + config.zIndex + '; \
        bottom: ' + config.buttonMargin + 'px; \
        ' + side + ': ' + sideOffset + 'px; \
      } \
      #lucid-sm-button { \
        width: ' + config.buttonSize + 'px; \
        height: ' + config.buttonSize + 'px; \
        border-radius: 50%; \
        border: none; \
        cursor: pointer; \
        background: linear-gradient(135deg, #6366f1 0%, #4338ca 100%); \
        box-shadow: 0 4px 16px rgba(99,102,241,0.4), 0 2px 6px rgba(0,0,0,0.1); \
        display: flex; \
        align-items: center; \
        justify-content: center; \
        transition: transform 0.2s ease, box-shadow 0.2s ease; \
      } \
      #lucid-sm-button:hover { \
        transform: scale(1.08); \
        box-shadow: 0 6px 24px rgba(99,102,241,0.5), 0 3px 10px rgba(0,0,0,0.15); \
      } \
      #lucid-sm-button:active { transform: scale(0.95); } \
      #lucid-sm-button svg { width: 22px; height: 22px; } \
      #lucid-sm-menu { \
        position: absolute; \
        bottom: ' + (config.buttonSize + 12) + 'px; \
        ' + side + ': 0; \
        width: ' + config.menuWidth + 'px; \
        background: #ffffff; \
        border-radius: 14px; \
        box-shadow: 0 8px 32px rgba(0,0,0,0.16), 0 2px 8px rgba(0,0,0,0.08); \
        border: 1px solid rgba(0,0,0,0.06); \
        display: none; \
        overflow: hidden; \
      } \
      #lucid-sm-menu.lucid-sm-visible { \
        display: block; \
        animation: lucid-sm-slide-up 0.25s ease-out; \
      } \
      #lucid-sm-menu-header { \
        padding: 14px 16px 10px; \
        font-size: 13px; \
        font-weight: 700; \
        color: #4338ca; \
        border-bottom: 1px solid #f1f1f4; \
        letter-spacing: -0.02em; \
      } \
      #lucid-sm-menu-list { \
        list-style: none; \
        padding: 6px 0; \
      } \
      #lucid-sm-menu-list li { \
        margin: 0; \
      } \
      #lucid-sm-menu-list a { \
        display: flex; \
        align-items: center; \
        gap: 10px; \
        padding: 10px 16px; \
        color: #374151; \
        text-decoration: none; \
        font-size: 14px; \
        font-weight: 500; \
        transition: background 0.15s ease; \
        cursor: pointer; \
        letter-spacing: -0.01em; \
      } \
      #lucid-sm-menu-list a:hover { \
        background: #f5f3ff; \
        color: #4338ca; \
      } \
      #lucid-sm-menu-list a svg { \
        width: 18px; \
        height: 18px; \
        flex-shrink: 0; \
        color: #6366f1; \
      } \
      #lucid-sm-menu-list a .lucid-sm-ext { \
        margin-left: auto; \
        width: 14px; \
        height: 14px; \
        color: #9ca3af; \
      } \
      #lucid-sm-empty { \
        padding: 20px 16px; \
        text-align: center; \
        color: #9ca3af; \
        font-size: 13px; \
      } \
      @keyframes lucid-sm-slide-up { \
        from { opacity: 0; transform: translateY(8px); } \
        to { opacity: 1; transform: translateY(0); } \
      } \
    ';

    var style = document.createElement('style');
    style.id = 'lucid-sm-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function getEmpno() {
    if (typeof GO !== 'undefined' && typeof GO.session === 'function') {
      var sess = GO.session();
      if (sess && sess.employeeNumber) return sess.employeeNumber;
    }
    return config.userId || '';
  }

  function fetchMenus(callback) {
    if (loaded) { callback(menuItems); return; }

    var empno = getEmpno();
    if (!empno) { callback([]); return; }

    var xhr = new XMLHttpRequest();
    xhr.open('GET', config.apiUrl + '/api/v1/service-menu?empno=' + encodeURIComponent(empno));
    xhr.onload = function () {
      if (xhr.status === 200) {
        try {
          var data = JSON.parse(xhr.responseText);
          menuItems = data.menus || [];
          loaded = true;
        } catch (e) { menuItems = []; }
      }
      callback(menuItems);
    };
    xhr.onerror = function () { callback([]); };
    xhr.send();
  }

  function renderMenu(items) {
    var list = menuPanel.querySelector('#lucid-sm-menu-list');
    var empty = menuPanel.querySelector('#lucid-sm-empty');
    list.innerHTML = '';

    if (!items.length) {
      empty.style.display = 'block';
      list.style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    list.style.display = 'block';

    items.forEach(function (item) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = item.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        window.open(item.url, '_blank', 'noopener,noreferrer');
      });
      a.innerHTML =
        '<span class="lucid-sm-icon">' + getIcon(item.icon) + '</span>' +
        '<span>' + item.name + '</span>' +
        '<span class="lucid-sm-ext">' + ICONS.link + '</span>';
      li.appendChild(a);
      list.appendChild(li);
    });
  }

  function buildWidget() {
    container = document.createElement('div');
    container.id = 'lucid-sm-container';

    // 플로팅 버튼
    button = document.createElement('button');
    button.id = 'lucid-sm-button';
    button.title = '서비스 메뉴';
    button.innerHTML =
      '<span class="lucid-sm-icon-grid">' + ICONS.grid + '</span>' +
      '<span class="lucid-sm-icon-close" style="display:none">' + ICONS.close + '</span>';
    button.addEventListener('click', toggleMenu);

    // 메뉴 패널
    menuPanel = document.createElement('div');
    menuPanel.id = 'lucid-sm-menu';
    menuPanel.innerHTML =
      '<div id="lucid-sm-menu-header">Services</div>' +
      '<ul id="lucid-sm-menu-list"></ul>' +
      '<div id="lucid-sm-empty" style="display:none">메뉴가 없습니다</div>';

    container.appendChild(menuPanel);
    container.appendChild(button);
    document.body.appendChild(container);

    // 외부 클릭 시 닫기
    document.addEventListener('click', function (e) {
      if (isOpen && !container.contains(e.target)) {
        closeMenu();
      }
    });

    // SPA 환경: body 변경 시 위젯 재부착
    if (typeof MutationObserver !== 'undefined') {
      new MutationObserver(function () {
        if (!document.body.contains(container)) {
          document.body.appendChild(container);
        }
      }).observe(document.body, { childList: true });
    }
  }

  function toggleMenu() {
    if (isOpen) { closeMenu(); } else { openMenu(); }
  }

  function openMenu() {
    isOpen = true;
    // 루시드 챗봇이 열려있으면 닫기
    if (global.LucidChat && typeof global.LucidChat.close === 'function') {
      global.LucidChat.close();
    }
    var gridIcon = button.querySelector('.lucid-sm-icon-grid');
    var closeIcon = button.querySelector('.lucid-sm-icon-close');
    gridIcon.style.display = 'none';
    closeIcon.style.display = 'flex';

    fetchMenus(function (items) {
      renderMenu(items);
      menuPanel.classList.add('lucid-sm-visible');
    });
  }

  function closeMenu() {
    isOpen = false;
    menuPanel.classList.remove('lucid-sm-visible');
    var gridIcon = button.querySelector('.lucid-sm-icon-grid');
    var closeIcon = button.querySelector('.lucid-sm-icon-close');
    gridIcon.style.display = 'flex';
    closeIcon.style.display = 'none';
  }

  // ─── Public API ───
  global.LucidServiceMenu = {
    init: function (userConfig) {
      config = {};
      for (var key in DEFAULT_CONFIG) config[key] = DEFAULT_CONFIG[key];
      if (userConfig) {
        for (var k in userConfig) config[k] = userConfig[k];
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

    open: function () { if (!isOpen) openMenu(); },
    close: function () { if (isOpen) closeMenu(); },
    toggle: function () { toggleMenu(); },

    destroy: function () {
      if (container && container.parentNode) container.parentNode.removeChild(container);
      var style = document.getElementById('lucid-sm-styles');
      if (style) style.remove();
    },
  };

})(typeof window !== 'undefined' ? window : this);
