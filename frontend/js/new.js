let TEAMS=[];
const $=id=>document.getElementById(id);
const ROLES=[['allrounder','All-rounder'],['batter','Batter'],['bowler','Bowler']], SLOTS=11;
const armed={};   // two-step delete: first tap arms the button, second tap deletes

function panel(k){
  const rows=Array.from({length:SLOTS},(_,i)=>`<div class="pl" style="--i:${i}"><span class="no">${i+1}</span>
      <input id="pn${k}${i}" placeholder="Player ${i+1}" aria-label="Player ${i+1} name" autocomplete="off">
      <select id="pr${k}${i}" aria-label="Player ${i+1} role">${ROLES.map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></div>`).join('');
  $('p'+k).innerHTML=`<label class="lbl" for="s${k}">Team ${k.toUpperCase()}</label>
   <div class="selrow"><select id="s${k}"></select>
     <button type="button" class="del" id="d${k}">Delete team</button></div>
   <div class="reveal" id="n${k}" inert><div class="inner">
     <input id="nm${k}" placeholder="Team name" aria-label="Team name" style="margin-top:8px">
     <h3 class="xi">Playing 11</h3>
     <span class="lbl">Fill at least 2 boxes and leave the rest empty if you have fewer players. Batters open the innings, bowlers and all-rounders bowl. A team name you've used before can be picked from the list any time.</span>
     ${rows}
   </div></div>`;
  fill(k);
  $('s'+k).onchange=()=>{disarm(k);refresh()}; $('nm'+k).oninput=refresh;
  $('d'+k).onclick=()=>removeTeam(k);
}
function fill(k,keep){
  const s=$('s'+k), want=keep!==undefined?keep:s.value;
  s.innerHTML=TEAMS.map(t=>`<option value="${t.id}">${esc(t.name)} (${t.players.length} players)</option>`).join('')+'<option value="new">+ New team</option>';
  s.value=[...s.options].some(o=>o.value===String(want))?String(want):(TEAMS.length?String(TEAMS[0].id):'new');
}
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function name(k){const s=$('s'+k);return s.value==='new'?($('nm'+k).value||'Team '+k.toUpperCase()):s.selectedOptions[0].text.replace(/ \(\d+ players\)$/,'')}
function refresh(){
  ['a','b'].forEach(k=>{
    const isNew=$('s'+k).value==='new', box=$('n'+k);
    box.classList.toggle('open',isNew); box.inert=!isNew;
    $('d'+k).hidden=isNew;
  });
  const cur=$('tw').value||'a';
  $('tw').innerHTML=`<option value="a">${esc(name('a'))}</option><option value="b">${esc(name('b'))}</option>`;$('tw').value=cur;
}
function disarm(k){clearTimeout(armed[k]);armed[k]=null;const b=$('d'+k);if(b){b.classList.remove('armed');b.textContent='Delete team'}}
async function removeTeam(k){
  const b=$('d'+k), id=$('s'+k).value; if(id==='new')return;
  if(!armed[k]){
    b.classList.add('armed');b.textContent='Tap again to confirm';
    armed[k]=setTimeout(()=>disarm(k),4000);return;
  }
  disarm(k);$('err').textContent='';
  try{
    const r=await fetch(API_BASE+'/api/teams/'+id+'/',{method:'DELETE'});
    const j=await r.json(); if(!r.ok)throw new Error(j.error||'Could not delete the team.');
    const gone=TEAMS.find(t=>String(t.id)===id); TEAMS=j;
    ['a','b'].forEach(x=>fill(x)); refresh();
    toast((gone?gone.name:'Team')+' deleted. Its matches stay in the records.');
  }catch(x){$('err').textContent=x.message}
}
function toast(t){
  const e=document.createElement('div');e.className='toast';e.textContent=t;e.setAttribute('role','status');
  document.body.appendChild(e);setTimeout(()=>e.remove(),3200);
}
async function teamId(k){
  const v=$('s'+k).value; if(v!=='new')return +v;
  const nm=$('nm'+k).value.trim();
  const filled=Array.from({length:SLOTS},(_,i)=>$('pn'+k+i).value.trim()).some(Boolean);
  const same=TEAMS.find(t=>t.name.toLowerCase()===nm.toLowerCase());
  if(same&&!filled)return same.id;   // typed a name you've already saved and no new players: reuse that team
  const r=await fetch(API_BASE+'/api/teams/',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:nm,players:Array.from({length:SLOTS},(_,i)=>({name:$('pn'+k+i).value,role:$('pr'+k+i).value})).filter(p=>p.name.trim())})});
  const j=await r.json(); if(!r.ok)throw new Error(j.error);
  TEAMS=j; return j.find(t=>t.name.toLowerCase()===nm.toLowerCase()).id;
}
$('f').onsubmit=async e=>{
  e.preventDefault();$('err').textContent='';const go=e.submitter||document.querySelector('#f button[type=submit]');go.classList.add('busy');
  try{
    const a=await teamId('a'), b=await teamId('b');
    const r=await fetch(API_BASE+'/api/matches/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      team_a:a,team_b:b,overs_limit:+$('ov').value,toss_winner:$('tw').value==='a'?a:b,toss_decision:$('td').value})});
    const j=await r.json(); if(!r.ok)throw new Error(j.error);
    document.body.classList.add('leaving');
    setTimeout(()=>location.href='match.html?id='+j.id+'&mode=score',180);
  }catch(x){$('err').textContent=x.message;go.classList.remove('busy')}
};
(async()=>{   // only one match can be played at a time
  try{const m=await (await fetch(API_BASE+'/api/matches/')).json(), live=m.find(x=>x.status==='live');
    if(live){$('err').innerHTML=esc(live.title)+' is still live. Resume it or end it to start a new match.';
      const bar=document.createElement('div');bar.className='livebar';
      bar.innerHTML='<a class="btn" href="match.html?id='+live.id+'&mode=score">Resume match</a>';
      bar.appendChild(endButton(live.id,()=>location.reload()));$('err').after(bar);
      document.querySelectorAll('#f button[type=submit]').forEach(b=>b.disabled=true)}}catch(x){}
})();
(async()=>{TEAMS=await (await fetch(API_BASE+'/api/teams/')).json();panel('a');panel('b');
  if(TEAMS.length>1)$('sb').value=String(TEAMS[1].id);   // sensible default: two different teams
  refresh();})();
