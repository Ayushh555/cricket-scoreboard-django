(async()=>{
  try{
    const s=await (await fetch(API_BASE+'/api/stats/')).json();
    const none=n=>`<tr><td colspan="${n}">No balls scored yet</td></tr>`;
    document.getElementById('bat').innerHTML='<tr><th>Player</th><th>Runs</th><th>Balls</th><th>4s</th><th>6s</th><th>SR</th></tr>'+
      (s.batting.map(p=>`<tr><td>${esc(p.name)}<small>${esc(p.team)}</small></td><td><b>${p.runs}</b></td><td>${p.balls}</td><td>${p.fours}</td><td>${p.sixes}</td><td>${p.sr}</td></tr>`).join('')||none(6));
    document.getElementById('bowl').innerHTML='<tr><th>Player</th><th>Wkts</th><th>Overs</th><th>Runs</th><th>Econ</th></tr>'+
      (s.bowling.map(p=>`<tr><td>${esc(p.name)}<small>${esc(p.team)}</small></td><td><b>${p.wickets}</b></td><td>${p.overs}</td><td>${p.runs}</td><td>${p.econ}</td></tr>`).join('')||none(5));
  }catch(e){document.getElementById('bat').innerHTML='<tr><td class="err">Can\'t reach the scoring server.</td></tr>'}
})();
