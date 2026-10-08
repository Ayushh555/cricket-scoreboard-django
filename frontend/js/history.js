const box=document.getElementById('matches');
async function load(){
  try{
    const A=await requireLogin();
    const m=await (await fetch(API_BASE+'/api/matches/')).json();
    box.innerHTML=m.length?m.map(x=>`<div class="mwrap"><a class="mrow" href="match.html?id=${x.id}&mode=${x.status==='live'&&A.authenticated?'score':'live'}">
      <b>${esc(x.title)}</b> ${x.status==='live'?'<span class="live-dot">LIVE</span>':''}
      <small>${x.scores.map(esc).join('  |  ')||'Not started'}</small><small>${esc(x.result||x.date)}</small></a>
      ${A.authenticated?`<button class="del" onclick="del(${x.id})">Delete</button>`:''}</div>`).join(''):'<span class="lbl">No matches yet. Start one from the home screen.</span>';
  }catch(e){box.innerHTML='<p class="err">Can\'t reach the scoring server.</p>'}
}
async function del(id){
  if(!confirm('Delete this match and its scorecard? This cannot be undone.'))return;
  const r=await fetch(API_BASE+'/api/matches/'+id+'/',{method:'DELETE'});
  if(r.ok)load(); else alert('Could not delete the match.');
}
load();
