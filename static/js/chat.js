// Chat bubble — talks to /chat for natural-language commands.

(function () {
  const toggle = document.getElementById('chat-toggle');
  const panel = document.getElementById('chat-panel');
  const closeBtn = document.getElementById('chat-close');
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const messages = document.getElementById('chat-messages');
  if (!toggle || !panel) return;

  function show(visible) {
    panel.hidden = !visible;
    if (visible) setTimeout(() => input.focus(), 50);
  }
  toggle.addEventListener('click', () => show(panel.hidden));
  closeBtn.addEventListener('click', () => show(false));

  function appendMessage(text, role) {
    const node = document.createElement('div');
    node.className = 'chat-msg chat-msg-' + role;
    node.textContent = text;
    messages.appendChild(node);
    messages.scrollTop = messages.scrollHeight;
    return node;
  }

  function appendBotWithDeckLink(text, deck) {
    const node = document.createElement('div');
    node.className = 'chat-msg chat-msg-bot';
    const p = document.createElement('div');
    p.textContent = text.replace(deck.view_url, '').replace(/\s+$/, '');
    node.appendChild(p);
    const link = document.createElement('a');
    link.href = deck.view_url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = '↗ Open deck';
    node.appendChild(link);
    messages.appendChild(node);
    messages.scrollTop = messages.scrollHeight;
    return node;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    appendMessage(text, 'user');
    input.value = '';
    const pending = appendMessage('Thinking…', 'system');
    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      pending.remove();
      if (data.ok) {
        if (data.deck && data.deck.view_url) {
          appendBotWithDeckLink(data.reply, data.deck);
        } else {
          appendMessage(data.reply, 'bot');
        }
        if (data.action && data.action !== 'generate_deck') {
          appendMessage('(action: ' + data.action + ') — refresh the page to see updates.', 'system');
        }
      } else {
        appendMessage('Error: ' + (data.error || 'unknown'), 'system');
      }
    } catch (err) {
      pending.remove();
      appendMessage('Network error: ' + err.message, 'system');
    }
  });
})();
