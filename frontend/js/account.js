(async()=>{
  const $=id=>document.getElementById(id);
  const a=await requireLogin();
  $('who').textContent=a.username;
  $('pw').onsubmit=async e=>{
    e.preventDefault();$('pwerr').textContent='';$('pwok').textContent='';
    if($('np').value!==$('np2').value){$('pwerr').textContent="The two new passwords don't match.";return}
    try{
      const r=await fetch(API_BASE+'/api/auth/password/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:$('cur').value,new_password:$('np').value})});
      const j=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(r.status===429?'Too many tries. Wait a minute.':(j.error||'Something went wrong.'));
      $('pwok').textContent='Password changed.';$('pw').reset();
    }catch(x){$('pwerr').textContent=x.message}
  };
})();
