(async()=>{
  const $=id=>document.getElementById(id);
  const me=await authReady;
  const n=new URLSearchParams(location.search).get('next')||'index.html';
  const next=/^[\w.\-]+(\?[\w=&%.\-]*)?$/.test(n)?n:'index.html';        // only same-site pages
  if(me.authenticated){location.replace(next);return}
  const setup=!!me.can_register;                                          // first run: no account exists yet
  if(setup){
    $('title').textContent='Create your scorer account';
    $('sub').textContent='First time here. Choose a username and password. You will use them to score and manage matches.';
    $('go').textContent='Create account'; $('p2box').hidden=false; $('p2').required=true;
    $('p').autocomplete='new-password';
  }
  $('f').onsubmit=async e=>{
    e.preventDefault(); $('err').textContent='';
    if(setup&&$('p').value!==$('p2').value){$('err').textContent="The two passwords don't match.";return}
    $('go').disabled=true;
    try{
      const r=await fetch(API_BASE+'/api/auth/'+(setup?'register/':'login/'),{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({username:$('u').value.trim(),password:$('p').value})});
      const j=await r.json();
      if(!r.ok){$('err').textContent=r.status===429?'Too many tries. Wait a minute and try again.':(j.error||'Could not sign in.');return}
      location.href=next;
    }catch(x){$('err').textContent="Can't reach the scoring server."}
    finally{$('go').disabled=false}
  };
})();
