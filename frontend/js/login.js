let mode='login';
const $=id=>document.getElementById(id);
function setMode(m){
  mode=m;$('err').textContent='';
  $('t-login').setAttribute('aria-selected',m==='login');$('t-register').setAttribute('aria-selected',m==='register');
  $('go').textContent=m==='login'?'Log in':'Create account';
  $('pw').autocomplete=m==='login'?'current-password':'new-password';
  $('hint').hidden=m==='login';
}
$('f').onsubmit=async e=>{
  e.preventDefault();$('err').textContent='';
  try{
    const r=await fetch(API_BASE+'/api/auth/'+mode+'/',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:$('un').value,password:$('pw').value})});
    const j=await r.json(); if(!r.ok)throw new Error(j.error||'Something went wrong.');
    location.replace(safeNext(new URLSearchParams(location.search).get('next')));
  }catch(x){$('err').textContent=x.message}
};
setMode('login');
