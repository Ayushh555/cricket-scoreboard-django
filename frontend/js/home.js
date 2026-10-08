document.documentElement.classList.add('js');
(()=>{
  const $=id=>document.getElementById(id);
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const get=u=>fetch(API_BASE+u).then(r=>{if(!r.ok)throw new Error(r.status);return r.json()});
  let A={authenticated:false}, lastBoard='', lastScore=null, lastMatch=null, lastRecent='', perfTab='runs', stats=null;

  // ---------- small helpers ----------
  const io='IntersectionObserver' in window?new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.08}):null;
  const reveal=()=>document.querySelectorAll('.rv:not(.in)').forEach(el=>io?io.observe(el):el.classList.add('in'));
  function countTo(el,to){
    const from=+el.dataset.v||0; el.dataset.v=to;
    if(reduce||from===to){el.textContent=to;return}
    const t0=performance.now();
    const step=t=>{const k=Math.min((t-t0)/800,1);el.textContent=Math.round(from+(to-from)*(1-Math.pow(1-k,3)));if(k<1)requestAnimationFrame(step)};
    requestAnimationFrame(step);
  }

  // ---------- live scoreboard (refreshes itself) ----------
  function renderHero(ms,live,s){
    let h='';
    if(s){
      const inn=s.innings[s.innings.length-1], L=s.live;
      const line=L&&L.need?'Waiting for '+(L.need==='bowler'?'the bowler':'a batter'):
        L&&L.target?`${esc(inn.team)} need ${L.runs_needed} from ${L.balls_left} balls`:esc(inn.team)+' batting';
      h=`<section class="board" aria-label="Live match">
        <div class="bhead"><span class="pulse"></span>LIVE<span class="bsub">Innings ${inn.number}, ${s.overs_limit} overs</span></div>
        <div class="bteams">${esc(s.title)}</div>
        <div class="bscore"><span class="n" id="bn">${inn.runs}</span><span class="w">/${inn.wickets}</span><span class="ov">${inn.overs} ov<br>RR ${inn.run_rate.toFixed(2)}</span></div>
        <div class="bline">${line}</div>
        <div class="bact">${A.authenticated?`<a class="bbtn" href="match.html?id=${s.id}&mode=score">Continue scoring</a><a class="blink" href="match.html?id=${s.id}&mode=live">Watch view</a>`:`<a class="bbtn" href="match.html?id=${s.id}&mode=live">Watch live</a>`}</div>
        ${live.length>1?`<a class="more" href="history.html">+ ${live.length-1} more live ${live.length-1===1?'match':'matches'}</a>`:''}
      </section>${A.authenticated?`<button class="big end" type="button" id="endlive" data-id="${s.id}" data-title="${esc(s.title)}"><b>End this match</b><small>Only one match can run at a time. End it to start a new one.</small></button>`:''}`;
    }else{
      h=A.authenticated?`<a class="big primary" href="new.html"><b>New match</b><small>Pick teams, toss and start scoring</small></a>`:
        `<a class="big primary" href="login.html"><b>Sign in to score</b><small>Only the scorer can start and score matches. Anyone can watch.</small></a>`;
      if(!ms.length)h+=`<section class="steps rv"><h2>How it works</h2><ol>
        <li><b>Add two teams.</b> Name up to 11 players each and mark them batter, bowler or all-rounder.</li>
        <li><b>Do the toss.</b> Choose the overs, who won and what they chose.</li>
        <li><b>Score every ball.</b> Share the live link so everyone can follow along.</li></ol></section>`;
    }
    if(h!==lastBoard){$('hero').innerHTML=h;lastBoard=h}
    if(s){
      const inn=s.innings[s.innings.length-1], key=inn.runs+'/'+inn.wickets;
      if(lastMatch===s.id&&lastScore!==null&&lastScore!==key){const n=$('bn');n.classList.remove('tick');void n.offsetWidth;n.classList.add('tick')}
      lastScore=key;lastMatch=s.id;
    }else{lastScore=null;lastMatch=null}
  }

  $('hero').addEventListener('click',async e=>{
    const b=e.target.closest('#endlive'); if(!b)return;
    if(!confirm('End "'+b.dataset.title+'" now? The result is worked out from the current score.'))return;
    const r=await fetch(API_BASE+'/api/matches/'+b.dataset.id+'/end/',{method:'POST'});
    if(r.ok)load(); else alert('Could not end the match.');
  });

  // ---------- numbers ----------
  function renderNumbers(ms,t){
    if(!ms.length){$('numbers').innerHTML='';return}
    if(!$('numbers').firstChild)$('numbers').innerHTML=`<div class="numbers rv">${['Matches','Runs','Wickets','Sixes'].map(k=>`<div><b data-k="${k}">0</b><small>${k}</small></div>`).join('')}</div>`;
    const v={Matches:t.matches,Runs:t.runs,Wickets:t.wickets,Sixes:t.sixes};
    document.querySelectorAll('#numbers b').forEach(b=>countTo(b,v[b.dataset.k]));
  }

  // ---------- recent results (tap to expand) ----------
  function renderRecent(done){
    const key=done.slice(0,3).map(x=>x.id+x.result).join('|');
    if(key===lastRecent)return; lastRecent=key;
    $('recent').innerHTML=done.length?`<div class="sech rv"><h2>Recent results</h2><a href="history.html">All</a></div>`+
      done.slice(0,3).map(x=>`<div class="acc rv" data-id="${x.id}"><button class="accbtn" type="button" aria-expanded="false">
        <b>${esc(x.result)}</b><small>${esc(x.title)}, ${esc(x.date)}</small><small>${x.scores.map(esc).join('  |  ')}</small><span class="chev" aria-hidden="true"></span></button>
        <div class="accbody"><div class="accin" aria-live="polite"></div></div></div>`).join(''):'';
    reveal();
  }
  function mini(s){
    return s.innings.map(i=>{
      const b=[...i.batting].sort((a,c)=>c.runs-a.runs)[0], w=[...i.bowling].sort((a,c)=>c.wickets-a.wickets||a.runs-c.runs)[0];
      return `<div class="mini"><div class="mrw"><b>${esc(i.team)}</b><b>${i.runs}/${i.wickets} (${i.overs})</b></div>
        ${b?`<div class="mrw"><span>Top bat: ${esc(b.name)}</span><span>${b.runs} (${b.balls})</span></div>`:''}
        ${w&&w.overs!=='0.0'?`<div class="mrw"><span>Top bowl: ${esc(w.name)}</span><span>${w.wickets}-${w.runs} (${w.overs})</span></div>`:''}</div>`}).join('')+
      `<a class="fulllink" href="match.html?id=${s.id}&mode=live">Full scorecard</a>`;
  }
  $('recent').addEventListener('click',async e=>{
    const btn=e.target.closest('.accbtn'); if(!btn)return;
    const acc=btn.parentElement, open=!acc.classList.contains('open');
    acc.classList.toggle('open',open); btn.setAttribute('aria-expanded',open);
    const inn=acc.querySelector('.accin');
    if(open&&!inn.dataset.loaded){
      inn.textContent='Loading...';
      try{inn.innerHTML=mini(await get('/api/matches/'+acc.dataset.id+'/'));inn.dataset.loaded=1}catch(x){inn.textContent="Couldn't load this match."}
    }
  });

  // ---------- top performers (switch Runs / Wickets) ----------
  function renderPerf(){
    if(!stats)return;
    const bat=stats.batting.filter(p=>p.runs>0).slice(0,3), bowl=stats.bowling.filter(p=>p.wickets>0).slice(0,3);
    if(!bat.length&&!bowl.length){$('perf').innerHTML='';return}
    const rows=(list,val,fmt)=>list.length?list.map((p,i)=>`<li><span class="rk">${i+1}</span><span class="nm">${esc(p.name)}<small>${esc(p.team)}</small></span>
      <span class="vl">${fmt(p)}</span><i class="bar"><u data-w="${Math.round(val(p)*100/val(list[0]))}"></u></i></li>`).join(''):'<li class="none">Nothing here yet</li>';
    $('perf').innerHTML=`<div class="sech rv"><h2>Top performers</h2><a href="stats.html">All stats</a></div>
      <div class="seg rv" role="tablist" aria-label="Leaderboard">
        <button role="tab" data-t="runs" aria-selected="${perfTab==='runs'}">Runs</button>
        <button role="tab" data-t="wkts" aria-selected="${perfTab==='wkts'}">Wickets</button></div>
      <ol class="lb rv">${perfTab==='runs'?rows(bat,p=>p.runs,p=>`<b>${p.runs}</b> runs`):rows(bowl,p=>p.wickets,p=>`<b>${p.wickets}</b> wkts`)}</ol>`;
    reveal();
    requestAnimationFrame(()=>requestAnimationFrame(()=>document.querySelectorAll('#perf .bar u').forEach(u=>u.style.width=u.dataset.w+'%')));
  }
  $('perf').addEventListener('click',e=>{const b=e.target.closest('.seg button');if(b&&b.dataset.t!==perfTab){perfTab=b.dataset.t;renderPerf()}});

  // ---------- theme ----------
  $('theme').addEventListener('click',()=>{
    const t=document.documentElement.dataset.theme==='dark'?'light':'dark';
    document.documentElement.dataset.theme=t;
    try{localStorage.setItem('crease-theme',t)}catch(e){}
  });

  // ---------- load + auto refresh ----------
  async function load(){
    try{
      A=await requireLogin();
      const [ms,st]=await Promise.all([get('/api/matches/'),get('/api/stats/')]);
      const live=ms.filter(m=>m.status==='live');
      const s=live.length?await get('/api/matches/'+live[0].id+'/'):null;
      $('srv').textContent=''; stats=st;
      renderHero(ms,live,s); renderNumbers(ms,st.totals); renderRecent(ms.filter(m=>m.status==='completed')); renderPerf(); reveal();
    }catch(e){
      $('srv').textContent="Can't reach the scoring server. Start it with: python manage.py runserver";
      if(!lastBoard){$('hero').innerHTML=`<a class="big primary" href="new.html"><b>New match</b><small>Pick teams, toss and start scoring</small></a>`;lastBoard='x'}
    }
  }
  load();
  setInterval(()=>{if(!document.hidden)load()},5000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load()});
  reveal();
})();
