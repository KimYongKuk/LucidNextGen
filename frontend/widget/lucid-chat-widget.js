/**
 * Lucid AI Chat Widget v1.0
 * L&F 그룹웨어 플로팅 챗 위젯
 * 
 * 사용법:
 * <script src="/static/lucid-chat-widget.js"></script>
 * <script>
 *   LucidChat.init({
 *     apiUrl: 'https://your-api-domain.com',
 *     userId: '<%= session.getAttribute("empNo") %>',
 *     userName: '<%= session.getAttribute("empNm") %>',
 *     position: 'bottom-right'
 *   });
 * </script>
 */
(function (global) {
  'use strict';

  // ─── Configuration ───
  const DEFAULT_CONFIG = {
    apiUrl: '',
    userId: '',
    userName: '',
    position: 'bottom-right',       // bottom-right | bottom-left
    theme: 'blue',
    zIndex: 99999,
    widgetWidth: 400,
    widgetHeight: 560,
    buttonSize: 58,
    buttonMargin: 24,
    placeholder: '질문을 입력하세요...',
    title: 'Lucid AI',
    subtitle: 'L&F 업무 AI 어시스턴트',
    quickActions: ['SAP 사용법', '사내규정 조회', '업무양식 안내'],
    // SSE 설정
    streamEndpoint: '/api/v1/chat/message/stream',
    // SSE 커스텀 JSON 이벤트 타입 매핑 (백엔드 a2a_streaming 형식)
    sseTokenType: 'content',        // 토큰 스트리밍 이벤트 타입
    sseDoneType: 'done',            // 완료 이벤트 타입
    sseErrorType: 'error',          // 에러 이벤트 타입
    sseContentField: 'chunk',       // 토큰 내용 필드명
    sseStatusField: 'type',         // 이벤트 타입 필드명
    // 추가 SSE 이벤트 타입 (선택)
    sseThinkingType: 'thinking',    // 사고 과정 이벤트
    sseSourceType: 'source',        // 출처/참조 이벤트
    sseToolType: 'tool_status',     // 도구 호출 이벤트
  };

  let config = {};
  let state = {
    isOpen: false,
    messages: [],
    isStreaming: false,
    sessionId: null,
    abortController: null,
  };

  // ─── DOM Elements ───
  let container, button, widget, messagesEl, inputEl, sendBtn, badge;

  // ─── Utility: Generate Session ID ───
  function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  }

  // ─── Utility: Simple Markdown to HTML ───
  function renderMarkdown(text) {
    if (!text) return '';
    let html = text
      // Code blocks (```)
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="lcd-code-block"><code>$2</code></pre>')
      // Inline code
      .replace(/`([^`]+)`/g, '<code class="lcd-inline-code">$1</code>')
      // Bold
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      // Italic
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="lcd-link">$1</a>')
      // Line breaks
      .replace(/\n/g, '<br>');
    return html;
  }

  // ─── Utility: Escape HTML ───
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // ─── Utility: Time format ───
  function formatTime(date) {
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
  }

  // ─── Inject Styles ───
  function injectStyles() {
    if (document.getElementById('lucid-chat-widget-styles')) return;

    const css = `
      /* ─── Lucid Chat Widget Styles ─── */
      #lcd-container * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }

      #lcd-container {
        font-family: 'Pretendard', 'Noto Sans KR', 'Malgun Gothic', -apple-system, sans-serif;
        font-size: 14px;
        line-height: 1.5;
        position: fixed;
        z-index: ${config.zIndex};
      }

      /* ─── Float Button ─── */
      #lcd-button {
        width: ${config.buttonSize}px;
        height: ${config.buttonSize}px;
        border-radius: 50%;
        border: none;
        cursor: pointer;
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        box-shadow: 0 4px 20px rgba(26,115,232,0.4), 0 2px 8px rgba(0,0,0,0.1);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        position: relative;
      }
      #lcd-button:hover {
        transform: scale(1.08);
        box-shadow: 0 6px 28px rgba(26,115,232,0.5), 0 3px 12px rgba(0,0,0,0.15);
      }
      #lcd-button:active {
        transform: scale(0.95);
      }
      #lcd-button svg {
        width: 28px;
        height: 28px;
        transition: transform 0.3s ease;
      }
      #lcd-button.lcd-open svg.lcd-icon-chat {
        display: none;
      }
      #lcd-button.lcd-open svg.lcd-icon-close {
        display: block;
      }
      #lcd-button:not(.lcd-open) svg.lcd-icon-chat {
        display: block;
      }
      #lcd-button:not(.lcd-open) svg.lcd-icon-close {
        display: none;
      }

      /* Badge */
      #lcd-badge {
        position: absolute;
        top: -4px;
        right: -4px;
        background: #e53935;
        color: white;
        font-size: 11px;
        font-weight: 700;
        min-width: 20px;
        height: 20px;
        border-radius: 10px;
        display: none;
        align-items: center;
        justify-content: center;
        padding: 0 5px;
        border: 2px solid white;
      }

      /* ─── Chat Widget ─── */
      #lcd-widget {
        width: ${config.widgetWidth}px;
        height: ${config.widgetHeight}px;
        max-height: calc(100vh - 100px);
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 8px 40px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.08);
        display: none;
        flex-direction: column;
        overflow: hidden;
        border: 1px solid rgba(0,0,0,0.06);
        position: absolute;
        bottom: ${config.buttonSize + 12}px;
      }
      #lcd-widget.lcd-visible {
        display: flex;
        animation: lcd-slide-up 0.3s ease-out;
      }

      /* Position */
      .lcd-pos-bottom-right #lcd-button,
      .lcd-pos-bottom-right #lcd-widget {
        right: 0;
      }
      .lcd-pos-bottom-left #lcd-button,
      .lcd-pos-bottom-left #lcd-widget {
        left: 0;
      }

      /* ─── Header ─── */
      #lcd-header {
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        padding: 14px 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-shrink: 0;
      }
      #lcd-header-left {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      #lcd-header-icon {
        width: 32px;
        height: 32px;
        border-radius: 8px;
        background: rgba(255,255,255,0.15);
        display: flex;
        align-items: center;
        justify-content: center;
      }
      #lcd-header-icon svg {
        width: 20px;
        height: 20px;
      }
      #lcd-header-title {
        color: white;
        font-weight: 700;
        font-size: 15px;
      }
      #lcd-header-subtitle {
        color: rgba(255,255,255,0.7);
        font-size: 11px;
        margin-top: 1px;
      }
      #lcd-header-actions {
        display: flex;
        gap: 4px;
      }
      .lcd-header-btn {
        width: 30px;
        height: 30px;
        border-radius: 6px;
        border: none;
        background: rgba(255,255,255,0.12);
        color: white;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        transition: background 0.15s;
      }
      .lcd-header-btn:hover {
        background: rgba(255,255,255,0.25);
      }

      /* ─── Messages Area ─── */
      #lcd-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px 14px;
        display: flex;
        flex-direction: column;
        gap: 14px;
        background: #f7f8fb;
        scroll-behavior: smooth;
      }
      #lcd-messages::-webkit-scrollbar {
        width: 5px;
      }
      #lcd-messages::-webkit-scrollbar-track {
        background: transparent;
      }
      #lcd-messages::-webkit-scrollbar-thumb {
        background: #ccc;
        border-radius: 3px;
      }

      /* Welcome */
      .lcd-welcome {
        text-align: center;
        padding: 20px 10px;
      }
      .lcd-welcome-icon {
        font-size: 36px;
        margin-bottom: 10px;
      }
      .lcd-welcome-title {
        font-size: 16px;
        font-weight: 700;
        color: #333;
        margin-bottom: 4px;
      }
      .lcd-welcome-desc {
        font-size: 12px;
        color: #888;
        line-height: 1.6;
      }

      /* Message Bubble */
      .lcd-msg {
        display: flex;
        gap: 8px;
        max-width: 100%;
        animation: lcd-fade-in 0.2s ease-out;
      }
      .lcd-msg-user {
        flex-direction: row-reverse;
      }
      .lcd-msg-avatar {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-top: 2px;
      }
      .lcd-msg-ai .lcd-msg-avatar {
        background: linear-gradient(135deg, #1a73e8, #0d47a1);
      }
      .lcd-msg-ai .lcd-msg-avatar svg {
        width: 18px;
        height: 18px;
      }
      .lcd-msg-bubble {
        max-width: 78%;
        padding: 10px 14px;
        font-size: 13px;
        line-height: 1.65;
        word-break: break-word;
      }
      .lcd-msg-user .lcd-msg-bubble {
        background: #1a73e8;
        color: white;
        border-radius: 14px 14px 4px 14px;
      }
      .lcd-msg-ai .lcd-msg-bubble {
        background: white;
        color: #333;
        border-radius: 14px 14px 14px 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        border: 1px solid rgba(0,0,0,0.04);
      }
      .lcd-msg-time {
        font-size: 10px;
        color: #aaa;
        margin-top: 4px;
        display: block;
      }
      .lcd-msg-user .lcd-msg-time {
        text-align: right;
      }

      /* Markdown elements inside bubble */
      .lcd-msg-bubble strong { font-weight: 600; }
      .lcd-msg-bubble em { font-style: italic; }
      .lcd-msg-bubble .lcd-inline-code {
        background: rgba(0,0,0,0.06);
        padding: 1px 5px;
        border-radius: 3px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 12px;
      }
      .lcd-msg-user .lcd-msg-bubble .lcd-inline-code {
        background: rgba(255,255,255,0.2);
      }
      .lcd-msg-bubble .lcd-code-block {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 10px 12px;
        border-radius: 8px;
        margin: 8px 0;
        overflow-x: auto;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 12px;
        line-height: 1.5;
      }
      .lcd-msg-bubble .lcd-code-block code {
        background: none;
        padding: 0;
        color: inherit;
      }
      .lcd-msg-bubble .lcd-link {
        color: #1a73e8;
        text-decoration: underline;
      }
      .lcd-msg-user .lcd-msg-bubble .lcd-link {
        color: #bbdefb;
      }

      /* Typing Indicator */
      .lcd-typing {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .lcd-typing-dots {
        display: flex;
        gap: 4px;
        background: white;
        padding: 10px 16px;
        border-radius: 14px 14px 14px 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        border: 1px solid rgba(0,0,0,0.04);
      }
      .lcd-typing-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #aaa;
        animation: lcd-bounce 1s ease-in-out infinite;
      }
      .lcd-typing-dot:nth-child(2) { animation-delay: 0.15s; }
      .lcd-typing-dot:nth-child(3) { animation-delay: 0.3s; }

      /* Status messages (thinking, tool_call) */
      .lcd-status-msg {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 4px 0;
        font-size: 11px;
        color: #888;
        animation: lcd-fade-in 0.2s ease-out;
      }
      .lcd-status-msg .lcd-status-icon {
        width: 14px;
        height: 14px;
        animation: lcd-spin 1.5s linear infinite;
      }

      /* ─── Quick Actions ─── */
      #lcd-quick-actions {
        padding: 8px 14px 4px;
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        background: white;
        border-top: 1px solid #f0f0f0;
      }
      .lcd-quick-btn {
        background: #f0f4ff;
        border: 1px solid rgba(26,115,232,0.12);
        border-radius: 20px;
        padding: 5px 12px;
        font-size: 11px;
        color: #1a73e8;
        cursor: pointer;
        font-family: inherit;
        font-weight: 500;
        transition: background 0.15s;
        white-space: nowrap;
      }
      .lcd-quick-btn:hover {
        background: #e3ecff;
      }
      .lcd-quick-btn:disabled {
        opacity: 0.5;
        cursor: default;
      }

      /* ─── Input Area ─── */
      #lcd-input-area {
        padding: 10px 14px 14px;
        display: flex;
        gap: 8px;
        background: white;
        align-items: flex-end;
      }
      #lcd-input {
        flex: 1;
        padding: 10px 14px;
        border: 1.5px solid #e0e0e0;
        border-radius: 12px;
        font-size: 13px;
        font-family: inherit;
        outline: none;
        transition: border-color 0.2s, background 0.2s;
        background: #fafafa;
        resize: none;
        min-height: 40px;
        max-height: 100px;
        overflow-y: auto;
        line-height: 1.4;
      }
      #lcd-input:focus {
        border-color: #1a73e8;
        background: white;
      }
      #lcd-input::placeholder {
        color: #bbb;
      }
      #lcd-send {
        width: 40px;
        height: 40px;
        border-radius: 10px;
        border: none;
        background: #e0e0e0;
        cursor: default;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: all 0.2s;
      }
      #lcd-send.lcd-active {
        background: linear-gradient(135deg, #1a73e8, #0d47a1);
        cursor: pointer;
      }
      #lcd-send.lcd-active:hover {
        box-shadow: 0 2px 8px rgba(26,115,232,0.4);
      }
      #lcd-send svg {
        width: 18px;
        height: 18px;
      }

      /* ─── Animations ─── */
      @keyframes lcd-slide-up {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes lcd-fade-in {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      @keyframes lcd-bounce {
        0%, 60%, 100% { transform: translateY(0); }
        30% { transform: translateY(-4px); }
      }
      @keyframes lcd-spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }

      /* ─── Mobile Responsive ─── */
      @media (max-width: 480px) {
        #lcd-widget {
          width: calc(100vw - 20px) !important;
          height: calc(100vh - 80px) !important;
          max-height: none !important;
          border-radius: 12px;
          bottom: ${config.buttonSize + 8}px !important;
          right: 0 !important;
          left: 0 !important;
          margin: 0 10px;
        }
      }
    `;

    const style = document.createElement('style');
    style.id = 'lucid-chat-widget-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ─── SVG Icons ───
  const ICONS = {
    chat: '<svg viewBox="0 0 24 24" fill="white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z" fill="white"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="white"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="white"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>',
    ai: '<svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="3" fill="white" opacity="0.9"/><path d="M10 16a6 6 0 0112 0" stroke="white" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/><circle cx="16" cy="16" r="10" stroke="white" stroke-width="1.5" opacity="0.3"/></svg>',
    newChat: '<svg viewBox="0 0 24 24" fill="white" width="16" height="16"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="white"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
    spinner: '<svg viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="2"><path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83"/></svg>',
  };

  // ─── Build DOM ───
  function buildWidget() {
    const posClass = config.position === 'bottom-left' ? 'lcd-pos-bottom-left' : 'lcd-pos-bottom-right';

    container = document.createElement('div');
    container.id = 'lcd-container';
    container.className = posClass;
    container.style.cssText = `
      position: fixed;
      ${config.position === 'bottom-left' ? 'left' : 'right'}: ${config.buttonMargin}px;
      bottom: ${config.buttonMargin}px;
    `;

    // Float Button
    button = document.createElement('button');
    button.id = 'lcd-button';
    button.setAttribute('title', 'Lucid AI');
    button.innerHTML = `
      <span class="lcd-icon-chat">${ICONS.chat}</span>
      <span class="lcd-icon-close" style="display:none">${ICONS.close}</span>
      <span id="lcd-badge"></span>
    `;
    button.addEventListener('click', toggleWidget);

    badge = button.querySelector('#lcd-badge');

    // Widget Panel
    widget = document.createElement('div');
    widget.id = 'lcd-widget';
    widget.innerHTML = `
      <div id="lcd-header">
        <div id="lcd-header-left">
          <div id="lcd-header-icon">${ICONS.ai}</div>
          <div>
            <div id="lcd-header-title">${escapeHtml(config.title)}</div>
            <div id="lcd-header-subtitle">${escapeHtml(config.subtitle)}</div>
          </div>
        </div>
        <div id="lcd-header-actions">
          <button class="lcd-header-btn" id="lcd-btn-new" title="새 대화">${ICONS.newChat}</button>
          <button class="lcd-header-btn" id="lcd-btn-minimize" title="최소화">−</button>
        </div>
      </div>
      <div id="lcd-messages"></div>
      <div id="lcd-quick-actions"></div>
      <div id="lcd-input-area">
        <textarea id="lcd-input" rows="1" placeholder="${escapeHtml(config.placeholder)}"></textarea>
        <button id="lcd-send">${ICONS.send}</button>
      </div>
    `;

    container.appendChild(widget);
    container.appendChild(button);
    document.body.appendChild(container);

    // SPA 환경: body 자식 변경 시 위젯이 사라지면 다시 붙이기
    if (typeof MutationObserver !== 'undefined') {
      var reattachObserver = new MutationObserver(function () {
        if (!document.body.contains(container)) {
          document.body.appendChild(container);
        }
      });
      reattachObserver.observe(document.body, { childList: true });
    }

    // Cache elements
    messagesEl = widget.querySelector('#lcd-messages');
    inputEl = widget.querySelector('#lcd-input');
    sendBtn = widget.querySelector('#lcd-send');

    // Event Listeners
    widget.querySelector('#lcd-btn-minimize').addEventListener('click', toggleWidget);
    widget.querySelector('#lcd-btn-new').addEventListener('click', startNewChat);
    inputEl.addEventListener('input', onInputChange);
    inputEl.addEventListener('keydown', onInputKeydown);
    sendBtn.addEventListener('click', sendMessage);

    // Build quick actions
    buildQuickActions();

    // Show welcome
    showWelcome();
  }

  // ─── Quick Actions ───
  function buildQuickActions() {
    const container = widget.querySelector('#lcd-quick-actions');
    container.innerHTML = '';
    config.quickActions.forEach(function (text) {
      const btn = document.createElement('button');
      btn.className = 'lcd-quick-btn';
      btn.textContent = text;
      btn.addEventListener('click', function () {
        if (!state.isStreaming) {
          inputEl.value = text;
          onInputChange();
          sendMessage();
        }
      });
      container.appendChild(btn);
    });
  }

  // ─── Welcome Screen ───
  function showWelcome() {
    messagesEl.innerHTML = `
      <div class="lcd-welcome">
        <div class="lcd-welcome-icon">💡</div>
        <div class="lcd-welcome-title">안녕하세요!</div>
        <div class="lcd-welcome-desc">
          Lucid AI에게 업무 관련 궁금한 점을<br>무엇이든 물어보세요.
        </div>
      </div>
    `;
  }

  // ─── Toggle Widget ───
  function toggleWidget() {
    state.isOpen = !state.isOpen;

    if (state.isOpen) {
      widget.classList.add('lcd-visible');
      button.classList.add('lcd-open');
      button.querySelector('.lcd-icon-chat').style.display = 'none';
      button.querySelector('.lcd-icon-close').style.display = 'flex';
      inputEl.focus();
    } else {
      widget.classList.remove('lcd-visible');
      button.classList.remove('lcd-open');
      button.querySelector('.lcd-icon-chat').style.display = 'flex';
      button.querySelector('.lcd-icon-close').style.display = 'none';
    }
  }

  // ─── New Chat ───
  function startNewChat() {
    if (state.isStreaming) {
      stopStreaming();
    }
    state.messages = [];
    state.sessionId = generateSessionId();
    showWelcome();
    buildQuickActions();
    inputEl.value = '';
    onInputChange();
  }

  // ─── Input Handling ───
  function onInputChange() {
    // Auto-resize textarea
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + 'px';

    // Toggle send button state
    if (inputEl.value.trim()) {
      sendBtn.classList.add('lcd-active');
    } else {
      sendBtn.classList.remove('lcd-active');
    }
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // ─── Add Message to UI ───
  function addMessage(role, content, options) {
    options = options || {};

    // Remove welcome if first message
    const welcome = messagesEl.querySelector('.lcd-welcome');
    if (welcome) welcome.remove();

    const msgDiv = document.createElement('div');
    msgDiv.className = 'lcd-msg lcd-msg-' + role;
    if (options.id) msgDiv.id = options.id;

    const time = formatTime(new Date());

    if (role === 'ai') {
      msgDiv.innerHTML = `
        <div class="lcd-msg-avatar">${ICONS.ai}</div>
        <div>
          <div class="lcd-msg-bubble">${renderMarkdown(content)}</div>
          <span class="lcd-msg-time">${time}</span>
        </div>
      `;
    } else {
      msgDiv.innerHTML = `
        <div>
          <div class="lcd-msg-bubble">${escapeHtml(content)}</div>
          <span class="lcd-msg-time">${time}</span>
        </div>
      `;
    }

    messagesEl.appendChild(msgDiv);
    scrollToBottom();
    return msgDiv;
  }

  // ─── Typing Indicator ───
  function showTyping() {
    removeTyping();
    const div = document.createElement('div');
    div.className = 'lcd-typing';
    div.id = 'lcd-typing';
    div.innerHTML = `
      <div class="lcd-msg-avatar" style="background:linear-gradient(135deg,#1a73e8,#0d47a1);width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;">${ICONS.ai}</div>
      <div class="lcd-typing-dots">
        <div class="lcd-typing-dot"></div>
        <div class="lcd-typing-dot"></div>
        <div class="lcd-typing-dot"></div>
      </div>
    `;
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function removeTyping() {
    const el = document.getElementById('lcd-typing');
    if (el) el.remove();
  }

  // ─── Status Message (thinking, tool call) ───
  function showStatus(text) {
    removeStatus();
    const div = document.createElement('div');
    div.className = 'lcd-status-msg';
    div.id = 'lcd-status';
    div.innerHTML = `
      <span class="lcd-status-icon">${ICONS.spinner}</span>
      <span>${escapeHtml(text)}</span>
    `;
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function removeStatus() {
    const el = document.getElementById('lcd-status');
    if (el) el.remove();
  }

  // ─── Scroll ───
  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ─── Disable/Enable Quick Actions ───
  function setQuickActionsEnabled(enabled) {
    const btns = widget.querySelectorAll('.lcd-quick-btn');
    btns.forEach(function (btn) {
      btn.disabled = !enabled;
    });
  }

  // ─── Stop Streaming ───
  function stopStreaming() {
    if (state.abortController) {
      state.abortController.abort();
      state.abortController = null;
    }
    state.isStreaming = false;
    removeTyping();
    removeStatus();
    setQuickActionsEnabled(true);
    updateSendButton();
  }

  // ─── Update Send Button (send vs stop) ───
  function updateSendButton() {
    if (state.isStreaming) {
      sendBtn.innerHTML = ICONS.stop;
      sendBtn.classList.add('lcd-active');
      sendBtn.setAttribute('title', '응답 중지');
    } else {
      sendBtn.innerHTML = ICONS.send;
      if (inputEl.value.trim()) {
        sendBtn.classList.add('lcd-active');
      } else {
        sendBtn.classList.remove('lcd-active');
      }
      sendBtn.setAttribute('title', '전송');
    }
  }

  // ─── Send Message ───
  function sendMessage() {
    // If streaming, stop it
    if (state.isStreaming) {
      stopStreaming();
      return;
    }

    const text = inputEl.value.trim();
    if (!text) return;

    // Initialize session if needed
    if (!state.sessionId) {
      state.sessionId = generateSessionId();
    }

    // Add user message
    state.messages.push({ role: 'user', content: text });
    addMessage('user', text);

    // Clear input
    inputEl.value = '';
    inputEl.style.height = 'auto';
    onInputChange();

    // Show typing
    showTyping();
    state.isStreaming = true;
    setQuickActionsEnabled(false);
    updateSendButton();

    // Stream response
    streamChat(text);
  }

  // ─── SSE Streaming ───
  function streamChat(message) {
    state.abortController = new AbortController();
    const signal = state.abortController.signal;

    const url = config.apiUrl + config.streamEndpoint;
    const body = JSON.stringify({
      message: message,
      session_id: state.sessionId,
      user_id: config.userId,
      user_name: config.userName,
    });

    let fullContent = '';
    let aiMsgEl = null;

    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        // 사용자 인증 헤더 (필요 시 수정)
        'X-User-Id': config.userId,
      },
      body: body,
      signal: signal,
    }).then(function (response) {
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      function processStream() {
        return reader.read().then(function (result) {
          if (result.done) {
            onStreamEnd();
            return;
          }

          buffer += decoder.decode(result.value, { stream: true });

          // Process complete SSE lines
          var lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (line.startsWith('data: ')) {
              var dataStr = line.substring(6);

              // Check for [DONE] marker
              if (dataStr === '[DONE]') {
                onStreamEnd();
                return;
              }

              try {
                var data = JSON.parse(dataStr);
                handleSSEEvent(data);
              } catch (e) {
                // Non-JSON data, treat as plain text token
                handleToken(dataStr);
              }
            }
          }

          return processStream();
        });
      }

      function handleSSEEvent(data) {
        // 백엔드 완료 이벤트: {"complete": true}
        if (data.complete) {
          onStreamEnd();
          return;
        }
        var eventType = data[config.sseStatusField] || '';
        var content = data[config.sseContentField] || '';

        switch (eventType) {
          case config.sseTokenType:
            handleToken(content);
            break;

          case config.sseDoneType:
            onStreamEnd();
            break;

          case config.sseErrorType:
            onStreamError(content || data.message || '오류가 발생했습니다.');
            break;

          case config.sseThinkingType:
            showStatus('생각하고 있습니다...');
            break;

          case config.sseToolType:
            var toolMsg = data.message || '';
            var toolName = data.tool || data.tool_name || data.name || '도구';
            showStatus(toolMsg || toolName + ' 실행 중...');
            break;

          case config.sseSourceType:
            // 출처 정보는 메시지에 추가
            if (content && aiMsgEl) {
              fullContent += '\n\n📎 **출처:** ' + content;
              updateAIMessage(fullContent);
            }
            break;

          default:
            // 알 수 없는 타입이지만 content가 있으면 토큰으로 처리
            if (content) {
              handleToken(content);
            }
            break;
        }
      }

      function handleToken(token) {
        removeTyping();
        removeStatus();

        if (!aiMsgEl) {
          // Create AI message bubble
          aiMsgEl = addMessage('ai', '');
        }

        fullContent += token;
        updateAIMessage(fullContent);
      }

      function updateAIMessage(content) {
        if (aiMsgEl) {
          var bubble = aiMsgEl.querySelector('.lcd-msg-bubble');
          if (bubble) {
            bubble.innerHTML = renderMarkdown(content);
            scrollToBottom();
          }
        }
      }

      function onStreamEnd() {
        removeTyping();
        removeStatus();
        state.isStreaming = false;
        state.abortController = null;
        setQuickActionsEnabled(true);
        updateSendButton();

        if (fullContent) {
          state.messages.push({ role: 'ai', content: fullContent });
        }

        // Hide quick actions after first exchange
        if (state.messages.length > 2) {
          var qa = widget.querySelector('#lcd-quick-actions');
          if (qa) qa.style.display = 'none';
        }
      }

      function onStreamError(errorMsg) {
        removeTyping();
        removeStatus();
        state.isStreaming = false;
        state.abortController = null;
        setQuickActionsEnabled(true);
        updateSendButton();

        addMessage('ai', '⚠️ ' + errorMsg);
      }

      return processStream();

    }).catch(function (err) {
      if (err.name === 'AbortError') {
        // User cancelled
        removeTyping();
        removeStatus();
        if (fullContent) {
          state.messages.push({ role: 'ai', content: fullContent + '\n\n_(응답 중단됨)_' });
          if (aiMsgEl) {
            var bubble = aiMsgEl.querySelector('.lcd-msg-bubble');
            if (bubble) {
              bubble.innerHTML = renderMarkdown(fullContent + '\n\n_(응답 중단됨)_');
            }
          }
        }
      } else {
        removeTyping();
        removeStatus();
        addMessage('ai', '⚠️ 서버 연결에 실패했습니다. 잠시 후 다시 시도해주세요.\n\n`' + err.message + '`');
      }
      state.isStreaming = false;
      state.abortController = null;
      setQuickActionsEnabled(true);
      updateSendButton();
    });
  }

  // ─── Public API ───
  global.LucidChat = {
    /**
     * 위젯 초기화
     * @param {Object} userConfig - 설정 객체
     */
    init: function (userConfig) {
      config = Object.assign({}, DEFAULT_CONFIG, userConfig || {});
      state.sessionId = generateSessionId();

      // Wait for DOM ready
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

    /** 위젯 열기 */
    open: function () {
      if (!state.isOpen) toggleWidget();
    },

    /** 위젯 닫기 */
    close: function () {
      if (state.isOpen) toggleWidget();
    },

    /** 위젯 토글 */
    toggle: function () {
      toggleWidget();
    },

    /** 새 대화 시작 */
    newChat: function () {
      startNewChat();
    },

    /** 프로그래밍 방식으로 메시지 전송 */
    sendMessage: function (text) {
      if (text) {
        inputEl.value = text;
        sendMessage();
      }
    },

    /** 설정 업데이트 */
    updateConfig: function (newConfig) {
      Object.assign(config, newConfig);
    },

    /** 위젯 제거 */
    destroy: function () {
      stopStreaming();
      if (container && container.parentNode) {
        container.parentNode.removeChild(container);
      }
      var style = document.getElementById('lucid-chat-widget-styles');
      if (style) style.remove();
    },
  };

})(typeof window !== 'undefined' ? window : this);
