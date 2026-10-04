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
  const cc=$('caller').value||'a';
  $('caller').innerHTML=`<option value="a">${esc(name('a'))}</option><option value="b">${esc(name('b'))}</option>`;$('caller').value=cc;
  renderToss();
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
// ---------- virtual toss ----------
let call='heads', toss=null, flipping=false, angle=0;     // toss = {result, winner:'a'|'b', decision:null|'bat'|'bowl'}
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
const tossMode=()=>document.querySelector('.tmode[aria-selected="true"]').dataset.m;
document.querySelectorAll('.tmode').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.tmode').forEach(x=>x.setAttribute('aria-selected',x===b));
  $('vtoss').hidden=b.dataset.m!=='virtual'; $('mtoss').hidden=b.dataset.m!=='manual';
});
document.querySelectorAll('.call').forEach(b=>b.onclick=()=>{
  if(toss||flipping)return;                                  // the call is locked once the coin is in the air
  call=b.dataset.c; document.querySelectorAll('.call').forEach(x=>x.setAttribute('aria-selected',x===b)); renderToss();
});
$('caller').onchange=()=>{if(!toss&&!flipping)renderToss()};
function renderToss(){
  const r=$('tossres'); if(!r)return;
  $('caller').disabled=!!toss||flipping;
  document.querySelectorAll('.call').forEach(b=>b.disabled=!!toss||flipping);
  $('flip').textContent=toss?'Toss done':flipping?'Flipping...':'Flip the coin'; $('flip').disabled=!!toss||flipping;
  if(!toss){r.innerHTML=flipping?'':`<p class="lbl" style="margin-top:10px">${esc(name($('caller').value))} call ${call}.</p>`;return}
  r.innerHTML=`<p class="tossline"><b>${toss.result==='heads'?'Heads':'Tails'}!</b> ${esc(name(toss.winner))} won the toss.</p>
    <span class="lbl">${esc(name(toss.winner))} choose to:</span>
    <div class="seg" role="group" aria-label="Toss decision">
      <button type="button" class="dec" data-d="bat" aria-selected="${toss.decision==='bat'}">Bat first</button>
      <button type="button" class="dec" data-d="bowl" aria-selected="${toss.decision==='bowl'}">Bowl first</button></div>
    <button type="button" class="link" id="redo">Toss again</button>`;
  r.querySelectorAll('.dec').forEach(b=>b.onclick=()=>{toss.decision=b.dataset.d;$('err').textContent='';renderToss()});
  $('redo').onclick=()=>{toss=null;renderToss()};
}
$('flip').onclick=()=>{
  if(toss||flipping)return;
  const heads=crypto.getRandomValues(new Uint8Array(1))[0]%2===0, result=heads?'heads':'tails';
  const caller=$('caller').value, winner=call===result?caller:(caller==='a'?'b':'a');
  flipping=true; renderToss();
  const target=heads?0:180;                                   // heads face is the front, tails the back
  angle+=1800+((target-angle%360)+360)%360;
  $('coin').style.transform=`rotateY(${angle}deg)`;
  if(!reduceMotion){$('coinbox').classList.remove('up');void $('coinbox').offsetWidth;$('coinbox').classList.add('up')}
  setTimeout(()=>{flipping=false;toss={result,winner,decision:null};renderToss()},reduceMotion?0:1900);
};
function tossValue(){
  if(tossMode()==='manual')return {w:$('tw').value,d:$('td').value};
  if(!toss)throw new Error('Flip the coin first, or switch to "Set manually".');
  if(!toss.decision)throw new Error(name(toss.winner)+' won the toss. Choose bat first or bowl first.');
  return {w:toss.winner,d:toss.decision};
}
$('f').onsubmit=async e=>{
  e.preventDefault();$('err').textContent='';
  try{
    const t=tossValue();
    const a=await teamId('a'), b=await teamId('b');
    const r=await fetch(API_BASE+'/api/matches/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      team_a:a,team_b:b,overs_limit:+$('ov').value,toss_winner:t.w==='a'?a:b,toss_decision:t.d})});
    const j=await r.json(); if(!r.ok)throw new Error(j.error);
    location.href='match.html?id='+j.id+'&mode=score';
  }catch(x){$('err').textContent=x.message}
};
(async()=>{TEAMS=await (await fetch(API_BASE+'/api/teams/')).json();panel('a');panel('b');refresh();})();
