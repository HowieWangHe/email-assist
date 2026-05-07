/* ===== Theme ===== */
function initTheme() {
  const saved = (() => { try { return localStorage.getItem('theme'); } catch (e) { return null; } })();
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'light');
  document.documentElement.dataset.theme = theme;
  updateThemeToggle(theme);
  const toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.addEventListener('click', toggleTheme);
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme;
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('theme', next); } catch (e) {}
  updateThemeToggle(next);
}

function updateThemeToggle(theme) {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.innerHTML = theme === 'dark'
    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg><span>浅色</span>`
    : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg><span>深色</span>`;
}

/* ===== Toast ===== */
function toast(message, type = 'info', duration = 3000) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const icon = type === 'success'
    ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
    : type === 'error'
    ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`
    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
  el.innerHTML = `${icon}<span>${message}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 300);
  }, duration);
}

/* ===== Modal Confirm ===== */
function confirmAction({ title = '确认操作', message = '', confirmText = '确认', requiredInput = null, onConfirmDanger = false } = {}) {
  return new Promise((resolve) => {
    const modal = document.getElementById('confirm-modal');
    const titleEl = document.getElementById('confirm-title');
    const msgEl = document.getElementById('confirm-message');
    const inputWrap = document.getElementById('confirm-input-wrap');
    const inputEl = document.getElementById('confirm-input');
    const okBtn = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    okBtn.textContent = confirmText;
    okBtn.className = onConfirmDanger ? 'danger' : '';
    inputWrap.style.display = requiredInput ? 'block' : 'none';
    inputEl.value = '';

    function cleanup() {
      modal.style.display = 'none';
      okBtn.onclick = null;
      cancelBtn.onclick = null;
      inputEl.onkeydown = null;
    }

    okBtn.onclick = () => {
      if (requiredInput) {
        if (inputEl.value.trim() !== requiredInput) {
          toast(`请输入 "${requiredInput}" 以确认`, 'error');
          inputEl.focus();
          return;
        }
      }
      cleanup();
      resolve(true);
    };

    cancelBtn.onclick = () => { cleanup(); resolve(false); };
    inputEl.onkeydown = (e) => { if (e.key === 'Enter') okBtn.click(); };

    modal.style.display = 'flex';
    if (requiredInput) setTimeout(() => inputEl.focus(), 50);
  });
}

/* ===== Button Loading ===== */
function setLoading(btn, loading = true, loadingText = null) {
  if (!btn) return;
  if (loading) {
    if (!btn.dataset.originalHtml) btn.dataset.originalHtml = btn.innerHTML;
    const text = loadingText || btn.textContent.trim();
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner ${btn.classList.contains('secondary') ? 'spinner-secondary' : ''}"></span><span>${text}</span>`;
  } else {
    btn.disabled = false;
    if (btn.dataset.originalHtml) {
      btn.innerHTML = btn.dataset.originalHtml;
      delete btn.dataset.originalHtml;
    }
  }
}

/* ===== Preview modal ===== */
function openPreview({ title = '预览', text = '', message = '', url = '', contentType = '', rows = [] } = {}) {
  const modal = document.getElementById('preview-modal');
  const titleEl = document.getElementById('preview-title');
  const bodyEl = document.getElementById('preview-body');
  const closeBtn = document.getElementById('preview-close');
  titleEl.textContent = title;
  bodyEl.innerHTML = '';

  if (rows.length) {
    const table = document.createElement('table');
    table.className = 'preview-table';
    rows.forEach((row, index) => {
      const tr = document.createElement('tr');
      row.forEach((cell) => {
        const el = document.createElement(index === 0 ? 'th' : 'td');
        el.textContent = cell;
        tr.appendChild(el);
      });
      table.appendChild(tr);
    });
    bodyEl.appendChild(table);
  } else if (text) {
    const pre = document.createElement('pre');
    pre.textContent = text;
    bodyEl.appendChild(pre);
  } else if (url && contentType.startsWith('image/')) {
    const img = document.createElement('img');
    img.src = url;
    img.alt = title;
    bodyEl.appendChild(img);
  } else if (url && contentType === 'application/pdf') {
    const frame = document.createElement('iframe');
    frame.src = url;
    frame.title = title;
    bodyEl.appendChild(frame);
  } else {
    const p = document.createElement('p');
    p.textContent = message || '该文件暂不支持预览。';
    bodyEl.appendChild(p);
  }

  function cleanup() {
    modal.style.display = 'none';
    closeBtn.onclick = null;
  }
  closeBtn.onclick = cleanup;
  modal.style.display = 'flex';
}

/* ===== Sidebar active state ===== */
function highlightNav() {
  const path = window.location.pathname;
  document.querySelectorAll('.nav-link').forEach(link => {
    const navPath = link.dataset.nav;
    if (navPath === path || (navPath !== '/' && path.startsWith(navPath))) {
      link.classList.add('is-active');
    } else {
      link.classList.remove('is-active');
    }
  });
}

/* ===== Tabs ===== */
function initTabs(container) {
  const tabs = container.querySelectorAll('.tab');
  const panels = container.querySelectorAll('.tab-panel');
  const tabKey = `tab:${location.pathname}`;

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      tabs.forEach(t => t.classList.remove('is-active'));
      panels.forEach(p => p.classList.remove('is-active'));
      tab.classList.add('is-active');
      const panel = container.querySelector(`.tab-panel[data-tab-panel="${target}"]`);
      if (panel) panel.classList.add('is-active');
      try { localStorage.setItem(tabKey, target); } catch (e) {}
    });
  });

  const saved = (() => { try { return localStorage.getItem(tabKey); } catch (e) { return null; } })();

  if (saved) {
    const savedTab = container.querySelector(`.tab[data-tab="${saved}"]`);
    if (savedTab) {
      savedTab.click();
      return;
    }
  }

  if (tabs.length && !container.querySelector('.tab.is-active')) {
    tabs[0].click();
  }
}

/* ===== Recipient search ===== */
function initRecipientSearch() {
  const searchInput = document.getElementById('recipient-search');
  if (!searchInput) return;
  const rows = document.querySelectorAll('#recipients-table tbody tr[data-recipient-row]');

  searchInput.addEventListener('input', () => {
    const query = searchInput.value.trim().toLowerCase();
    rows.forEach(row => {
      const text = (row.dataset.searchText || '').toLowerCase();
      row.style.display = text.includes(query) ? '' : 'none';
    });
  });
}

/* ===== Fetch helpers ===== */
async function postJSON(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = response.headers.get('content-type')?.includes('application/json')
    ? await response.json()
    : {};
  return { response, data };
}

/* ===== Init ===== */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  highlightNav();
  document.querySelectorAll('.tabs-container').forEach(initTabs);
  initRecipientSearch();
});
