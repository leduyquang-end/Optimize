// ===== MARKED CONFIG =====
marked.setOptions({
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value;
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true
});

// ===== STATE =====
const chatBox = document.getElementById('chat-box');
const inputEl = document.getElementById('user-input');
const sendBtn = document.getElementById('sendBtn');
let isWaiting = false;

// ===== AUTO-RESIZE TEXTAREA =====
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});

inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!isWaiting) sendMessage();
  }
});

// ===== HELPERS =====
function getTime() {
  return new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function scrollBottom() {
  chatBox.scrollTop = chatBox.scrollHeight;
}

function removeWelcome() {
  const w = document.getElementById('welcome-msg');
  if (w) w.remove();
}

function escapeHtml(t) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ===== ADD USER MESSAGE =====
function addUserMessage(text) {
  removeWelcome();

  const row = document.createElement('div');
  row.className = 'msg-row user';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = '🧑';

  const content = document.createElement('div');
  content.className = 'msg-content';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');

  const time = document.createElement('div');
  time.className = 'msg-time';
  time.textContent = getTime();

  content.appendChild(bubble);
  content.appendChild(time);
  row.appendChild(avatar);
  row.appendChild(content);
  chatBox.appendChild(row);
  scrollBottom();
}

// ===== CREATE STREAMING BOT BUBBLE =====
// Trả về { bubble, timeEl, row } để cập nhật dần
function createBotBubble() {
  removeWelcome();

  const row = document.createElement('div');
  row.className = 'msg-row bot';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = '🤖';

  const content = document.createElement('div');
  content.className = 'msg-content';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble streaming';   // class streaming để style cursor nhấp nháy

  const time = document.createElement('div');
  time.className = 'msg-time';
  time.textContent = getTime();

  content.appendChild(bubble);
  content.appendChild(time);
  row.appendChild(avatar);
  row.appendChild(content);
  chatBox.appendChild(row);
  scrollBottom();

  return { bubble, timeEl: time };
}

// ===== TYPING INDICATOR =====
function showTyping() {
  removeWelcome();
  const row = document.createElement('div');
  row.className = 'typing-row';
  row.id = 'typing-indicator';

  const avatar = document.createElement('div');
  avatar.className = 'typing-avatar';
  avatar.textContent = '🤖';

  const bubble = document.createElement('div');
  bubble.className = 'typing-bubble';
  bubble.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatBox.appendChild(row);
  scrollBottom();
}

function hideTyping() {
  const t = document.getElementById('typing-indicator');
  if (t) t.remove();
}

// ===== SEND MESSAGE (STREAMING) =====
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || isWaiting) return;

  isWaiting = true;
  sendBtn.disabled = true;
  inputEl.value = '';
  inputEl.style.height = 'auto';

  addUserMessage(text);
  showTyping();

  try {
    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';
    let   rawText = '';       // toàn bộ text thô tích lũy
    let   botBubble = null;   // tạo bubble khi nhận token đầu tiên

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE: mỗi sự kiện kết thúc bằng "\n\n"
      const events = buffer.split('\n\n');
      buffer = events.pop();   // phần chưa hoàn chỉnh giữ lại

      for (const event of events) {
        if (!event.startsWith('data: ')) continue;
        const dataStr = event.slice(6).trim();

        if (dataStr === '[DONE]') {
          // Hoàn thành — render Markdown lần cuối
          if (botBubble) {
            botBubble.innerHTML = marked.parse(rawText);
            botBubble.classList.remove('streaming');
            // Highlight code blocks
            botBubble.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
          }
          break;
        }

        let parsed;
        try { parsed = JSON.parse(dataStr); } catch { continue; }

        const token = parsed.token;
        if (token == null) continue;

        rawText += token;

        // Tạo bubble lần đầu (sau khi nhận token đầu tiên)
        if (!botBubble) {
          hideTyping();
          const { bubble } = createBotBubble();
          botBubble = bubble;
        }

        // Render Markdown liên tục — không bị "nhảy" nhờ marked parse incremental
        botBubble.innerHTML = marked.parse(rawText) + '<span class="cursor">▍</span>';
        scrollBottom();
      }
    }

    // Đảm bảo cursor bị xóa nếu [DONE] tới trong lần read cuối
    if (botBubble) {
      botBubble.innerHTML = marked.parse(rawText);
      botBubble.classList.remove('streaming');
      botBubble.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
    }

  } catch (err) {
    hideTyping();
    // Tạo bubble lỗi
    const { bubble } = createBotBubble();
    bubble.textContent = 'Không thể kết nối đến server. Vui lòng thử lại.';
    bubble.classList.remove('streaming');
  } finally {
    isWaiting = false;
    sendBtn.disabled = false;
    inputEl.focus();
    scrollBottom();
  }
}

// ===== QUICK QUESTION =====
function sendQuick(q) {
  if (isWaiting) return;
  inputEl.value = q;
  inputEl.dispatchEvent(new Event('input'));
  sendMessage();
}

// ===== CLEAR CHAT =====
function clearChat() {
  chatBox.innerHTML = `
    <div class="welcome" id="welcome-msg">
      <div class="welcome-icon">👋</div>
      <h2>Xin chào! Mình là Trợ lý TLU</h2>
      <p>Mình có thể giúp bạn tìm hiểu về học bổng, học phí,<br/>điểm rèn luyện và các quy định của trường.<br/>Hãy đặt câu hỏi nhé!</p>
    </div>`;
  inputEl.focus();
}