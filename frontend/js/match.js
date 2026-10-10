const Q_=new URLSearchParams(location.search), ID=+Q_.get('id'), SCORER=Q_.get('mode')==='score', API=API_BASE+'/api/matches/'+ID+'/';
const DIS=[['bowled','Bowled'],['caught','Caught'],['lbw','LBW'],['stumped','Stumped'],['hit_wicket','Hit wkt']];
let seenBall=null,S=null,view='score',extra='',wtype='',wwho=null,wend='',pendingW=false,msg='';
const $=id=>document.getElementById(id);
if(SCORER)requireLogin();
else authReady.then(a=>{if(!a.authenticated){const n=document.querySelector('.navrow');if(n)n.remove()}});   // visitors only have the live view

// ---------- talking to the server, and keeping working without it ----------
// base = the last version the server sent. queue = scores taken while offline, replayed on the server when the signal returns.
const KEY='crease:m:'+ID, Q={base:null,queue:[],err:'',syncing:false,online:true,stamp:0};
const uid=()=>Math.random().toString(36).slice(2,10)+Date.now().toString(36);
function saveQ(){try{localStorage.setItem(KEY,JSON.stringify({base:Q.base,queue:Q.queue}))}catch(e){}}
function loadQ(){try{const j=JSON.parse(localStorage.getItem(KEY)||'null');if(j&&j.base){Q.base=j.base;Q.queue=SCORER?(j.queue||[]):[]}}catch(e){}}
function recompute(){
  if(!Q.base)return;
  if(!Q.queue.length){S=Q.base;return}
  const r=Engine.replay(Q.base,Q.queue);
  if(r.error){Q.queue=Q.queue.slice(0,r.applied);saveQ()}   // should not happen; keep what still fits
  S=r.S;
}
function setBase(j){Q.base=j;Q.stamp=Date.now();saveQ();recompute()}
const isNet=e=>!!e&&(e.name==='AbortError'||e.name==='TypeError');   // fetch rejects with TypeError when there is no connection
async function net(url,opts={},ms=6000){
  const ac=new AbortController(), t=setTimeout(()=>ac.abort(),ms);
  try{const r=await fetch(url,{...opts,signal:ac.signal});let j={};try{j=await r.json()}catch(e){}return {ok:r.ok,status:r.status,json:j}}
  finally{clearTimeout(t)}
}
const post=(path,body)=>net(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
const clearForm=()=>{extra='';wtype='';wwho=null;wend='';pendingW=false};

async function load(){
  try{
    const r=await net(API);
    Q.online=true;
    if(r.ok&&!Q.queue.length)setBase(r.json);
  }catch(e){ if(!isNet(e))return; Q.online=false }
  if(!S&&Q.base)recompute();
  render();
  if(Q.queue.length&&Q.online&&!Q.err)sync();
}
// Scoring actions: try the server; with no signal, apply the rules here and queue the action.
async function act(type,body){
  const a={type,...body}; if(type==='ball')a.cid=uid();
  msg='';
  if(Q.queue.length||!Q.online&&type!=='undo'){ return enqueue(a) }
  try{
    const r=await post(type==='ball'?'ball/':'select/',type==='ball'?{runs:a.runs,extra:a.extra,wicket:a.wicket,dismissed:a.dismissed,end:a.end,cid:a.cid}:{role:a.role,player:a.player});
    Q.online=true;
    if(r.ok){setBase(r.json);clearForm()}else msg=r.json.error||'Something went wrong.';
    render();
  }catch(e){ if(isNet(e)){Q.online=false;enqueue(a)} else {msg='Something went wrong.';render()} }
}
function enqueue(a){
  if(!Q.base||!Q.base.live||!Q.base.live.roster){msg="No connection, and this match isn't saved on the phone yet. Reconnect once.";render();return}
  const r=Engine.apply(S,a);
  if(r.error){msg=r.error;render();return}
  Q.queue.push(a);saveQ();recompute();clearForm();render();
}
async function sync(){
  if(Q.syncing||!Q.queue.length)return;
  Q.syncing=true;render();
  try{
    while(Q.queue.length){
      const a=Q.queue[0];
      let r;
      try{ r=await post(a.type==='ball'?'ball/':'select/',a.type==='ball'?{runs:a.runs,extra:a.extra,wicket:a.wicket,dismissed:a.dismissed,end:a.end,cid:a.cid}:{role:a.role,player:a.player}) }
      catch(e){ if(isNet(e)){Q.online=false;break} throw e }
      Q.online=true;
      if(r.ok){Q.queue.shift();Q.base=r.json;Q.err='';saveQ();continue}
      // The server said no. If it was a pick that already went through earlier (a lost reply), skip it.
      let g=null; try{g=await net(API)}catch(e){}
      if(g&&g.ok){
        const rest=Q.queue.slice(1);
        if(a.type==='select'&&Engine.replay(g.json,rest).applied===rest.length){Q.queue=rest;Q.base=g.json;saveQ();continue}
        Q.base=g.json;saveQ();
      }
      Q.err=r.json.error||'The server could not accept a score.';break;
    }
    recompute();
    if(!Q.queue.length&&!Q.err){msg='All offline scores are saved.'}
  }catch(e){}
  Q.syncing=false;render();
}
const retrySync=()=>{Q.err='';sync()};
const useServer=async()=>{Q.queue=[];Q.err='';try{const g=await net(API);if(g.ok)Q.base=g.json}catch(e){}saveQ();recompute();clearForm();render()};
window.addEventListener('online',()=>{Q.online=true;if(SCORER)sync();load()});
window.addEventListener('offline',()=>{Q.online=false;render()});
setInterval(()=>{if(SCORER&&Q.queue.length&&!Q.err)sync()},6000);

const add=n=>act('ball',{runs:n,extra,wicket:wtype,dismissed:wwho,end:wend});
async function undo(){
  msg='';
  if(Q.queue.length){const last=Q.queue[Q.queue.length-1];Q.queue.pop();if(last.type==='select'&&Q.queue.length===0&&Q.err)Q.err='';saveQ();recompute();clearForm();render();return}
  try{const r=await post('undo/');Q.online=true;if(r.ok){setBase(r.json);clearForm()}else msg=r.json.error||'Nothing to undo.'}
  catch(e){if(isNet(e)){Q.online=false;msg='No connection. Offline, you can only undo scores taken since you went offline.'}}
  render();
}
const endMatch=async()=>{if(!confirm('End the match now? The result is worked out from the current score.'))return;
  if(Q.queue.length){msg='Wait for the offline scores to send first.';render();return}
  try{const r=await post('end/');if(r.ok){setBase(r.json);clearForm()}else msg=r.json.error||'Could not end the match.'}catch(e){msg='No connection. Try again when you are online.'}render()};
const delMatch=async()=>{if(!confirm('Delete this match and its scorecard? This cannot be undone.'))return;
  try{const r=await net(API,{method:'DELETE'});if(r.ok){try{localStorage.removeItem(KEY)}catch(e){}location.href='history.html'}else{msg='Could not delete the match.';render()}}catch(e){msg='No connection. Try again when you are online.';render()}};
const pick=(role,id)=>act('select',{role,player:id});
const setX=x=>{extra=extra===x?'':x;render()};
const toggleW=()=>{pendingW=!pendingW;wtype='';wwho=null;wend='';render()};
const toggleRO=()=>{wtype=wtype==='run_out'?'':'run_out';pendingW=false;wwho=null;wend='';render()};
const setEnd=k=>{wend=wend===k?'':k;render()};
const pickDis=t=>{wtype=t;wwho=null;add(0)};
const setWho=id=>{wwho=id;render()};
const tab=t=>{view=t;render()};
const openShare=()=>{const d=$('share');d.open=true;d.scrollIntoView({behavior:'smooth',block:'center'})};

// ---------- the score screen ----------
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
function doneBox(){
  const sum=(S.summary||[]).map(l=>`<li>${esc(l)}</li>`).join('');
  const p=S.potm;
  return `<div class="done">${esc(S.result)}</div>`+
    (p?`<div class="potm"><span class="lbl">Player of the match</span><b>${esc(p.name)}</b><small>${esc(p.team)}${p.line?' · '+esc(p.line):''}</small></div>`:'')+
    (sum?`<ul class="sumlist">${sum}</ul>`:'');
}
function scoreView(inn){
  const L=S.live;
  if(!L)return doneBox()+(SCORER?`<div class="act"><button onclick="undo()">Undo last ball</button><button onclick="location.href='new.html'">New match</button><button onclick="delMatch()">Delete match</button></div>`:'');
  if(S._offlineEnd)return `<div class="done">Innings finished. Connect to the internet to carry on. Every ball is saved on this phone and will be sent.</div>`+(SCORER?`<div class="act"><button onclick="undo()">Undo last ball</button></div>`:'');
  const bw=L.bowler&&(inn.bowling.find(x=>x.id===L.bowler.id)||{wickets:0,runs:0,overs:'0.0'});
  const rules=S.rules||{};
  let h=`${L.opening?`<div class="sec"><span class="lbl">${esc(S.toss)}</span>${rules.last_man||rules.free_hit||rules.max_bowler?`<span class="lbl">Rules: ${[rules.last_man?'last man batting':'',rules.free_hit?'free hit after no-ball':'',rules.max_bowler?'max '+rules.max_bowler+' over'+(rules.max_bowler>1?'s':'')+' per bowler':''].filter(Boolean).join(', ')}</span>`:''}</div>`:''}
    ${L.free_hit&&!L.need?'<div class="fh" role="status"><b>FREE HIT</b> Only a run out counts on this ball.</div>':''}
    <div class="sec"><span class="lbl">Over ${L.over_no}${L.bowler?', bowled by '+esc(L.bowler.name):''}</span>
    <div class="chips">${L.this_over.map(b=>`<span class="chip ${b.k}">${b.t}</span>`).join('')||'<span class="lbl">No balls yet</span>'}</div></div>
    <div class="sec">${bat(L.striker,true,inn)}${L.lone?'<div class="row"><span class="lbl">Last man batting: no partner, strike stays.</span></div>':bat(L.non_striker,false,inn)}
    ${bw?`<div class="row"><span>${esc(L.bowler.name)}</span><span class="n"><b>${bw.wickets}-${bw.runs}</b> (${bw.overs})</span></div>`:''}</div>`;
  if(!SCORER)return h;
  const undoRow=`<div class="act"><button onclick="undo()">Undo last ball</button><button onclick="openShare()">Share</button><button onclick="endMatch()">End match</button></div>`;
  if(L.need)return h+`<div class="hint">${ask(L)}</div>
    ${chooser(L)}${undoRow}`;
  const ex=k=>`<button class="${extra===k?'on':''}" onclick="setX('${k}')">${{wd:'Wd',nb:'Nb',lb:'LB'}[k]}</button>`;
  const ro=`<button class="wbtn ${wtype==='run_out'?'on':''}" onclick="toggleRO()">Run out</button>`;
  const wk=L.free_hit?'':`<button class="wbtn ${pendingW&&wtype!=='run_out'?'on':''}" onclick="toggleW()">Wicket</button>`;
  const x=ex('wd')+ex('nb')+ro+ex('lb')+wk;
  const d=pendingW&&!L.free_hit?`<div class="wk">${DIS.map(([k,t])=>`<button class="${wtype===k?'on':''}" onclick="pickDis('${k}')">${t}</button>`).join('')}</div>`:'';
  const who=wtype==='run_out'?`<div class="wk" style="grid-template-columns:1fr 1fr">${[L.striker,L.non_striker].filter((p,i,a)=>a.findIndex(q=>q.id===p.id)===i).map(p=>`<button class="${(wwho||L.striker.id)===p.id?'on':''}" onclick="setWho(${p.id})">${esc(p.name)} out</button>`).join('')}</div>`:'';
  const endRow=wtype==='run_out'&&!L.lone?`<span class="lbl">Out at which end? Leave unselected to work it out from the runs.</span><div class="wk" style="grid-template-columns:1fr 1fr">${[['striker',"Striker's end"],['non',"Non-striker's end"]].map(([k,t])=>`<button class="${wend===k?'on':''}" onclick="setEnd('${k}')">${t}</button>`).join('')}</div>`:'';
  return h+`<div class="hint">${hint(L)}</div><div class="mods">${x}</div>${d}${who}${endRow}
    <div class="pad">${[0,1,2,3,4,6].map(n=>`<button class="${n>3?'hi':''}" onclick="add(${n})">${n}</button>`).join('')}</div>${undoRow}`;
}
function cardView(){
  return `<span class="lbl" style="margin-top:10px">${esc(S.toss)}</span>`+S.innings.map(i=>`<h2>${esc(i.team)}, innings ${i.number}: ${i.runs}/${i.wickets} (${i.overs} ov)</h2>
   <div class="wrap"><table><tr><th>Batter</th><th>R</th><th>B</th><th>4s</th><th>6s</th><th>SR</th></tr>
   ${i.batting.map(p=>`<tr><td>${esc(p.name)}<small>${esc(p.out||'not out')}</small></td><td><b>${p.runs}</b></td><td>${p.balls}</td><td>${p.fours}</td><td>${p.sixes}</td><td>${p.balls?Math.round(p.runs*100/p.balls):'-'}</td></tr>`).join('')}</table></div>
   ${i.yet_to_bat.length?`<span class="lbl">Yet to bat: ${i.yet_to_bat.map(esc).join(', ')}</span>`:''}
   <div class="wrap"><table><tr><th>Bowler</th><th>O</th><th>R</th><th>W</th><th>Econ</th></tr>
   ${i.bowling.map(p=>`<tr><td>${esc(p.name)}</td><td>${p.overs}</td><td>${p.runs}</td><td><b>${p.wickets}</b></td><td>${p.econ}</td></tr>`).join('')||'<tr><td colspan="5">No overs bowled yet</td></tr>'}</table></div>
   ${i.fow.length?`<span class="lbl">Fall of wickets: ${i.fow.map(f=>`${f.n}-${f.score} (${esc(f.name)}, ${f.over} ov)`).join(', ')}</span>`:''}`).join('');
}

// ---------- the overs tab: charts, over by over, partnerships ----------
function barChart(inn,limit){
  const W=340,H=150,L=26,B=22,T=10, n=Math.max(limit,inn.by_over.length), max=Math.max(6,...inn.by_over.map(o=>o.runs));
  const bw=(W-L-6)/n, y=v=>T+(H-T-B)*(1-v/max);
  const bars=inn.by_over.map(o=>{const x=L+(o.over-1)*bw+bw*0.15,w=bw*0.7;
    return `<rect x="${x.toFixed(1)}" y="${y(o.runs).toFixed(1)}" width="${w.toFixed(1)}" height="${(H-B-y(o.runs)).toFixed(1)}" rx="2" class="cbar"/>`+
      `<text x="${(x+w/2).toFixed(1)}" y="${(y(o.runs)-3).toFixed(1)}" class="clab" text-anchor="middle">${o.runs}</text>`+
      (o.wickets?`<circle cx="${(x+w/2).toFixed(1)}" cy="${(H-B+8).toFixed(1)}" r="3.5" class="cwk"/>`:'')}).join('');
  const ticks=Array.from({length:n},(_,i)=>`<text x="${(L+i*bw+bw/2).toFixed(1)}" y="${H-2}" class="clab" text-anchor="middle">${i+1}</text>`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Runs in each over for ${esc(inn.team)}"><line x1="${L}" y1="${H-B}" x2="${W-4}" y2="${H-B}" class="caxis"/>${bars}${ticks}</svg>`;
}
function wormChart(){
  const W=340,H=170,L=30,B=22,T=10, limit=S.overs_limit;
  const max=Math.max(10,...S.innings.map(i=>i.by_over.length?i.by_over[i.by_over.length-1].total:0));
  const x=o=>L+(W-L-8)*(o/limit), y=v=>T+(H-T-B)*(1-v/max);
  const lines=S.innings.map((inn,k)=>{
    const pts=[[0,0],...inn.by_over.map(o=>[o.over,o.total])];
    const wk=inn.fow.map(f=>{const o=Math.min(limit,Math.ceil(parseFloat(f.over)||0.01));const row=inn.by_over.find(r=>r.over===o);return row?[o,row.total]:null}).filter(Boolean);
    return `<polyline points="${pts.map(p=>x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)).join(' ')}" class="cline c${k}"/>`+
      wk.map(p=>`<circle cx="${x(p[0]).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="3" class="cwk"/>`).join('');
  }).join('');
  const grid=[0,.5,1].map(f=>`<line x1="${L}" x2="${W-6}" y1="${y(max*f).toFixed(1)}" y2="${y(max*f).toFixed(1)}" class="cgrid"/><text x="${L-4}" y="${(y(max*f)+3).toFixed(1)}" class="clab" text-anchor="end">${Math.round(max*f)}</text>`).join('');
  const xt=Array.from({length:limit+1},(_,o)=>o%Math.ceil(limit/6)===0?`<text x="${x(o).toFixed(1)}" y="${H-4}" class="clab" text-anchor="middle">${o}</text>`:'').join('');
  const key=S.innings.map((inn,k)=>`<span class="ckey"><i class="sw c${k}"></i>${esc(inn.team)}</span>`).join('');
  return `<div class="ckeys">${key}<span class="ckey"><i class="dot"></i>wicket</span></div><svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Runs so far, over by over">${grid}${xt}${lines}</svg>`;
}
function oversView(){
  const stale=Q.queue.length?'<span class="lbl">Charts are catching up. They are exact once the offline scores are sent.</span>':'';
  let h=stale+`<h2>Run progress</h2>${wormChart()}`;
  S.innings.forEach(inn=>{
    h+=`<h2>${esc(inn.team)}, innings ${inn.number}</h2>${barChart(inn,S.overs_limit)}
      <div class="ovlist">${inn.by_over.map(o=>`<div class="ovrow"><div class="ovh"><b>Over ${o.over}</b><span>${esc(o.bowler)} · ${o.runs} run${o.runs===1?'':'s'}${o.wickets?' · '+o.wickets+' wkt':''}</span><span class="n">${o.total}</span></div>
        <div class="chips">${o.balls.map(b=>`<span class="chip ${b.k}">${b.t}</span>`).join('')}</div></div>`).join('')||'<span class="lbl">No overs yet</span>'}</div>
      ${inn.partnerships.length?`<h3 class="ah">Partnerships</h3><div class="wrap"><table><tr><th>Batters</th><th>Runs</th><th>Balls</th></tr>${inn.partnerships.map(p=>`<tr><td>${esc(p.a)}${p.b?' &amp; '+esc(p.b):' (alone)'}</td><td><b>${p.runs}</b></td><td>${p.balls}</td></tr>`).join('')}</table></div>`:''}
      ${inn.fow.length?`<span class="lbl">Fall of wickets: ${inn.fow.map(f=>`${f.n}-${f.score} (${esc(f.name)}, ${f.over} ov)`).join(', ')}</span>`:''}`;
  });
  return h;
}

// ---------- sharing: link, WhatsApp, QR, image ----------
const liveLink=()=>location.origin+location.pathname.replace(/[^/]*$/,'')+'match.html?id='+ID+'&mode=live';
function scoreLine(){
  if(!S)return '';
  const parts=S.innings.map(i=>`${i.team} ${i.runs}/${i.wickets} (${i.overs})`).join(', ');
  return S.title+': '+(S.status==='completed'&&S.result?parts+'. '+S.result+'.':parts+'.');
}
function paintShare(){
  if(!S)return;
  const link=liveLink();
  $('wa').href='https://wa.me/?text='+encodeURIComponent(scoreLine()+' Follow live: '+link);
  if(!$('qr').dataset.link||$('qr').dataset.link!==link){
    $('qr').dataset.link=link;
    try{const q=qrcode(0,'M');q.addData(link);q.make();$('qr').innerHTML=q.createSvgTag({cellSize:4,margin:2,scalable:true})}catch(e){$('qr').textContent=''}
  }
}
$('cp').onclick=async()=>{
  try{await navigator.clipboard.writeText(liveLink());msg='Live link copied. Anyone with it can follow the score.'}
  catch(e){msg='Copy this link: '+liveLink()}
  render();
};
function trunc(ctx,t,w){t=String(t);while(t.length>1&&ctx.measureText(t).width>w)t=t.slice(0,-2)+'\u2026';return t}
function drawCard(){
  const W=1080, pad=64, inns=S.innings, rows=[];
  const bats=i=>[...i.batting].filter(b=>b.balls||b.runs).sort((a,b)=>b.runs-a.runs||a.balls-b.balls).slice(0,3);
  const bowls=i=>[...i.bowling].sort((a,b)=>b.wickets-a.wickets||a.runs-b.runs).slice(0,2);
  let H=pad+186+110;
  inns.forEach(i=>{H+=198+bats(i).length*52+bowls(i).length*52});
  H+=S.potm&&S.status==='completed'?130:0;
  const c=document.createElement('canvas');c.width=W;c.height=H;const x=c.getContext('2d');
  const F='Archivo, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  x.fillStyle='#0e1a2b';x.fillRect(0,0,W,H);
  x.fillStyle='#16263d';x.fillRect(24,24,W-48,H-48);
  x.fillStyle='#c8102e';x.beginPath();x.arc(pad+12,pad+8,12,0,7);x.fill();
  x.fillStyle='#8aa0bd';x.font='700 26px '+F;x.textBaseline='alphabetic';x.fillText('THE CREASE',pad+36,pad+17);
  let y=pad+100;
  x.fillStyle='#f4f7fb';x.font='800 58px '+F;x.fillText(trunc(x,S.title,W-2*pad),pad,y);
  y+=56;x.fillStyle='#f2c94c';x.font='700 38px '+F;
  const head=S.status==='completed'&&S.result?S.result:(S.live&&S.live.target?`${inns[inns.length-1].team} need ${S.live.runs_needed} from ${S.live.balls_left} balls`:'Match in progress');
  x.fillText(trunc(x,head,W-2*pad),pad,y);y+=30;
  inns.forEach(i=>{
    y+=34;x.strokeStyle='#2a3d5a';x.lineWidth=2;x.beginPath();x.moveTo(pad,y);x.lineTo(W-pad,y);x.stroke();y+=76;
    x.fillStyle='#8aa0bd';x.font='700 30px '+F;x.fillText(trunc(x,i.team.toUpperCase(),520),pad,y-48);
    x.fillStyle='#f4f7fb';x.font='800 84px '+F;const sc=`${i.runs}/${i.wickets}`;x.fillText(sc,pad,y+30);
    const w=x.measureText(sc).width;x.fillStyle='#8aa0bd';x.font='600 34px '+F;x.fillText(`${i.overs} ov`,pad+w+22,y+30);
    y+=88;
    bats(i).forEach(b=>{x.fillStyle='#f4f7fb';x.font='700 34px '+F;x.fillText(trunc(x,b.name,540),pad,y);
      x.textAlign='right';x.font='800 34px '+F;x.fillText(`${b.runs}${b.out?'':'*'} (${b.balls})`,W-pad,y);x.textAlign='left';y+=52});
    bowls(i).forEach(b=>{x.fillStyle='#b9c7db';x.font='600 32px '+F;x.fillText(trunc(x,b.name+' (bowling)',540),pad,y);
      x.textAlign='right';x.fillText(`${b.wickets}/${b.runs} (${b.overs})`,W-pad,y);x.textAlign='left';y+=52});
  });
  if(S.potm&&S.status==='completed'){
    y+=26;x.fillStyle='#1f3454';x.fillRect(pad,y,W-2*pad,104);
    x.fillStyle='#f2c94c';x.font='700 24px '+F;x.fillText('PLAYER OF THE MATCH',pad+24,y+36);
    x.fillStyle='#f4f7fb';x.font='800 38px '+F;x.fillText(trunc(x,S.potm.name+(S.potm.line?'  \u00b7  '+S.potm.line:''),W-2*pad-48),pad+24,y+80);y+=104;
  }
  x.fillStyle='#8aa0bd';x.font='600 26px '+F;x.fillText('Scored live on The Crease',pad,H-pad+4);
  return c;
}
$('img').onclick=async()=>{
  if(!S)return;
  try{
    const c=drawCard(), blob=await new Promise(r=>c.toBlob(r,'image/png'));
    const url=URL.createObjectURL(blob);
    $('cardimg').src=url;$('cardsave').href=url;$('cardout').hidden=false;
    const file=new File([blob],'scorecard.png',{type:'image/png'});
    if(navigator.canShare&&navigator.canShare({files:[file]}))await navigator.share({files:[file],title:S.title,text:scoreLine()+' '+liveLink()});
  }catch(e){if(e&&e.name!=='AbortError'){msg='Could not make the image on this device.';render()}}
};

// ---------- celebrations ----------
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
function syncBar(){
  if(Q.err)return `<span class="err">Some offline scores could not be saved: ${esc(Q.err)}</span> <button class="pill" onclick="retrySync()">Try again</button> <button class="pill" onclick="useServer()">Use the server's version</button>`;
  if(Q.queue.length)return Q.syncing?`Sending ${Q.queue.length} offline ${Q.queue.length===1?'score':'scores'}…`:
    `Offline. ${Q.queue.length} ${Q.queue.length===1?'score is':'scores are'} saved on this phone and will send when you are back online.`;
  if(!Q.online)return SCORER?'No connection. You can keep scoring and it will send later.':'No connection. Showing the last score. Trying again…';
  if(!SCORER&&S&&S.status==='live'&&Q.stamp)return `Live · updated ${Math.max(0,Math.round((Date.now()-Q.stamp)/1000))}s ago`;
  return '';
}
function render(){
  if(!S)return;
  watchBall();
  const inn=S.innings[S.innings.length-1], L=S.live;
  $('title').textContent=S.title; $('sub').textContent='Innings '+inn.number+', '+S.overs_limit+' overs';
  const sb=$('sync'),t=syncBar();sb.innerHTML=t;sb.className='sync'+(t?(Q.err?' bad':(Q.queue.length||!Q.online?' warn':' ok')):'');
  $('hero').innerHTML=`<div class="score">${inn.runs}<i>/${inn.wickets}</i></div>
    <div class="meta"><b>${inn.overs}</b>of ${S.overs_limit} overs<br>Run rate ${inn.run_rate.toFixed(2)}</div>`;
  $('chase').innerHTML=esc(L&&L.target?`${inn.team} need ${L.runs_needed} from ${L.balls_left} balls (target ${L.target})`:
    (S.status==='completed'?S.result:inn.team+' batting'));
  ['score','card','overs'].forEach(t=>$('t-'+t).setAttribute('aria-selected',view===t));
  $('view').innerHTML=(view==='score'?scoreView(inn):view==='card'?cardView():oversView())+(msg?`<p class="${/^(Live|All offline)/.test(msg)?'hint':'err'}" role="alert">${msg}</p>`:'');
  paintShare();
}
loadQ();
if(Q.base){S=null;recompute();render()}
load();
if(!SCORER){
  setInterval(()=>{if(document.hidden)return;if(S&&S.status==='completed'&&Q.online)return;load()},4000);
  setInterval(()=>{if(S&&S.status==='live')render()},1000);          // keeps the "updated Ns ago" text honest
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load()});
}
