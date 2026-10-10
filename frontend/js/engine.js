// Offline scoring engine. It mirrors the server's rules (scoring/services.py) so a scorer with no signal can keep going.
// The server stays the source of truth: queued actions are replayed there, and the app shows the server's version after.
const Engine = (() => {
  const BAT_RANK = {batter: 0, allrounder: 1, bowler: 2}, BOWL_RANK = {bowler: 0, allrounder: 1, batter: 2};
  const WK = {bowled: 'bowled', caught: 'caught', lbw: 'lbw', run_out: 'run out', stumped: 'stumped', hit_wicket: 'hit wicket'};
  const clone = o => JSON.parse(JSON.stringify(o));
  const legalOf = s => { const [o, b] = String(s).split('.').map(Number); return o * 6 + b; };
  const ovs = n => `${Math.floor(n / 6)}.${n % 6}`;
  const fail = (error, code = 'invalid') => ({error, code});

  function label(bat, extra, xr, wicket) {
    if (wicket) return {t: 'W', k: 'w'};
    if (extra === 'wd') return {t: 'Wd' + (xr > 1 ? '+' + (xr - 1) : ''), k: 'x'};
    if (extra === 'nb') return {t: 'Nb' + (bat ? '+' + bat : ''), k: 'x'};
    if (extra === 'b' || extra === 'lb') return {t: extra.toUpperCase() + xr, k: 'x'};
    return {t: String(bat), k: bat >= 4 ? 'f' : bat === 0 ? 'z' : ''};
  }
  const maxWickets = (S, n) => S.rules.last_man ? n : Math.max(n - 1, 1);
  const person = (S, id) => { const L = S.live; return id == null ? null : (L.roster.bat.concat(L.roster.bowl).find(p => p.id === id) || null); };

  function usedBatters(inn, L) {
    const u = new Set(inn.batting.map(b => b.id));
    if (L.striker) u.add(L.striker.id);
    if (L.non_striker) u.add(L.non_striker.id);
    return u;
  }
  function bowlerLegal(inn, id) { const b = inn.bowling.find(x => x.id === id); return b ? legalOf(b.overs) : 0; }
  const capped = (S, inn, id) => S.rules.max_bowler > 0 && bowlerLegal(inn, id) >= S.rules.max_bowler * 6;

  // Recompute who is needed and the choices, exactly like the server's _live().
  function refresh(S) {
    const L = S.live, inn = S.innings[L.innings - 1], legal = legalOf(inn.overs);
    L.need = !(L.striker && L.non_striker) ? 'batter' : !L.bowler ? 'bowler' : null;
    L.options = [];
    if (L.need === 'batter') {
      const used = usedBatters(inn, L);
      L.options = L.roster.bat.filter(p => !used.has(p.id)).sort((a, b) => BAT_RANK[a.role] - BAT_RANK[b.role]);
    } else if (L.need === 'bowler') {
      const pool = L.roster.bowl.filter(p => p.id !== L.last_bowler && !capped(S, inn, p.id));
      const pref = pool.filter(p => p.role !== 'batter');
      L.options = (pref.length ? pref : pool).slice().sort((a, b) => BOWL_RANK[a.role] - BOWL_RANK[b.role]);
    }
    const overIdx = L.need === 'bowler' && legal ? Math.floor(legal / 6) - 1 : Math.floor(legal / 6);
    const row = inn.by_over.find(o => o.over === overIdx + 1);
    L.this_over = row ? row.balls.map(b => ({t: b.t, k: b.k})) : [];
    L.over_no = overIdx + 1;
    L.opening = inn.by_over.length === 0;
    L.balls_left = S.overs_limit * 6 - legal;
    L.lone = !!L.striker && !!L.non_striker && L.striker.id === L.non_striker.id;
    L.free_hit = S.rules.free_hit && !!L._fh;
    if (L.innings === 2) { L.target = S.innings[0].runs + 1; L.runs_needed = Math.max(L.target - inn.runs, 0); }
  }
  function ensureBat(inn, p) {
    if (p && !inn.batting.some(b => b.id === p.id)) inn.batting.push({id: p.id, name: p.name, runs: 0, balls: 0, fours: 0, sixes: 0, out: ''});
  }
  function tidy(S) {                                  // yet-to-bat and run rate follow from the rest
    const L = S.live, inn = S.innings[L.innings - 1], legal = legalOf(inn.overs);
    inn.yet_to_bat = L.roster.bat.filter(p => !inn.batting.some(b => b.id === p.id)).map(p => p.name);
    inn.run_rate = legal ? Math.round(inn.runs * 600 / legal) / 100 : 0;
    const bowl = inn.bowling; bowl.forEach(w => { const l = legalOf(w.overs); w.econ = l ? Math.round(w.runs * 60 / l) / 10 : 0; });
  }

  function ball(S, a) {
    const L = S.live, inn = S.innings[L.innings - 1];
    if (!(L.striker && L.non_striker)) return fail('Choose the next batter first.', 'need_batter');
    if (!L.bowler) return fail('Choose the bowler first.', 'need_bowler');
    const runs = parseInt(a.runs || 0, 10), extra = a.extra || '', wicket = a.wicket || '', end = a.end || '';
    if (!(runs >= 0 && runs <= 7)) return fail('Runs must be between 0 and 7.');
    if (!['', 'wd', 'nb', 'b', 'lb'].includes(extra)) return fail('Unknown extra.');
    if (wicket && !WK[wicket]) return fail('Unknown dismissal.');
    if (!['', 'striker', 'non'].includes(end)) return fail('Unknown end.');
    if (wicket && wicket !== 'run_out' && S.rules.free_hit && L._fh) return fail('Free hit: only a run out counts on this ball.', 'free_hit');
    const legalBefore = legalOf(inn.overs), legal = !(extra === 'wd' || extra === 'nb');
    let s = L.striker, n = L.non_striker, bowler = L.bowler;
    let bat = 0, xr = 0;
    if (extra === 'wd') xr = 1 + runs; else if (extra === 'nb') { xr = 1; bat = runs; } else if (extra === 'b' || extra === 'lb') xr = runs; else bat = runs;
    let out = null;
    if (wicket) {
      const allowed = {wd: ['stumped', 'run_out', 'hit_wicket'], nb: ['run_out']}[extra];
      if (allowed && !allowed.includes(wicket)) return fail("That dismissal isn't possible off this delivery.");
      out = s;
      if (wicket === 'run_out' && (a.dismissed === s.id || a.dismissed === n.id)) out = a.dismissed === s.id ? s : n;
    }
    // scorecard
    ensureBat(inn, s); ensureBat(inn, n);
    const br = inn.batting.find(b => b.id === s.id);
    br.runs += bat; br.balls += extra !== 'wd' ? 1 : 0; br.fours += bat === 4 ? 1 : 0; br.sixes += bat === 6 ? 1 : 0;
    let wr = inn.bowling.find(w => w.id === bowler.id);
    if (!wr) { wr = {id: bowler.id, name: bowler.name, overs: '0.0', runs: 0, wickets: 0, econ: 0}; inn.bowling.push(wr); }
    wr.runs += bat + ((extra === 'wd' || extra === 'nb') ? xr : 0);
    wr.overs = ovs(legalOf(wr.overs) + (legal ? 1 : 0));
    if (wicket) {
      let how = WK[wicket];
      if (wicket !== 'run_out') { wr.wickets += 1; how += ' b ' + bowler.name; }
      inn.batting.find(b => b.id === out.id).out = how;
    }
    inn.runs += bat + xr; if (wicket) inn.wickets += 1;
    inn.overs = ovs(legalBefore + (legal ? 1 : 0));
    // over-by-over, fall of wickets, partnerships
    const overNo = Math.floor(legalBefore / 6) + 1;
    let row = inn.by_over.find(o => o.over === overNo);
    if (!row) { const prev = inn.by_over[inn.by_over.length - 1]; row = {over: overNo, runs: 0, wickets: 0, bowler: bowler.name, balls: [], total: prev ? prev.total : 0}; inn.by_over.push(row); }
    row.runs += bat + xr; row.total += bat + xr; row.wickets += wicket ? 1 : 0; row.balls.push(label(bat, extra, xr, wicket));
    const key = [s.id, n.id].filter((v, i, arr) => arr.indexOf(v) === i).sort((x, y) => x - y).join('-');
    let part = inn.partnerships[inn.partnerships.length - 1];
    if (!part || part.k !== key) { part = {a: s.name, b: n.id !== s.id ? n.name : '', runs: 0, balls: 0, k: key}; inn.partnerships.push(part); }
    part.runs += bat + xr; part.balls += legal ? 1 : 0;
    if (wicket) inn.fow.push({n: inn.fow.length + 1, score: inn.runs, name: out.name, over: ovs(legalBefore + (legal ? 1 : 0))});
    // who is at the crease now
    const wasLone = s.id === n.id;
    if (wasLone) { if (out) { s = n = null; } }
    else if (wicket === 'run_out') {
      let e = end;
      if (!e) e = ((out.id === s.id) === (runs % 2 === 0)) ? 'non' : 'striker';
      const survivor = out.id === s.id ? n : s;
      if (e === 'striker') { s = null; n = survivor; } else { s = survivor; n = null; }
    } else {
      if (out) { if (out.id === s.id) { s = null; } else { n = null; } }
      if (runs % 2) { const t = s; s = n; n = t; }
    }
    if (S.rules.last_man && (s === null) !== (n === null)) {
      const used = usedBatters(inn, {striker: s, non_striker: n});
      if (!L.roster.bat.some(p => !used.has(p.id))) { const one = s || n; s = n = one; }
    }
    let lastBowler = L.last_bowler;
    if (legal && (legalBefore + 1) % 6 === 0) { const t = s; s = n; n = t; lastBowler = bowler.id; bowler = null; }
    L.striker = s && person(S, s.id); L.non_striker = n && person(S, n.id); L.bowler = bowler && person(S, bowler.id);
    L.last_bowler = lastBowler;
    L._fh = extra === 'nb' || (L._fh && extra === 'wd');
    // does the innings end here?
    const legalNow = legalBefore + (legal ? 1 : 0);
    const chased = L.innings === 2 && inn.runs > S.innings[0].runs;
    if (legalNow >= S.overs_limit * 6 || inn.wickets >= maxWickets(S, L.roster.bat.length) || chased) {
      S._offlineEnd = true; tidy(S); return {S};
    }
    refresh(S); tidy(S);
    S.last_ball = {id: (S.last_ball ? S.last_ball.id : 0) + 1, runs: bat, wicket: !!wicket};
    return {S};
  }

  function select(S, a) {
    const L = S.live, inn = S.innings[L.innings - 1];
    if (a.role === 'batter') {
      if (L.striker && L.non_striker) return fail('No new batter is needed right now.');
      const p = L.roster.bat.find(x => x.id === a.player);
      if (!p || usedBatters(inn, L).has(p.id)) return fail("That player can't bat now.");
      if (!L.striker) L.striker = p; else L.non_striker = p;
      ensureBat(inn, p);
    } else if (a.role === 'bowler') {
      if (L.bowler) return fail('A bowler is already chosen.');
      const p = L.roster.bowl.find(x => x.id === a.player);
      if (!p) return fail("That player isn't in the bowling team.");
      if (p.id === L.last_bowler) return fail("A bowler can't bowl two overs in a row.");
      if (capped(S, inn, p.id)) return fail(p.name + ' has bowled the maximum ' + S.rules.max_bowler + ' overs.');
      L.bowler = p;
    } else return fail('Unknown role.');
    refresh(S); tidy(S);
    return {S};
  }

  // Apply one queued action to a copy of the state. Returns {S} or {error, code}.
  function apply(S, action) {
    const T = clone(S);
    if (!T.live || T._offlineEnd) return fail('This innings is over. Connect to continue.', 'offline_end');
    T.live._fh = T.live._fh !== undefined ? T.live._fh : !!T.live.free_hit;
    return action.type === 'ball' ? ball(T, action) : action.type === 'select' ? select(T, action) : fail('Unknown action.');
  }
  // Replay the whole queue on the last server state. Stops at the first action that can't apply.
  function replay(base, queue) {
    let S = clone(base), applied = 0;
    for (const a of queue) { const r = apply(S, a); if (r.error) return {S, applied, error: r.error}; S = r.S; applied++; }
    return {S, applied};
  }
  return {apply, replay};
})();
if (typeof module !== 'undefined') module.exports = Engine;
