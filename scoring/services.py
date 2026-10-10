"""Game rules. Views stay thin; everything about cricket lives here."""
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from .models import Ball, Innings, Match, Player, Team

E = Ball.Extra
WD, NB, BYE, LB = E.WIDE, E.NO_BALL, E.BYE, E.LEG_BYE
ILLEGAL = (WD, NB)


BAT_RANK = {"batter": 0, "allrounder": 1, "bowler": 2}   # who bats first
BOWL_RANK = {"bowler": 0, "allrounder": 1, "batter": 2}   # who bowls first


class RuleError(Exception):
    def __init__(self, message, code="invalid", **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


# ---------- setup ----------
@transaction.atomic
def create_team(name, players, owner=None):
    name = (name or "").strip()
    roster, seen = [], set()
    for item in players:
        n, r = (item.get("name"), item.get("role")) if isinstance(item, dict) else (item, None)
        n = (n or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            roster.append((n, r if r in BAT_RANK else Player.Role.ALL_ROUNDER))
    if not name:
        raise RuleError("Give the team a name.")
    if len(roster) < 2:
        raise RuleError("A team needs at least 2 players.")
    if len(roster) > 30:
        raise RuleError("That is too many players for one team.")
    if Team.objects.filter(owner=owner, name__iexact=name).exists():
        raise RuleError("You already have a team with that name.")
    team = Team.objects.create(name=name, owner=owner)
    Player.objects.bulk_create([Player(name=n, role=r, team=team) for n, r in roster])
    return team


def _new_innings(match, number, bat, bowl):
    # Openers and the first bowler are chosen by the scorer, so the crease starts empty.
    return Innings.objects.create(match=match, number=number, batting_team=bat, bowling_team=bowl)


@transaction.atomic
def create_match(team_a, team_b, overs, toss_winner, decision, owner=None, last_man=False, free_hit=False, max_bowler=0):
    try:
        a, b = Team.objects.get(pk=team_a, owner=owner), Team.objects.get(pk=team_b, owner=owner)
        overs = int(overs)
    except (Team.DoesNotExist, TypeError, ValueError):
        raise RuleError("Pick two teams and a valid number of overs.")
    live = Match.objects.filter(owner=owner, status=Match.Status.LIVE).first()
    if live:
        raise RuleError(f"You already have a match in progress ({live}). Only one of your matches can run at a time. "
                        "End it before starting a new one.", "live_match", match_id=live.id, match_title=str(live))
    if a.pk == b.pk:
        raise RuleError("A team can't play itself.")
    if a.players.count() < 2 or b.players.count() < 2:
        raise RuleError("Each team needs at least 2 players.")
    if not 1 <= overs <= 50:
        raise RuleError("Overs must be between 1 and 50.")
    try:
        max_bowler = int(max_bowler or 0)
    except (TypeError, ValueError):
        raise RuleError("Max overs per bowler must be a number.")
    if not 0 <= max_bowler <= 50:
        raise RuleError("Max overs per bowler must be between 1 and 50, or empty for no limit.")
    if max_bowler and min(a.players.count(), b.players.count()) * max_bowler < overs:
        raise RuleError(f"With {max_bowler} over{'' if max_bowler == 1 else 's'} each, a team with so few players "
                        f"can't bowl {overs} overs. Raise the limit or add players.")
    if toss_winner not in (a.pk, b.pk) or decision not in ("bat", "bowl"):
        raise RuleError("Choose who won the toss and what they chose.")
    winner = a if toss_winner == a.pk else b
    other = b if winner is a else a
    first, second = (winner, other) if decision == "bat" else (other, winner)
    m = Match.objects.create(
        owner=owner, team_a=a, team_b=b, overs_limit=overs, toss_winner=winner,
        toss_decision=decision, status=Match.Status.LIVE,
        last_man_batting=bool(last_man), free_hit=bool(free_hit), max_overs_per_bowler=max_bowler,
    )
    _new_innings(m, 1, first, second)
    return m


# ---------- scoring ----------
def current_innings(match):
    return match.innings.filter(is_complete=False).order_by("number").first()


def max_wickets(inn):
    n = inn.batting_team.players.count()
    return n if inn.match.last_man_batting else max(n - 1, 1)     # last man batting: everyone must be out


def lone(inn):
    """The last batter playing on alone is stored as striker == non-striker."""
    return bool(inn.striker_id) and inn.striker_id == inn.non_striker_id


def free_hit_next(inn):
    """True when the next ball is a free hit: it follows a no-ball (and stays free through wides)."""
    fh = False
    for extra in inn.balls.values_list("extra_type", flat=True):
        fh = extra == NB or (fh and extra == WD)
    return fh and inn.match.free_hit


def _bowler_legal(inn, player_id):
    return inn.balls.filter(bowler_id=player_id).exclude(extra_type__in=ILLEGAL).count()


def _capped(inn, player_id):
    cap = inn.match.max_overs_per_bowler
    return bool(cap) and _bowler_legal(inn, player_id) >= cap * 6


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def compute_result(match):
    a, b = list(match.innings.order_by("number"))
    if b.total_runs > a.total_runs:
        return f"{b.batting_team} won by {_plural(max_wickets(b) - b.wickets, 'wicket')}"
    if b.total_runs < a.total_runs:
        return f"{a.batting_team} won by {_plural(a.total_runs - b.total_runs, 'run')}"
    return "Match tied"


def _finish_innings(match, inn):
    inn.is_complete = True
    inn.save()
    if inn.number == 1:
        _new_innings(match, 2, inn.bowling_team, inn.batting_team)
    else:
        match.status = Match.Status.COMPLETED
        match.result = compute_result(match)
        match.save()


@transaction.atomic
def add_ball(match, runs=0, extra="", wicket="", dismissed=None, end="", cid=""):
    inn = current_innings(match)
    if not inn:
        raise RuleError("This match is over.")
    if cid and Ball.objects.filter(innings__match=match, cid=cid).exists():
        return                                    # a retried offline ball: already counted
    if not (inn.striker_id and inn.non_striker_id):
        raise RuleError("Choose the next batter first.", "need_batter")
    if not inn.bowler_id:
        raise RuleError("Choose the bowler first.", "need_bowler")
    try:
        runs = int(runs or 0)
    except (TypeError, ValueError):
        raise RuleError("Runs must be a number.")
    if not 0 <= runs <= 7:
        raise RuleError("Runs must be between 0 and 7.")
    if extra not in ("", WD, NB, BYE, LB):
        raise RuleError("Unknown extra.")
    if wicket not in [c[0] for c in Ball.Wicket.choices]:
        raise RuleError("Unknown dismissal.")
    if end not in ("", "striker", "non"):
        raise RuleError("Unknown end.")

    if wicket and wicket != "run_out" and free_hit_next(inn):
        raise RuleError("Free hit: only a run out counts on this ball.", "free_hit")
    legal_before = inn.legal_balls
    legal = extra not in ILLEGAL
    s, n, bowler = inn.striker, inn.non_striker, inn.bowler
    ball = Ball(
        innings=inn, over_number=legal_before // 6,
        ball_in_over=legal_before % 6 + (1 if legal else 0),
        batter=s, non_striker=n, bowler=bowler, extra_type=extra, wicket_type=wicket, cid=cid or "",
    )
    if extra == WD:
        ball.extra_runs = 1 + runs
    elif extra == NB:
        ball.extra_runs, ball.runs_off_bat = 1, runs
    elif extra in (BYE, LB):
        ball.extra_runs = runs
    else:
        ball.runs_off_bat = runs

    out = None
    if wicket:
        allowed = {WD: ("stumped", "run_out", "hit_wicket"), NB: ("run_out",)}.get(extra)
        if allowed and wicket not in allowed:
            raise RuleError("That dismissal isn't possible off this delivery.")
        out = s
        if wicket == "run_out" and dismissed in (s.id, n.id):
            out = s if dismissed == s.id else n
        ball.dismissed_player = out
    ball.save()

    # New state.
    was_lone = s.id == n.id
    if was_lone:
        if out:
            s = n = None                          # the last batter is out: the innings is over
        # no partner to swap ends with, so strike never changes
    elif wicket == "run_out":
        # The dismissed batter is out at the end they were running to, unless the scorer says otherwise.
        # The new batter takes that end; whoever stands at the striker's end faces the next ball.
        if not end:
            end = "non" if (out.id == s.id) == (runs % 2 == 0) else "striker"
        survivor = n if out.id == s.id else s
        s, n = (None, survivor) if end == "striker" else (survivor, None)
    else:
        if out:
            s, n = (None, n) if out.id == s.id else (s, None)
        if runs % 2:
            s, n = n, s
    if match.last_man_batting and (s is None) != (n is None):
        used = _used_batters(inn) | {p.id for p in (s, n) if p}
        if not inn.batting_team.players.exclude(pk__in=used).exists():
            s = n = s or n                        # nobody left to bat with: the last man plays on alone
    if legal and (legal_before + 1) % 6 == 0:
        s, n, bowler = n, s, None                 # ends change (a no-op for a lone batter)
    inn.striker, inn.non_striker, inn.bowler = s, n, bowler

    legal_now = legal_before + (1 if legal else 0)
    chased = inn.number == 2 and inn.total_runs > match.innings.get(number=1).total_runs
    if legal_now >= match.overs_limit * 6 or inn.wickets >= max_wickets(inn) or chased:
        _finish_innings(match, inn)
    else:
        inn.save()


@transaction.atomic
def end_match(match):
    """Stop the match now. If the chase had started, the result comes from the current scores."""
    if match.status == Match.Status.COMPLETED:
        raise RuleError("This match has already finished.")
    inns = list(match.innings.order_by("number"))
    chase_started = len(inns) == 2 and inns[1].balls.exists()
    for i in inns:
        i.is_complete = True
        i.save()
    match.status = Match.Status.COMPLETED
    match.result = compute_result(match) + " (match ended early)" if chase_started else "Match ended early"
    match.save()


@transaction.atomic
def delete_team(team, force=False):
    matches = Match.objects.filter(Q(team_a=team) | Q(team_b=team))
    n = matches.count()
    if n and not force:
        raise RuleError(f"{team.name} has played in {_plural(n, 'match')}. Deleting the team also deletes "
                        f"{'that match' if n == 1 else 'those matches'} and the scores. Delete anyway?", "in_use")
    matches.delete()
    team.delete()


@transaction.atomic
def delete_player(player):
    team = player.team
    if Match.objects.filter(Q(team_a=team) | Q(team_b=team), status=Match.Status.LIVE).exists():
        raise RuleError(f"{team.name} is in a live match. End or finish that match before changing its players.", "live")
    played = Ball.objects.filter(Q(batter=player) | Q(non_striker=player) | Q(bowler=player)
                                 | Q(dismissed_player=player)).exists()
    if played:
        raise RuleError(f"{player.name} has played in a match, so removing them would break that scorecard. "
                        "Delete those matches first.", "played")
    if team.players.count() <= 2:
        raise RuleError("A team needs at least 2 players.", "min")
    player.delete()


def _used_batters(inn):
    ids = set(inn.balls.values_list("batter_id", flat=True))
    ids |= set(inn.balls.values_list("non_striker_id", flat=True))
    return ids | {i for i in (inn.striker_id, inn.non_striker_id) if i}


def _last_over_bowler(inn):
    over = inn.legal_balls // 6 - 1
    if over < 0:
        return None
    return inn.balls.filter(over_number=over).values_list("bowler_id", flat=True).last()


@transaction.atomic
def select(match, role, player_id):
    inn = current_innings(match)
    if not inn:
        raise RuleError("This match is over.")
    if role == "batter":
        if inn.striker_id and inn.non_striker_id:
            raise RuleError("No new batter is needed right now.")
        p = inn.batting_team.players.filter(pk=player_id).first()
        if not p or p.id in _used_batters(inn):
            raise RuleError("That player can't bat now.")
        if inn.striker_id is None:
            inn.striker = p
        else:
            inn.non_striker = p
    elif role == "bowler":
        if inn.bowler_id:
            raise RuleError("A bowler is already chosen.")
        p = inn.bowling_team.players.filter(pk=player_id).first()
        if not p:
            raise RuleError("That player isn't in the bowling team.")
        if p.id == _last_over_bowler(inn):
            raise RuleError("A bowler can't bowl two overs in a row.")
        if _capped(inn, p.id):
            raise RuleError(f"{p.name} has bowled the maximum {inn.match.max_overs_per_bowler} overs.")
        inn.bowler = p
    else:
        raise RuleError("Unknown role.")
    inn.save()


@transaction.atomic
def undo(match):
    inn = match.innings.filter(balls__isnull=False).order_by("-number").distinct().first()
    if not inn:
        raise RuleError("Nothing to undo.")
    ball = inn.balls.last()
    match.innings.filter(number__gt=inn.number).delete()
    inn.striker, inn.non_striker, inn.bowler = ball.batter, ball.non_striker, ball.bowler
    inn.is_complete = False
    inn.save()
    ball.delete()
    match.status, match.result = Match.Status.LIVE, ""
    match.save()


# ---------- read models ----------
def label(b):
    if b.wicket_type:
        return "W", "w"
    if b.extra_type == WD:
        return "Wd" + (f"+{b.extra_runs - 1}" if b.extra_runs > 1 else ""), "x"
    if b.extra_type == NB:
        return "Nb" + (f"+{b.runs_off_bat}" if b.runs_off_bat else ""), "x"
    if b.extra_type in (BYE, LB):
        return f"{b.extra_type.upper()}{b.extra_runs}", "x"
    r = b.runs_off_bat
    return str(r), ("f" if r >= 4 else "z" if r == 0 else "")


def scorecard(inn):
    bat, bowl = {}, {}

    def rec(p):
        return bat.setdefault(p.id, {"id": p.id, "name": p.name, "runs": 0, "balls": 0,
                                     "fours": 0, "sixes": 0, "out": ""})

    for b in inn.balls.select_related("batter", "non_striker", "bowler"):
        r = rec(b.batter)
        rec(b.non_striker)
        r["runs"] += b.runs_off_bat
        r["balls"] += b.extra_type != WD
        r["fours"] += b.runs_off_bat == 4
        r["sixes"] += b.runs_off_bat == 6
        w = bowl.setdefault(b.bowler_id, {"id": b.bowler_id, "name": b.bowler.name,
                                          "legal": 0, "runs": 0, "wickets": 0})
        w["runs"] += b.runs_off_bat + (b.extra_runs if b.extra_type in ILLEGAL else 0)
        w["legal"] += b.is_legal
        if b.wicket_type:
            how = b.get_wicket_type_display().lower()
            if b.wicket_type != "run_out":
                w["wickets"] += 1
                how += f" b {b.bowler.name}"
            bat[b.dismissed_player_id]["out"] = how
    for p in (inn.striker, inn.non_striker):
        if p:
            rec(p)
    bowling = [{"id": w["id"], "name": w["name"], "overs": f"{w['legal'] // 6}.{w['legal'] % 6}",
                "runs": w["runs"], "wickets": w["wickets"],
                "econ": round(w["runs"] * 6 / w["legal"], 1) if w["legal"] else 0} for w in bowl.values()]
    yet = [p.name for p in inn.batting_team.players.order_by("id") if p.id not in bat]
    return {"batting": list(bat.values()), "bowling": bowling, "yet_to_bat": yet}


def breakdown(inn):
    """Over-by-over runs, the worm line, fall of wickets and partnerships for one innings."""
    overs, fow, parts, cur, run, legal = {}, [], [], None, 0, 0
    for b in inn.balls.select_related("batter", "non_striker", "bowler", "dismissed_player"):
        run += b.total_runs
        o = overs.setdefault(b.over_number, {"over": b.over_number + 1, "runs": 0, "wickets": 0,
                                             "bowler": b.bowler.name, "balls": []})
        o["runs"] += b.total_runs
        o["wickets"] += bool(b.wicket_type)
        t, k = label(b)
        o["balls"].append({"t": t, "k": k})
        key = frozenset((b.batter_id, b.non_striker_id))
        if cur is None or cur["key"] != key:
            cur = {"key": key, "a": b.batter.name, "b": b.non_striker.name if b.non_striker_id != b.batter_id else "",
                   "runs": 0, "balls": 0}
            parts.append(cur)
        cur["runs"] += b.total_runs
        cur["balls"] += b.is_legal
        legal += b.is_legal
        if b.wicket_type:
            fow.append({"n": len(fow) + 1, "score": run, "name": b.dismissed_player.name,
                        "over": f"{legal // 6}.{legal % 6}"})
    rows = [overs[k] for k in sorted(overs)]
    total = 0
    for r in rows:
        total += r["runs"]
        r["total"] = total
    return {"by_over": rows, "fow": fow,
            "partnerships": [{"a": x["a"], "b": x["b"], "runs": x["runs"], "balls": x["balls"],
                              "k": "-".join(map(str, sorted(x["key"])))} for x in parts]}


def summarize(m, inns):
    """A few plain-English lines about the finished match and a player of the match."""
    if m.status != Match.Status.COMPLETED:
        return [], None
    pts = {}          # player name -> [points, team, runs, balls, wickets, runs conceded, legal balls]

    def rec(name, team):
        return pts.setdefault((name, team), {"pts": 0, "runs": 0, "balls": 0, "wk": 0, "conc": 0, "legal": 0, "bat": False, "bowl": False})
    lines, best_bat = [], None
    for k, i in enumerate(inns):
        card = scorecard(i)
        team, other = i.batting_team.name, i.bowling_team.name
        top = max(card["batting"], key=lambda x: (x["runs"], -x["balls"]), default=None)
        for x in card["batting"]:
            if x["balls"]:
                r = rec(x["name"], team)
                r["runs"] += x["runs"]; r["balls"] += x["balls"]; r["bat"] = True
                r["pts"] += x["runs"] + x["fours"] + 2 * x["sixes"]
        for x in card["bowling"]:
            r = rec(x["name"], other)
            r["wk"] += x["wickets"]; r["conc"] += x["runs"]; r["legal"] += int(x["overs"].split(".")[0]) * 6 + int(x["overs"].split(".")[1]); r["bowl"] = True
            r["pts"] += 20 * x["wickets"]
        if top and top["balls"]:
            lines.append(f"{team}: top score {top['name']} {top['runs']} ({top['balls']}).")
    bowlers = [(n, t, r) for (n, t), r in pts.items() if r["bowl"] and r["legal"]]
    if bowlers:
        n, t, r = max(bowlers, key=lambda z: (z[2]["wk"], -z[2]["conc"]))
        lines.append(f"Best bowling: {n} {r['wk']}/{r['conc']} ({r['legal'] // 6}.{r['legal'] % 6}).")
    potm = None
    if pts:
        (n, t), r = max(pts.items(), key=lambda kv: (kv[1]["pts"], kv[1]["runs"]))
        bits = []
        if r["bat"]:
            bits.append(f"{r['runs']} ({r['balls']})")
        if r["bowl"] and r["legal"]:
            bits.append(f"{r['wk']}/{r['conc']}")
        potm = {"name": n, "team": t, "line": " and ".join(bits)}
    return lines, potm


def _live(m, cur, first_total):
    legal = cur.legal_balls
    need = ("batter" if not (cur.striker_id and cur.non_striker_id)
            else "bowler" if not cur.bowler_id else None)
    opts = []
    if need == "batter":
        used = _used_batters(cur)
        opts = sorted((p for p in cur.batting_team.players.order_by("id") if p.id not in used),
                      key=lambda p: BAT_RANK[p.role])
    elif need == "bowler":
        last = _last_over_bowler(cur)
        pool = [p for p in cur.bowling_team.players.order_by("id") if p.id != last and not _capped(cur, p.id)]
        # Bowlers and all-rounders only; fall back to everyone if that leaves nobody.
        opts = sorted([p for p in pool if p.role != "batter"] or pool, key=lambda p: BOWL_RANK[p.role])
    over_idx = legal // 6 - 1 if need == "bowler" and legal else legal // 6
    p = lambda x: {"id": x.id, "name": x.name, "role": x.role} if x else None
    d = {
        "innings": cur.number, "striker": p(cur.striker), "non_striker": p(cur.non_striker),
        "bowler": p(cur.bowler), "need": need, "options": [p(o) for o in opts],
        "over_no": over_idx + 1, "opening": not cur.balls.exists(),
        "this_over": [dict(t=t, k=k) for t, k in map(label, cur.balls.filter(over_number=over_idx))],
        "balls_left": m.overs_limit * 6 - legal, "target": None, "runs_needed": None,
        "lone": lone(cur), "free_hit": free_hit_next(cur),
        "last_bowler": _last_over_bowler(cur),
        "roster": {"bat": [p(x) for x in cur.batting_team.players.order_by("id")],
                   "bowl": [p(x) for x in cur.bowling_team.players.order_by("id")]},
    }
    if cur.number == 2:
        d["target"] = first_total + 1
        d["runs_needed"] = max(first_total + 1 - cur.total_runs, 0)
    return d


def _last_ball(m):
    b = Ball.objects.filter(innings__match=m).order_by("-id").first()
    return {"id": b.id, "runs": b.runs_off_bat, "wicket": bool(b.wicket_type)} if b else None


def match_state(m):
    inns = list(m.innings.select_related("batting_team", "bowling_team", "striker", "non_striker", "bowler"))
    cur = next((i for i in inns if not i.is_complete), None)
    summary, potm = summarize(m, inns)
    return {
        "id": m.id, "title": str(m), "overs_limit": m.overs_limit, "status": m.status, "result": m.result,
        "toss": f"{m.toss_winner} won the toss and chose to {m.toss_decision}",
        "innings": [{"number": i.number, "team": i.batting_team.name, "runs": i.total_runs,
                     "wickets": i.wickets, "overs": i.overs_display, "run_rate": i.run_rate,
                     **scorecard(i), **breakdown(i)} for i in inns],
        "live": _live(m, cur, inns[0].total_runs) if cur else None,
        "last_ball": _last_ball(m),
        "rules": {"last_man": m.last_man_batting, "free_hit": m.free_hit, "max_bowler": m.max_overs_per_bowler},
        "summary": summary, "potm": potm,
    }


def match_brief(m):
    return {"id": m.id, "title": str(m), "status": m.status, "result": m.result,
            "date": m.created_at.strftime("%d %b %Y"),
            "scores": [f"{i.batting_team.name} {i.total_runs}/{i.wickets} ({i.overs_display})"
                       for i in m.innings.select_related("batting_team")]}


def player_stats(owner=None):
    names = {p.id: (p.name, p.team.name) for p in Player.objects.filter(team__owner=owner).select_related("team")}
    balls = Ball.objects.filter(innings__match__owner=owner)
    bat = balls.values("batter_id").annotate(
        runs=Sum("runs_off_bat"), faced=Count("id", filter=~Q(extra_type=WD)),
        fours=Count("id", filter=Q(runs_off_bat=4)), sixes=Count("id", filter=Q(runs_off_bat=6)))
    bowl = balls.values("bowler_id").annotate(
        legal=Count("id", filter=~Q(extra_type__in=ILLEGAL)), off_bat=Sum("runs_off_bat"),
        pen=Coalesce(Sum("extra_runs", filter=Q(extra_type__in=ILLEGAL)), 0),
        wkts=Count("id", filter=~Q(wicket_type="") & ~Q(wicket_type="run_out")))
    batting = [{"name": names[r["batter_id"]][0], "team": names[r["batter_id"]][1], "runs": r["runs"],
                "balls": r["faced"], "fours": r["fours"], "sixes": r["sixes"],
                "sr": round(r["runs"] * 100 / r["faced"]) if r["faced"] else 0} for r in bat]
    bowling = [{"name": names[r["bowler_id"]][0], "team": names[r["bowler_id"]][1],
                "overs": f"{r['legal'] // 6}.{r['legal'] % 6}", "runs": r["off_bat"] + r["pen"],
                "wickets": r["wkts"],
                "econ": round((r["off_bat"] + r["pen"]) * 6 / r["legal"], 1) if r["legal"] else 0} for r in bowl]
    agg = balls.aggregate(
        bat=Coalesce(Sum("runs_off_bat"), 0), extra=Coalesce(Sum("extra_runs"), 0),
        wickets=Count("id", filter=~Q(wicket_type="")), sixes=Count("id", filter=Q(runs_off_bat=6)))
    totals = {"matches": Match.objects.filter(owner=owner).count(), "teams": Team.objects.filter(owner=owner).count(),
              "runs": agg["bat"] + agg["extra"], "wickets": agg["wickets"], "sixes": agg["sixes"]}
    return {"totals": totals, "batting": sorted(batting, key=lambda x: -x["runs"])[:10],
            "bowling": sorted(bowling, key=lambda x: (-x["wickets"], x["econ"]))[:10]}
