// Keeps the pages and scripts available with no signal. Scores and accounts always come from the server (never cached here).
const CACHE = 'crease-shell-v1';
const SHELL = ['index.html', 'match.html', 'new.html', 'login.html', 'history.html', 'teams.html', 'account.html',
  'css/style.css', 'js/config.js', 'js/theme.js', 'js/qr.js', 'js/engine.js', 'js/match.js', 'js/home.js', 'js/new.js',
  'js/login.js', 'js/history.js', 'js/teams.js', 'js/account.js'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/api/') || u.pathname.startsWith('/admin/')) return;
  e.respondWith(fetch(r).then(res => {                                   // online: always the newest copy
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(r, copy)); }
    return res;
  }).catch(() => caches.match(r, {ignoreSearch: true})));                // offline: the last copy we saw
});
