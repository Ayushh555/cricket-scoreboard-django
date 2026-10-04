const Q=new URLSearchParams(location.search), ID=+Q.get('id'), SCORER=Q.get('mode')==='score', API=API_BASE+'/api/matches/'+ID+'/';
const DIS=[['bowled','Bowled'],['caught','Caught'],['lbw','LBW'],['stumped','Stumped'],['hit_wicket','Hit wkt']];
let seenBall=null,S=null,view='score',extra='',wtype='',wwho=null,wend='',pendingW=false,msg='';
const $=id=>document.getElementById(id);
async function load(){try{S=await (await fetch(API)).json();render()}catch(e){}}
async function post(path,body){
  const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  const j=await r.json();
  if(r.ok){S=j;msg='';extra='';wtype='';wwho=null;wend='';pendingW=false}else msg=j.error||'Something went wrong.';
  render();
}
const add=n=>post('ball/',{runs:n,extra,wicket:wtype,dismissed:wwho,end:wend});
const undo=()=>post('undo/');
const endMatch=()=>{if(confirm('End the match now? The result is worked out from the current score.'))post('end/')};
const delMatch=async()=>{if(!confirm('Delete this match and its scorecard? This cannot be undone.'))return;
  const r=await fetch(API,{method:'DELETE'});if(r.ok)location.href='history.html';else{msg='Could not delete the match.';render()}};
const pick=(role,id)=>post('select/',{role,player:id});
const setX=x=>{extra=extra===x?'':x;render()};
const toggleW=()=>{pendingW=!pendingW;wtype='';wwho=null;wend='';render()};
const toggleRO=()=>{wtype=wtype==='run_out'?'':'run_out';pendingW=false;wwho=null;wend='';render()};
const setEnd=k=>{wend=wend===k?'':k;render()};
const pickDis=t=>{wtype=t;wwho=null;add(0)};
const setWho=id=>{wwho=id;render()};
const tab=t=>{view=t;render()};
const share=()=>{navigator.clipboard&&navigator.clipboard.writeText(location.origin+location.pathname+'?id='+ID+'&mode=live');msg='Live link copied. Anyone with it can follow the score.';render()};

function hint(L){
  if(wtype==='run_out')return 'Run out: pick who is out, then tap the runs completed.';
  if(pendingW)return 'Pick how the batter got out.';
  const m={wd:'Wide: tap runs run on top of the wide.',nb:'No ball: tap runs off the bat.',lb:'Leg bye: tap runs the batters ran.'};
  return m[extra]||'Tap the runs for this ball.';
}
function bat(p,star,inn){
  if(!p)return '<div class="row"><span class="lbl">Waiting for next batter</span></div>';
  const s=inn.batting.find(x=>x.id===p.id)||{runs:0,balls:0};
  return `<div class="row ${star?'st':''}"><span>${esc(p.name)}</span><span class="n"><b>${s.runs}</b> (${s.balls})</span></div>`;
}
const ask=L=>L.need==='bowler'?(L.opening?'Who bowls the first over?':'Who bowls the next over?')
  :L.opening?(L.striker||L.non_striker?'Pick the other opener (non-striker).':'Pick the opener who faces the first ball (striker).'):'Who bats next?';
const GROUPS=[['batter','Batters'],['allrounder','All-rounders'],['bowler','Bowlers']];
function chooser(L){
  const order=L.need==='bowler'?[...GROUPS].reverse():GROUPS;
  return order.map(([r,t])=>{const o=L.options.filter(x=>x.role===r);
    return o.length?`<span class="lbl">${t}</span><div class="opts">${o.map(x=>`<button onclick="pick('${L.need}',${x.id})">${esc(x.name)}</button>`).join('')}</div>`:''}).join('');
}
function scoreView(inn){
  const L=S.live;
  if(!L)return `<div class="done">${esc(S.result)}</div>`+(SCORER?`<div class="act"><button onclick="undo()">Undo last ball</button><button onclick="location.href=\'new.html\'">New match</button><button onclick="delMatch()">Delete match</button></div>`:'');
  const bw=L.bowler&&(inn.bowling.find(x=>x.id===L.bowler.id)||{wickets:0,runs:0,overs:'0.0'});
  let h=`${L.opening?`<div class="sec"><span class="lbl">${esc(S.toss)}</span></div>`:''}<div class="sec"><span class="lbl">Over ${L.over_no}${L.bowler?', bowled by '+L.bowler.name:''}</span>
    <div class="chips">${L.this_over.map(b=>`<span class="chip ${b.k}">${b.t}</span>`).join('')||'<span class="lbl">No balls yet</span>'}</div></div>
    <div class="sec">${bat(L.striker,true,inn)}${bat(L.non_striker,false,inn)}
    ${bw?`<div class="row"><span>${esc(L.bowler.name)}</span><span class="n"><b>${bw.wickets}-${bw.runs}</b> (${bw.overs})</span></div>`:''}</div>`;
  if(!SCORER)return h;
  const undoRow=`<div class="act"><button onclick="undo()">Undo last ball</button><button onclick="share()">Copy live link</button><button onclick="endMatch()">End match</button></div>`;
  if(L.need)return h+`<div class="hint">${ask(L)}</div>
    ${chooser(L)}${undoRow}`;
  const ex=k=>`<button class="${extra===k?'on':''}" onclick="setX('${k}')">${{wd:'Wd',nb:'Nb',lb:'LB'}[k]}</button>`;
  const ro=`<button class="wbtn ${wtype==='run_out'?'on':''}" onclick="toggleRO()">Run out</button>`;
  const wk=`<button class="wbtn ${pendingW&&wtype!=='run_out'?'on':''}" onclick="toggleW()">Wicket</button>`;
  const x=ex('wd')+ex('nb')+ro+ex('lb')+wk;
  const d=pendingW?`<div class="wk">${DIS.map(([k,t])=>`<button class="${wtype===k?'on':''}" onclick="pickDis('${k}')">${t}</button>`).join('')}</div>`:'';
  const who=wtype==='run_out'?`<div class="wk" style="grid-template-columns:1fr 1fr">${[L.striker,L.non_striker].map(p=>`<button class="${(wwho||L.striker.id)===p.id?'on':''}" onclick="setWho(${p.id})">${esc(p.name)} out</button>`).join('')}</div>`:'';
  const endRow=wtype==='run_out'?`<span class="lbl">Out at which end? Leave unselected to work it out from the runs.</span><div class="wk" style="grid-template-columns:1fr 1fr">${[['striker',"Striker's end"],['non',"Non-striker's end"]].map(([k,t])=>`<button class="${wend===k?'on':''}" onclick="setEnd('${k}')">${t}</button>`).join('')}</div>`:'';
  return h+`<div class="hint">${hint(L)}</div><div class="mods">${x}</div>${d}${who}${endRow}
    <div class="pad">${[0,1,2,3,4,6].map(n=>`<button class="${n>3?'hi':''}" onclick="add(${n})">${n}</button>`).join('')}</div>${undoRow}`;
}
function cardView(){
  return `<span class="lbl" style="margin-top:10px">${esc(S.toss)}</span>`+S.innings.map(i=>`<h2>${esc(i.team)}, innings ${i.number}: ${i.runs}/${i.wickets} (${i.overs} ov)</h2>
   <div class="wrap"><table><tr><th>Batter</th><th>R</th><th>B</th><th>4s</th><th>6s</th><th>SR</th></tr>
   ${i.batting.map(p=>`<tr><td>${esc(p.name)}<small>${esc(p.out||'not out')}</small></td><td><b>${p.runs}</b></td><td>${p.balls}</td><td>${p.fours}</td><td>${p.sixes}</td><td>${p.balls?Math.round(p.runs*100/p.balls):'-'}</td></tr>`).join('')}</table></div>
   ${i.yet_to_bat.length?`<span class="lbl">Yet to bat: ${i.yet_to_bat.map(esc).join(', ')}</span>`:''}
   <div class="wrap"><table><tr><th>Bowler</th><th>O</th><th>R</th><th>W</th><th>Econ</th></tr>
   ${i.bowling.map(p=>`<tr><td>${esc(p.name)}</td><td>${p.overs}</td><td>${p.runs}</td><td><b>${p.wickets}</b></td><td>${p.econ}</td></tr>`).join('')||'<tr><td colspan="5">No overs bowled yet</td></tr>'}</table></div>`).join('');
}
function celebrate(n){
  const el=document.createElement('div'); el.className='boom b'+n; el.setAttribute('aria-hidden','true');
  el.innerHTML=`<div class="bt">${n===4?'FOUR!':'SIX!'}</div><span class="bball"></span>`+
    Array.from({length:18},(_,i)=>`<i style="--a:${i*20}deg;--d:${90+Math.random()*80}px"></i>`).join('');
  document.body.appendChild(el); setTimeout(()=>el.remove(),1700);
  if(SCORER&&navigator.vibrate)navigator.vibrate(n===6?[40,40,60]:40);
}
function watchBall(){                       // celebrate a new boundary off the bat (not on first load, not on undo)
  const lb=S.last_ball, id=lb?lb.id:0;
  if(seenBall!==null&&lb&&id>seenBall&&!lb.wicket&&(lb.runs===4||lb.runs===6))celebrate(lb.runs);
  seenBall=id;
}
function render(){
  if(!S)return;
  watchBall();
  const inn=S.innings[S.innings.length-1], L=S.live;
  $('title').textContent=S.title; $('sub').textContent='Innings '+inn.number+', '+S.overs_limit+' overs';
  $('hero').innerHTML=`<div class="score">${inn.runs}<i>/${inn.wickets}</i></div>
    <div class="meta"><b>${inn.overs}</b>of ${S.overs_limit} overs<br>Run rate ${inn.run_rate.toFixed(2)}</div>`;
  $('chase').innerHTML=esc(L&&L.target?`${inn.team} need ${L.runs_needed} from ${L.balls_left} balls (target ${L.target})`:
    (S.status==='completed'?S.result:inn.team+' batting'));
  ['score','card'].forEach(t=>$('t-'+t).setAttribute('aria-selected',view===t));
  $('view').innerHTML=(view==='score'?scoreView(inn):cardView())+(msg?`<p class="${msg.startsWith('Live')?'hint':'err'}" role="alert">${msg}</p>`:'');
}
load();
if(!SCORER)setInterval(load,4000);
