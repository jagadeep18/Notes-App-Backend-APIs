/**
 * Notes App — Frontend Logic
 * Connects to the FastAPI backend at the same origin.
 */
const API = '';  // same origin
let token = localStorage.getItem('access_token');
let refreshToken = localStorage.getItem('refresh_token');
let currentUser = null;
let currentPage = 1;
let searchTimeout = null;

// ── API Helper ───────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...opts, headers });

  if (res.status === 401 && refreshToken && path !== '/refresh') {
    const refreshed = await tryRefresh();
    if (refreshed) return api(path, opts);
    logout();
    return null;
  }

  return res;
}

async function tryRefresh() {
  try {
    const res = await fetch(`${API}/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (res.ok) {
      const data = await res.json();
      token = data.access_token;
      refreshToken = data.refresh_token;
      localStorage.setItem('access_token', token);
      localStorage.setItem('refresh_token', refreshToken);
      return true;
    }
  } catch (e) { /* ignore */ }
  return false;
}

// ── Auth ──────────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('auth-error').style.display = 'none';
  if (tab === 'login') {
    document.querySelectorAll('.auth-tab')[0].classList.add('active');
    document.getElementById('login-form').style.display = 'block';
    document.getElementById('signup-form').style.display = 'none';
  } else {
    document.querySelectorAll('.auth-tab')[1].classList.add('active');
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('signup-form').style.display = 'block';
  }
}

function showAuthError(msg) {
  const el = document.getElementById('auth-error');
  el.textContent = msg;
  el.style.display = 'block';
}

async function handleSignup(e) {
  e.preventDefault();
  const body = {
    username: document.getElementById('signup-username').value,
    email: document.getElementById('signup-email').value,
    password: document.getElementById('signup-password').value,
    full_name: document.getElementById('signup-fullname').value || undefined,
  };
  const res = await fetch(`${API}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    toast('Account created! Please login.', 'success');
    switchTab('login');
    document.getElementById('login-email').value = body.email;
  } else {
    const err = await res.json();
    showAuthError(err.detail || err.error?.message || 'Registration failed');
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const body = {
    email: document.getElementById('login-email').value,
    password: document.getElementById('login-password').value,
  };
  const res = await fetch(`${API}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    const data = await res.json();
    token = data.access_token;
    refreshToken = data.refresh_token;
    localStorage.setItem('access_token', token);
    localStorage.setItem('refresh_token', refreshToken);
    await loadUser();
    showMainScreen();
  } else {
    showAuthError('Invalid email or password');
  }
}

function handleLogout() {
  api('/logout', { method: 'POST' }).catch(() => {});
  logout();
}

function logout() {
  token = null;
  refreshToken = null;
  currentUser = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  document.getElementById('auth-screen').style.display = 'block';
  document.getElementById('main-screen').style.display = 'none';
}

async function loadUser() {
  const res = await api('/me');
  if (res && res.ok) {
    currentUser = await res.json();
    document.getElementById('user-badge').textContent = `👤 ${currentUser.username}`;
  }
}

function showMainScreen() {
  document.getElementById('auth-screen').style.display = 'none';
  document.getElementById('main-screen').style.display = 'block';
  loadNotes();
}

// ── Notes ─────────────────────────────────────────────────────────────────
async function loadNotes(page = 1, search = '') {
  currentPage = page;
  let url = `/notes?page=${page}&page_size=12`;
  if (search) url = `/search?q=${encodeURIComponent(search)}&page=${page}&page_size=12`;

  const res = await api(url);
  if (!res || !res.ok) return;
  const data = await res.json();
  
  // Handle both list (new spec) and paginated (old spec/stretch) formats
  const notes = Array.isArray(data) ? data : (data.items || []);

  renderNotes(notes);
  if (!Array.isArray(data)) {
    renderPagination(data.total, data.page, data.page_size);
  } else {
    document.getElementById('pagination').innerHTML = '';
  }
}

function renderNotes(notes) {
  const container = document.getElementById('notes-container');
  if (notes.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="icon">📝</div>
        <h3>No notes yet</h3>
        <p>Create your first note to get started.</p>
      </div>`;
    return;
  }

  container.innerHTML = notes.map(n => `
    <div class="note-card ${n.is_pinned ? 'pinned' : ''}" onclick="openNote('${n.id}')">
      <h3>${escapeHtml(n.title)}</h3>
      <p>${escapeHtml(n.content?.substring(0, 150) || '')}</p>
      <div class="note-meta">
        <span>${timeAgo(n.updated_at)}</span>
        ${n.is_private ? '<span class="note-badge badge-private">🔒 Private</span>' : ''}
      </div>
    </div>
  `).join('');
}

function renderPagination(total, page, pageSize) {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) { document.getElementById('pagination').innerHTML = ''; return; }

  const search = document.getElementById('search-input').value;
  let html = '';
  if (page > 1) html += `<button class="btn btn-secondary btn-sm" onclick="loadNotes(${page-1},'${search}')">← Prev</button>`;
  html += `<span class="user-badge">Page ${page} of ${totalPages}</span>`;
  if (page < totalPages) html += `<button class="btn btn-secondary btn-sm" onclick="loadNotes(${page+1},'${search}')">Next →</button>`;
  document.getElementById('pagination').innerHTML = html;
}

function debounceSearch() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    const q = document.getElementById('search-input').value.trim();
    loadNotes(1, q);
  }, 400);
}

// ── Note Modal ────────────────────────────────────────────────────────────
function openNewNote() {
  document.getElementById('note-id').value = '';
  document.getElementById('note-title').value = '';
  document.getElementById('note-content').value = '';
  document.getElementById('note-private').checked = false;
  document.getElementById('modal-title').textContent = 'New Note';
  document.getElementById('delete-btn').style.display = 'none';
  document.getElementById('pin-btn').style.display = 'none';
  document.getElementById('share-section').style.display = 'none';
  document.getElementById('note-modal').classList.add('active');
}

async function openNote(id) {
  const res = await api(`/notes/${id}`);
  if (!res || !res.ok) return;
  const note = await res.json();

  document.getElementById('note-id').value = note.id;
  document.getElementById('note-title').value = note.title;
  document.getElementById('note-content').value = note.content;
  document.getElementById('note-private').checked = note.is_private;
  document.getElementById('modal-title').textContent = 'Edit Note';
  document.getElementById('delete-btn').style.display = 'inline-flex';

  const pinBtn = document.getElementById('pin-btn');
  pinBtn.style.display = 'inline-flex';
  pinBtn.textContent = note.is_pinned ? '📌 Unpin' : '📌 Pin';
  pinBtn.dataset.pinned = note.is_pinned;

  document.getElementById('share-section').style.display = 'block';
  document.getElementById('note-modal').classList.add('active');
}

function closeModal() { document.getElementById('note-modal').classList.remove('active'); }
function closeModalOutside(e) { if (e.target === e.currentTarget) closeModal(); }

async function handleSaveNote(e) {
  e.preventDefault();
  const id = document.getElementById('note-id').value;
  const body = {
    title: document.getElementById('note-title').value,
    content: document.getElementById('note-content').value,
    is_private: document.getElementById('note-private').checked,
  };

  let res;
  if (id) {
    res = await api(`/notes/${id}`, { method: 'PUT', body: JSON.stringify(body) });
  } else {
    res = await api('/notes', { method: 'POST', body: JSON.stringify(body) });
  }

  if (res && res.ok) {
    toast(id ? 'Note updated' : 'Note created', 'success');
    closeModal();
    loadNotes(currentPage, document.getElementById('search-input').value.trim());
  } else {
    const err = await res?.json();
    toast(err?.detail || err?.error?.message || 'Save failed', 'error');
  }
}

async function handleDeleteNote() {
  const id = document.getElementById('note-id').value;
  if (!id || !confirm('Delete this note?')) return;

  const res = await api(`/notes/${id}`, { method: 'DELETE' });
  if (res && (res.status === 204 || res.ok)) {
    toast('Note deleted', 'success');
    closeModal();
    loadNotes(currentPage, document.getElementById('search-input').value.trim());
  } else {
    toast('Delete failed', 'error');
  }
}

async function handlePinToggle() {
  const id = document.getElementById('note-id').value;
  const isPinned = document.getElementById('pin-btn').dataset.pinned === 'true';
  const endpoint = isPinned ? 'unpin' : 'pin';

  const res = await api(`/notes/${id}/${endpoint}`, { method: 'POST' });
  if (res && res.ok) {
    toast(isPinned ? 'Note unpinned' : 'Note pinned', 'success');
    closeModal();
    loadNotes(currentPage, document.getElementById('search-input').value.trim());
  } else {
    const err = await res?.json();
    toast(err?.detail || err?.error?.message || 'Pin failed', 'error');
  }
}

async function handleShareNote() {
  const noteId = document.getElementById('note-id').value;
  const userId = document.getElementById('share-user-id').value.trim();
  const permission = document.getElementById('share-permission').value;

  if (!userId) { toast('Enter a user ID', 'error'); return; }

  const res = await api(`/notes/${noteId}/share`, {
    method: 'POST',
    body: JSON.stringify({ share_with_email: userId }), // Specs say share_with_email
  });

  if (res && res.ok) {
    toast('Note shared!', 'success');
    document.getElementById('share-user-id').value = '';
  } else {
    const err = await res?.json();
    toast(err?.detail || err?.error?.message || 'Share failed', 'error');
  }
}

// ── About ─────────────────────────────────────────────────────────────────
async function showAbout() {
  const res = await fetch(`${API}/about`);
  const data = await res.json();

  document.getElementById('about-content').innerHTML = `
    <div class="about-card">
      <h3>${data.name} <span style="font-size:.8rem;color:var(--text-dim)">${data.email}</span></h3>
      <p style="color:var(--text-dim);margin-bottom:16px">Developed for Assignment</p>
      <div class="feature-grid">
        ${Object.entries(data['my features']).map(([name, desc]) => `
          <div class="feature-item">
            <strong>${name}</strong>
            <p>${desc}</p>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="about-card">
      <h3>API Documentation</h3>
      <p style="color:var(--text-dim);margin-bottom:12px">Explore the full API:</p>
      <a href="/docs" target="_blank" class="btn btn-primary btn-sm" style="margin-right:8px">Swagger UI</a>
      <a href="/redoc" target="_blank" class="btn btn-secondary btn-sm">OpenAPI JSON</a>
    </div>
  `;
  document.getElementById('about-modal').classList.add('active');
}

function closeAbout() { document.getElementById('about-modal').classList.remove('active'); }
function closeAboutOutside(e) { if (e.target === e.currentTarget) closeAbout(); }

// ── Utilities ─────────────────────────────────────────────────────────────
function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ── Init ──────────────────────────────────────────────────────────────────
(async function init() {
  if (token) {
    await loadUser();
    if (currentUser) {
      showMainScreen();
    } else {
      logout();
    }
  }
})();
