let TEAMS=[];
const $=id=>document.getElementById(id);
const ROLES=[['allrounder','All-rounder'],['batter','Batter'],['bowler','Bowler']], SLOTS=11;
function panel(k){
  const rows=Array.from({length:SLOTS},(_,i)=>`<div class="pl"><span class="no">${i+1}</span>
      <input id="pn${k}${i}" placeholder="Player ${i+1}" aria-label="Player ${i+1} name" autocomplete="off">
      <select id="pr${k}${i}" aria-label="Player ${i+1} role">${ROLES.map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></div>`).join('');
  $('p'+k).innerHTML=`<label class="lbl" for="s${k}">Team ${k.toUpperCase()}</label>
   <select id="s${k}">${TEAMS.map(t=>`<option value="${t.id}">${esc(t.name)} (${t.players.length} players)</option>`).join('')}<option value="new">+ New team</option></select>
   <div id="n${k}" hidden>
     <input id="nm${k}" placeholder="Team name" aria-label="Team name" style="margin-top:8px">
     <h3 class="xi">Playing 11</h3>
     <span class="lbl">Fill at least 2 boxes and leave the rest empty if you have fewer players. Batters open the innings, bowlers and all-rounders bowl.</span>
     ${rows}
   </div>`;
  $('s'+k).onchange=refresh; $('nm'+k).oninput=refresh;
  if(!TEAMS.length)$('s'+k).value='new';
}
function name(k){const s=$('s'+k);return s.value==='new'?($('nm'+k).value||'Team '+k.toUpperCase()):s.selectedOptions[0].text.replace(/ \(\d+ players\)$/,'')}
function refresh(){
  ['a','b'].forEach(k=>{if($('n'+k))$('n'+k).hidden=$('s'+k).value!=='new'});
  const cur=$('tw').value||'a';
  $('tw').innerHTML=`<option value="a">${esc(name('a'))}</option><option value="b">${esc(name('b'))}</option>`;$('tw').value=cur;
}
async function teamId(k){
  const v=$('s'+k).value; if(v!=='new')return +v;
  const r=await fetch(API_BASE+'/api/teams/',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:$('nm'+k).value,players:Array.from({length:SLOTS},(_,i)=>({name:$('pn'+k+i).value,role:$('pr'+k+i).value})).filter(p=>p.name.trim())})});
  const j=await r.json(); if(!r.ok)throw new Error(j.error);
  return j.find(t=>t.name.toLowerCase()===$('nm'+k).value.trim().toLowerCase()).id;
}
$('f').onsubmit=async e=>{
  e.preventDefault();$('err').textContent='';
  try{
    const a=await teamId('a'), b=await teamId('b');
    const r=await fetch(API_BASE+'/api/matches/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      team_a:a,team_b:b,overs_limit:+$('ov').value,toss_winner:$('tw').value==='a'?a:b,toss_decision:$('td').value})});
    const j=await r.json(); if(!r.ok)throw new Error(j.error);
    location.href='match.html?id='+j.id+'&mode=score';
  }catch(x){$('err').textContent=x.message}
};
(async()=>{TEAMS=await (await fetch(API_BASE+'/api/teams/')).json();panel('a');panel('b');refresh();})();
