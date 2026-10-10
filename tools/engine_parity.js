// Replays server-recorded scoring sequences through the offline engine and compares every field the UI shows.
const fs = require('fs'), Engine = require('../frontend/js/engine.js');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let checked = 0, problems = [];
const ids = a => (a || []).map(x => x.id);
const near = (a, b, t) => Math.abs(a - b) <= t;
function cmp(where, ours, theirs) {
  const bad = (what, x, y) => problems.push(`${where}: ${what}\n   engine: ${JSON.stringify(x)}\n   server: ${JSON.stringify(y)}`);
  const eq = (what, x, y) => { if (JSON.stringify(x) !== JSON.stringify(y)) bad(what, x, y); };
  const i1 = ours.innings[ours.live.innings - 1], i2 = theirs.innings[ours.live.innings - 1];
  eq('runs', i1.runs, i2.runs); eq('wickets', i1.wickets, i2.wickets); eq('overs', i1.overs, i2.overs);
  if (!near(i1.run_rate, i2.run_rate, 0.011)) bad('run_rate', i1.run_rate, i2.run_rate);
  eq('batting', i1.batting.map(b => [b.id, b.runs, b.balls, b.fours, b.sixes, b.out]), i2.batting.map(b => [b.id, b.runs, b.balls, b.fours, b.sixes, b.out]));
  eq('bowling', i1.bowling.map(b => [b.id, b.overs, b.runs, b.wickets]), i2.bowling.map(b => [b.id, b.overs, b.runs, b.wickets]));
  i1.bowling.forEach((b, k) => { if (!near(b.econ, i2.bowling[k].econ, 0.11)) bad('econ', b.econ, i2.bowling[k].econ); });
  eq('yet_to_bat', i1.yet_to_bat, i2.yet_to_bat);
  eq('by_over', i1.by_over, i2.by_over); eq('fow', i1.fow, i2.fow); eq('partnerships', i1.partnerships, i2.partnerships);
  if (theirs.live && theirs.live.innings === ours.live.innings) {
    const a = ours.live, b = theirs.live;
    eq('striker', a.striker && a.striker.id, b.striker && b.striker.id);
    eq('non_striker', a.non_striker && a.non_striker.id, b.non_striker && b.non_striker.id);
    eq('bowler', a.bowler && a.bowler.id, b.bowler && b.bowler.id);
    eq('need', a.need, b.need); eq('options', ids(a.options), ids(b.options));
    eq('this_over', a.this_over, b.this_over); eq('over_no', a.over_no, b.over_no); eq('opening', a.opening, b.opening);
    eq('balls_left', a.balls_left, b.balls_left); eq('lone', a.lone, b.lone); eq('free_hit', a.free_hit, b.free_hit);
    eq('last_bowler', a.last_bowler, b.last_bowler); eq('target', a.target, b.target); eq('runs_needed', a.runs_needed, b.runs_needed);
  }
  checked++;
}
for (const sc of data) {
  let S = JSON.parse(JSON.stringify(sc.initial));
  sc.steps.forEach((st, k) => {
    const where = `${sc.name} step ${k} ${JSON.stringify(st.action)}`;
    const r = Engine.apply(S, st.action);
    if (st.error) { if (!r.error) problems.push(`${where}: server rejected (${st.error}) but engine accepted`); return; }
    if (r.error) { problems.push(`${where}: engine rejected (${r.error}) but server accepted`); S = null; return; }
    S = r.S;
    if (S._offlineEnd) {                       // the innings ended: totals must still agree, then stop
      const i1 = S.innings[S.live.innings - 1], i2 = st.state.innings[S.live.innings - 1];
      if (i1.runs !== i2.runs || i1.wickets !== i2.wickets || i1.overs !== i2.overs) problems.push(`${where}: end-of-innings totals differ`);
      checked++; S = null; return;
    }
    cmp(where, S, st.state);
  });
}
console.log(`compared ${checked} states in ${data.length} matches; ${problems.length} differences`);
if (problems.length) { console.log(problems.slice(0, 6).join('\n')); process.exit(1); }
