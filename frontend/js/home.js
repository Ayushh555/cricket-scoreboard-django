(async()=>{
  const m=(await (await fetch(API_BASE+'/api/matches/')).json()).slice(0,1);   // only the current (newest) match is shown
  const live=m.find(x=>x.status==='live'), nb=document.querySelector('.top .btn');
  if(live&&nb)nb.hidden=true;   // only one match at a time: resume or end it first
  document.getElementById('matches').innerHTML=m.length?m.map((x,i)=>`<a class="mrow" style="--i:${Math.min(i,12)}" href="match.html?id=${x.id}&mode=${x.status==='live'?'score':'live'}">
    <b>${x.title}</b> ${x.status==='live'?'<span class="live-dot">LIVE</span>':''}
    <small>${x.scores.join('  |  ')||'Not started'}</small><small>${x.result||x.date}</small></a>`).join(''):'<span class="lbl">No match yet. Start one!</span>';
  if(live){const bar=document.createElement('div');bar.className='livebar';
    bar.innerHTML='<a class="btn" href="match.html?id='+live.id+'&mode=score">Resume match</a>';
    bar.appendChild(endButton(live.id,()=>location.reload()));
    document.getElementById('matches').after(bar)}
  const s=await (await fetch(API_BASE+'/api/stats/')).json();
  document.getElementById('bat').innerHTML='<tr><th>Player</th><th>Runs</th><th>Balls</th><th>4s</th><th>6s</th><th>SR</th></tr>'+
    s.batting.map(p=>`<tr><td>${p.name}<small>${p.team}</small></td><td><b>${p.runs}</b></td><td>${p.balls}</td><td>${p.fours}</td><td>${p.sixes}</td><td>${p.sr}</td></tr>`).join('');
  document.getElementById('bowl').innerHTML='<tr><th>Player</th><th>Wkts</th><th>Overs</th><th>Runs</th><th>Econ</th></tr>'+
    s.bowling.map(p=>`<tr><td>${p.name}<small>${p.team}</small></td><td><b>${p.wickets}</b></td><td>${p.overs}</td><td>${p.runs}</td><td>${p.econ}</td></tr>`).join('');
})();
