// Same-origin by default: Django serves this folder, so the API is on the same address.
// Hosting the frontend separately? Set the backend address, e.g. 'http://127.0.0.1:8000'
// (and enable CORS on the backend).
const API_BASE = '';

// Escape text before it goes into innerHTML (team and player names are typed by users).
const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

// ---- sign-in support ----
// Every write goes out with the CSRF token and the session cookie; reads need neither.
const csrf = () => (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
const _fetch = window.fetch.bind(window);
window.fetch = (url, opts = {}) => {
  const m = (opts.method || 'GET').toUpperCase(), o = {credentials: 'include', ...opts};
  if (!['GET', 'HEAD', 'OPTIONS'].includes(m)) o.headers = {...(opts.headers || {}), 'X-CSRFToken': csrf()};
  return _fetch(url, o);
};
// Who is signed in? Resolves to {authenticated, username, can_register}.
const authReady = fetch(API_BASE + '/api/auth/me/').then(r => r.json()).catch(() => ({authenticated: false}));
// Pages that only the scorer may use send visitors to the sign-in page and bring them back afterwards.
async function requireLogin() {
  const a = await authReady;
  if (!a.authenticated) {
    location.replace('login.html?next=' + encodeURIComponent(location.pathname.split('/').pop() + location.search));
    await new Promise(() => {});
  }
  document.documentElement.classList.remove('gate');
  return a;
}
async function signOut() { await fetch(API_BASE + '/api/auth/logout/', {method: 'POST'}); location.href = 'index.html'; }

// Account control in the top-right corner of every page.
document.addEventListener('DOMContentLoaded', async () => {
  if (/login\.html$/.test(location.pathname)) return;
  const main = document.querySelector('main'); if (!main) return;
  const bar = document.createElement('div'); bar.className = 'authbar'; bar.id = 'authbar'; main.prepend(bar);
  const a = await authReady;
  bar.innerHTML = a.authenticated
    ? `<span class="uname">${esc(a.username)}</span><button class="pill" id="signout" type="button">Sign out</button>`
    : `<a class="pill" href="login.html?next=${encodeURIComponent(location.pathname.split('/').pop() + location.search)}">Sign in</a>`;
  const so = document.getElementById('signout'); if (so) so.onclick = signOut;
  const th = document.getElementById('theme'); if (th) bar.appendChild(th);   // home page: theme toggle sits beside it
});
