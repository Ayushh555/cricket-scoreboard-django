// Same-origin by default: Django serves this folder, so the API is on the same address.
// Hosting the frontend separately? Set the backend address, e.g. 'http://127.0.0.1:8000'
// (and enable CORS on the backend).
const API_BASE = '';

// Escape text before it goes into innerHTML (team and player names are typed by users).
const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
