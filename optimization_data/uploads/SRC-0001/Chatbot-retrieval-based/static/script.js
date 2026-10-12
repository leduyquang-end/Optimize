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

// ===== ADD MESSAGE =====
function addMessage(text, role) {
  removeWelcome();

  const row = document.createElement('div');
  row.className = `msg-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'bot' ? '🤖' : '🧑';

  const content = document.createElement('div');
  content.className = 'msg-content';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = role === 'bot'
    ? marked.parse(text)
    : escapeHtml(text).replace(/\n/g, '<br>');

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

// ===== SEND MESSAGE =====
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || isWaiting) return;

  isWaiting = true;
  sendBtn.disabled = true;
  inputEl.value = '';
  inputEl.style.height = 'auto';

  addMessage(text, 'user');
  showTyping();

  try {
    const res  = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    const data = await res.json();
    hideTyping();
    addMessage(data.reply || 'Xin lỗi, đã có lỗi xảy ra.', 'bot');
  } catch {
    hideTyping();
    addMessage('Không thể kết nối đến server. Vui lòng thử lại.', 'bot');
  } finally {
    isWaiting = false;
    sendBtn.disabled = false;
    inputEl.focus();
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