// Loaded on every page after config.js. Adds the CSRF header to POSTs and sends signed-out visitors to login.html.
(()=>{
  const cookie=n=>{const m=document.cookie.match('(?:^|; )'+n+'=([^;]*)');return m?decodeURIComponent(m[1]):''};
  const rawFetch=window.fetch.bind(window);
  let checked=null;   // set below; page API calls wait for it so a signed-out visitor never fires requests that just 403
  window.fetch=(u,o={})=>{
    const m=(o.method||'GET').toUpperCase();
    if(m!=='GET'&&m!=='HEAD')o={...o,headers:{...(o.headers||{}),'X-CSRFToken':cookie('csrftoken')}};
    const go=()=>rawFetch(u,{credentials:'same-origin',...o});
    if(!checked||String(u).includes('/api/auth/'))return go();
    return checked.then(me=>me.authenticated||liveLink?go():new Promise(()=>{}));   // not signed in: the page is redirecting
  };
  const page=location.pathname.split('/').pop()||'index.html';
  const onLogin=page==='login.html';
  const liveLink=page==='match.html'&&new URLSearchParams(location.search).get('mode')==='live'; // shared live links stay public
  const safeNext=n=>/^[\w-]+\.html(\?[\w=&%.-]*)?$/.test(n||'')?n:'index.html';
  checked=window.AUTH=rawFetch(API_BASE+'/api/auth/me/',{credentials:'same-origin'}).then(r=>r.json()).then(me=>{
    if(!me.authenticated&&!onLogin&&!liveLink)location.replace('login.html?next='+encodeURIComponent(page+location.search));
    if(me.authenticated&&onLogin)location.replace(safeNext(new URLSearchParams(location.search).get('next')));
    const who=document.getElementById('who');
    if(me.authenticated&&who){
      who.innerHTML='<span></span> <button type="button" class="link">Log out</button>';
      who.firstChild.textContent=me.username;
      who.querySelector('button').onclick=async()=>{await fetch(API_BASE+'/api/auth/logout/',{method:'POST'});location.replace('login.html')};
    }
    return me;
  });
  window.safeNext=safeNext;
})();
