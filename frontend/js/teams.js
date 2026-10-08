const box=document.getElementById('teams');
const ROLE={batter:'Batter',bowler:'Bowler',allrounder:'All-rounder'};
const open=new Set();
async function load(){
  try{
    const A=await requireLogin();
    const t=await (await fetch(API_BASE+'/api/teams/')).json();
    box.innerHTML=t.length?t.map(x=>`<div class="acc team ${open.has(x.id)?'open':''}" data-id="${x.id}">
      <div class="mwrap"><button class="accbtn" type="button" aria-expanded="${open.has(x.id)}"><b>${esc(x.name)}</b>
        <small>${x.roster.length} players, ${x.matches} ${x.matches===1?'match':'matches'}. Tap to see the players</small><span class="chev" aria-hidden="true"></span></button>
        ${A.authenticated?`<button class="del" data-name="${esc(x.name)}" onclick="del(${x.id},this.dataset.name)">Delete team</button>`:''}</div>
      <div class="accbody"><div class="accin"><ul class="plist">${x.roster.map(p=>`<li><span>${esc(p.name)}<small>${ROLE[p.role]||''}</small></span>
        ${A.authenticated?`<button class="del sm" data-name="${esc(p.name)}" onclick="delPlayer(${p.id},this.dataset.name)">Delete</button>`:''}</li>`).join('')}</ul></div></div></div>`).join(''):
      '<span class="lbl">No teams yet. They are created when you start a new match.</span>';
  }catch(e){box.innerHTML='<p class="err">Can\'t reach the scoring server.</p>'}
}
box.addEventListener('click',e=>{
  const b=e.target.closest('.accbtn'); if(!b)return;
  const acc=b.closest('.acc'), id=+acc.dataset.id, o=!acc.classList.contains('open');
  acc.classList.toggle('open',o); b.setAttribute('aria-expanded',o); o?open.add(id):open.delete(id);
});
async function del(id,name,force){
  if(!force&&!confirm('Delete the team '+name+'?'))return;
  const r=await fetch(API_BASE+'/api/teams/'+id+'/'+(force?'?force=1':''),{method:'DELETE'});
  const j=await r.json();
  if(r.ok)return load();
  if(j.code==='in_use'&&confirm(j.error))return del(id,name,true);
  if(j.code!=='in_use')alert(j.error||'Could not delete the team.');
}
async function delPlayer(id,name){
  if(!confirm('Delete '+name+' from the team?'))return;
  const r=await fetch(API_BASE+'/api/players/'+id+'/',{method:'DELETE'});
  if(r.ok)return load();
  alert((await r.json()).error||'Could not delete the player.');
}
load();
