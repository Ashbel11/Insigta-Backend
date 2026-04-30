// ── PKCE Helpers ─────────────────────────────────────────────────────────────
function generateCodeVerifier() {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return btoa(String.fromCharCode(...array))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

async function generateCodeChallenge(verifier) {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function generateState() {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array).map(b => b.toString(16).padStart(2, "0")).join("");
}

// ── CSRF ──────────────────────────────────────────────────────────────────────
function getCsrfToken() {
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

// ── API Client ────────────────────────────────────────────────────────────────
async function apiRequest(method, path, body = null, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  });

  const headers = {
    "X-API-Version": "3",
    "Content-Type": "application/json",
  };

  const csrf = getCsrfToken();
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const options = { method, headers, credentials: "include" };
  if (body) options.body = JSON.stringify(body);

  let res = await fetch(url.toString(), options);

  // Auto-refresh on 401
  if (res.status === 401) {
    const refreshRes = await fetch("/web/auth/refresh", {
      method: "POST",
      headers: { "X-CSRF-Token": csrf || "" },
      credentials: "include",
    });
    if (!refreshRes.ok) {
      window.location.href = "/web/login.html";
      return null;
    }
    res = await fetch(url.toString(), options);
  }

  return res;
}

// ── Auth Guard ────────────────────────────────────────────────────────────────
async function requireAuth() {
  const res = await fetch("/web/auth/me", { credentials: "include" });
  if (!res.ok) {
    window.location.href = "/web/login.html";
    return null;
  }
  const data = await res.json();
  return data.user;
}

// ── Logout ────────────────────────────────────────────────────────────────────
async function logout() {
  await fetch("/web/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": getCsrfToken() || "" },
    credentials: "include",
  });
  window.location.href = "/web/login.html";
}

// ── Shared Nav ────────────────────────────────────────────────────────────────
function renderNav(user) {
  return `
    <nav class="navbar">
      <div class="nav-brand">⚡ Insighta Labs</div>
      <div class="nav-links">
        <a href="/web/dashboard.html">Dashboard</a>
        <a href="/web/profiles.html">Profiles</a>
        <a href="/web/export.html">Export</a>
        ${user.role === "admin" ? '<a href="/web/create.html">Create</a>' : ""}
      </div>
      <div class="nav-user">
        ${user.avatar_url ? `<img src="${user.avatar_url}" class="avatar" />` : ""}
        <span>${user.username} <span class="badge badge-${user.role}">${user.role}</span></span>
        <button onclick="logout()" class="btn btn-sm btn-outline">Logout</button>
      </div>
    </nav>
  `;
}

// ── Shared Styles ─────────────────────────────────────────────────────────────
const SHARED_STYLES = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  .navbar { display: flex; align-items: center; justify-content: space-between;
            padding: 0 2rem; height: 60px; background: #1a1d27;
            border-bottom: 1px solid #2d3148; position: sticky; top: 0; z-index: 100; }
  .nav-brand { font-weight: 700; font-size: 1.1rem; color: #7c6af7; }
  .nav-links { display: flex; gap: 1.5rem; }
  .nav-links a { color: #94a3b8; text-decoration: none; font-size: 0.9rem; }
  .nav-links a:hover { color: #e2e8f0; }
  .nav-user { display: flex; align-items: center; gap: 0.75rem; font-size: 0.9rem; }
  .avatar { width: 28px; height: 28px; border-radius: 50%; }
  .badge { padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
  .badge-admin { background: #7c3aed22; color: #a78bfa; border: 1px solid #7c3aed44; }
  .badge-analyst { background: #0ea5e922; color: #38bdf8; border: 1px solid #0ea5e944; }
  .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
  .card { background: #1a1d27; border: 1px solid #2d3148; border-radius: 12px; padding: 1.5rem; }
  .btn { padding: 0.5rem 1.25rem; border-radius: 8px; border: none; cursor: pointer;
         font-size: 0.9rem; font-weight: 500; transition: opacity 0.2s; }
  .btn:hover { opacity: 0.85; }
  .btn-primary { background: #7c6af7; color: white; }
  .btn-outline { background: transparent; color: #94a3b8; border: 1px solid #2d3148; }
  .btn-sm { padding: 0.3rem 0.75rem; font-size: 0.8rem; }
  .btn-danger { background: #ef4444; color: white; }
  input, select { background: #0f1117; border: 1px solid #2d3148; color: #e2e8f0;
                  padding: 0.5rem 0.75rem; border-radius: 8px; font-size: 0.9rem;
                  width: 100%; outline: none; }
  input:focus, select:focus { border-color: #7c6af7; }
  label { display: block; font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.35rem; }
  .form-group { margin-bottom: 1rem; }
  .error { color: #f87171; font-size: 0.85rem; margin-top: 0.5rem; }
  .success { color: #4ade80; font-size: 0.85rem; margin-top: 0.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  th { text-align: left; padding: 0.75rem 1rem; color: #7c6af7;
       border-bottom: 1px solid #2d3148; font-weight: 600; }
  td { padding: 0.75rem 1rem; border-bottom: 1px solid #1e2235; color: #cbd5e1; }
  tr:hover td { background: #1e2235; }
  .pagination { display: flex; gap: 0.5rem; align-items: center; margin-top: 1.5rem; justify-content: center; }
  .page-info { color: #94a3b8; font-size: 0.85rem; }
  .spinner { border: 3px solid #2d3148; border-top-color: #7c6af7; border-radius: 50%;
             width: 32px; height: 32px; animation: spin 0.8s linear infinite;
             margin: 3rem auto; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty { text-align: center; color: #94a3b8; padding: 3rem; }
`;