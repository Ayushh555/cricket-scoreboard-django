const box=document.getElementById('teams');
const ROLE={batter:'Batter',bowler:'Bowler',allrounder:'All-rounder'};
async function load(){
  try{
    const t=await (await fetch(API_BASE+'/api/teams/')).json();
    box.innerHTML=t.length?t.map(x=>`<div class="mwrap"><div class="mrow"><b>${esc(x.name)}</b>
      <small>${x.roster.map(p=>esc(p.name)).join(', ')}</small>
      <small>${x.roster.length} players, ${x.matches} ${x.matches===1?'match':'matches'}</small></div>
      <button class="del" data-name="${esc(x.name)}" onclick="del(${x.id},this.dataset.name)">Delete</button></div>`).join(''):'<span class="lbl">No teams yet. They are created when you start a new match.</span>';
  }catch(e){box.innerHTML='<p class="err">Can\'t reach the scoring server.</p>'}
}
async function del(id,name,force){
  if(!force&&!confirm('Delete the team '+name+'?'))return;
  const r=await fetch(API_BASE+'/api/teams/'+id+'/'+(force?'?force=1':''),{method:'DELETE'});
  const j=await r.json();
  if(r.ok)return load();
  if(j.code==='in_use'&&confirm(j.error))return del(id,name,true);
  if(j.code!=='in_use')alert(j.error||'Could not delete the team.');
}
load();
