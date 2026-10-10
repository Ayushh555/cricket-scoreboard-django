(async()=>{
  const $=id=>document.getElementById(id);
  const me=await authReady;
  const n=new URLSearchParams(location.search).get('next')||'index.html';
  const next=/^[\w.\-]+(\?[\w=&%.\-]*)?$/.test(n)?n:'index.html';        // only same-site pages
  if(me.authenticated){location.replace(next);return}
  const setup=!!me.can_register;                                          // first run: no account exists yet
  const open=!!me.open_signup;
  let known=false; try{known=localStorage.getItem('crease_member')==='1'}catch(e){}
  // Newcomers land on Register. Anyone who has signed in or registered here before lands on Sign in.
  let mode=setup?'register':(open&&!known?'register':'login');
  const qm=new URLSearchParams(location.search).get('mode'); if(open&&(qm==='login'||qm==='register'))mode=qm;
    function paint(){
    const reg=mode==='register';
    $('title').textContent=setup?'Create your scorer account':reg?'Create an account':'Sign in';
    $('sub').textContent=setup?'First time here. Choose a username and password. You will use them to score and manage matches.'
      :reg?'Register first, then sign in. Every account keeps its own teams and scores its own matches.'
      :'Sign in to score your matches. Just watching one game? Open the live link the scorer shared with you. No account needed.';
    $('go').textContent=reg?'Create account':'Sign in';
    $('p2box').hidden=!reg; $('p2').required=reg;
    $('p').autocomplete=reg?'new-password':'current-password';
    $('err').textContent='';
    $('swapbox').hidden=setup||!open;
    $('swaptxt').textContent=reg?'Already registered?':'New here?';
    $('swap').textContent=reg?'Sign in':'Create an account';
  }
  $('swap').onclick=e=>{e.preventDefault();$('ok').textContent='';mode=mode==='register'?'login':'register';paint()};
  paint();
  $('f').onsubmit=async e=>{
    e.preventDefault(); $('err').textContent=''; $('ok').textContent='';
    const reg=mode==='register';
    if(reg&&$('p').value!==$('p2').value){$('err').textContent="The two passwords don't match.";return}
    $('go').disabled=true;
    try{
      const user=$('u').value.trim();
      const body=JSON.stringify({username:user,password:$('p').value});
      const r=await fetch(API_BASE+'/api/auth/'+(reg?'register/':'login/'),{method:'POST',headers:{'Content-Type':'application/json'},body});
      const j=await r.json();
      if(!r.ok){$('err').textContent=r.status===429?(j.error||'Too many tries. Wait a minute and try again.'):(j.error||'Could not continue.');return}
      try{localStorage.setItem('crease_member','1')}catch(x){}
      if(reg&&!j.authenticated){                       // registered: now sign in
        mode='login';paint();$('p').value='';$('p2').value='';
        $('ok').textContent='Account created. Now sign in.';$('p').focus();return;
      }
      location.href=next;
    }catch(x){$('err').textContent="Can't reach the scoring server."}
    finally{$('go').disabled=false}
  };
})();
