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
    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.code = code


# ---------- setup ----------
@transaction.atomic
def create_team(name, players):
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
    if Team.objects.filter(name__iexact=name, is_active=True).exists():
        raise RuleError(f"{name} already exists. Pick it from the list, or use a different name.")
    team = Team.objects.create(name=name)
    Player.objects.bulk_create([Player(name=n, role=r, team=team) for n, r in roster])
    return team


def delete_team(team_id):
    """Archive a team. Its matches, scorecards and player stats stay in the records (only the admin can erase those)."""
    team = Team.objects.filter(pk=team_id, is_active=True).first()
    if team is None:
        raise RuleError("That team doesn't exist.")
    if Match.objects.filter(Q(team_a=team) | Q(team_b=team)).exclude(status=Match.Status.COMPLETED).exists():
        raise RuleError(f"{team.name} is in a match that isn't finished yet.")
    team.is_active = False
    team.save(update_fields=["is_active"])


def _new_innings(match, number, bat, bowl):
    p = sorted(bat.players.order_by("id"), key=lambda x: BAT_RANK[x.role])[:2]  # batters open
    return Innings.objects.create(
        match=match, number=number, batting_team=bat, bowling_team=bowl,
        striker=p[0], non_striker=p[1],
    )


@transaction.atomic
def create_match(team_a, team_b, overs, toss_winner, decision):
    live = Match.objects.filter(status=Match.Status.LIVE).first()
    if live:
        raise RuleError(f"{live} is still being played. Finish it before starting a new match.",
                        code="match_live")
    try:
        a, b = Team.objects.get(pk=team_a, is_active=True), Team.objects.get(pk=team_b, is_active=True)
        overs = int(overs)
    except (Team.DoesNotExist, TypeError, ValueError):
        raise RuleError("Pick two teams and a valid number of overs.")
    if a.pk == b.pk:
        raise RuleError("A team can't play itself.")
    if a.players.count() < 2 or b.players.count() < 2:
        raise RuleError("Each team needs at least 2 players.")
    if not 1 <= overs <= 50:
        raise RuleError("Overs must be between 1 and 50.")
    if toss_winner not in (a.pk, b.pk) or decision not in ("bat", "bowl"):
        raise RuleError("Choose who won the toss and what they chose.")
    winner = a if toss_winner == a.pk else b
    other = b if winner is a else a
    first, second = (winner, other) if decision == "bat" else (other, winner)
    m = Match.objects.create(
        team_a=a, team_b=b, overs_limit=overs, toss_winner=winner,
        toss_decision=decision, status=Match.Status.LIVE,
    )
    _new_innings(m, 1, first, second)
    return m


# ---------- scoring ----------
def current_innings(match):
    return match.innings.filter(is_complete=False).order_by("number").first()


def max_wickets(inn):
    return max(inn.batting_team.players.count() - 1, 1)


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
def add_ball(match, runs=0, extra="", wicket="", dismissed=None, end=None):
    inn = current_innings(match)
    if not inn:
        raise RuleError("This match is over.")
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

    legal_before = inn.legal_balls
    legal = extra not in ILLEGAL
    s, n, bowler = inn.striker, inn.non_striker, inn.bowler
    ball = Ball(
        innings=inn, over_number=legal_before // 6,
        ball_in_over=legal_before % 6 + (1 if legal else 0),
        batter=s, non_striker=n, bowler=bowler, extra_type=extra, wicket_type=wicket,
    )
    if extra == WD:
        ball.extra_runs = 1 + runs
    elif extra == NB:
        ball.extra_runs, ball.runs_off_bat = 1, runs
    elif extra in (BYE, LB):
        ball.extra_runs = runs
    else:
        ball.runs_off_bat = runs

    if end not in (None, "", "striker", "non_striker"):
        raise RuleError("Unknown end.")
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

    # New state. A run-out can happen at either end, whoever is out, so the scorer says which end it was at:
    # the new batter takes that end and the survivor keeps the other. By default the dismissed batter's own end.
    if out:
        end = end if wicket == "run_out" and end else ("striker" if out.id == s.id else "non_striker")
        survivor = n if out.id == s.id else s
        s, n = (None, survivor) if end == "striker" else (survivor, None)
    elif runs % 2:
        s, n = n, s
    if legal and (legal_before + 1) % 6 == 0:
        s, n, bowler = n, s, None
    inn.striker, inn.non_striker, inn.bowler = s, n, bowler

    legal_now = legal_before + (1 if legal else 0)
    chased = inn.number == 2 and inn.total_runs > match.innings.get(number=1).total_runs
    if legal_now >= match.overs_limit * 6 or inn.wickets >= max_wickets(inn) or chased:
        _finish_innings(match, inn)
    else:
        inn.save()


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


def end_match(match):
    """Stop a live match for good. Its balls and stats stay; there is just no result."""
    if match.status != Match.Status.LIVE:
        raise RuleError("This match is not live.", code="not_live")
    match.innings.filter(is_complete=False).update(is_complete=True)
    match.status, match.result = Match.Status.COMPLETED, "Match ended early. No result."
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
        pool = [p for p in cur.bowling_team.players.order_by("id") if p.id != last]
        # Bowlers and all-rounders only; fall back to everyone if that leaves nobody.
        opts = sorted([p for p in pool if p.role != "batter"] or pool, key=lambda p: BOWL_RANK[p.role])
    over_idx = legal // 6 - 1 if need == "bowler" and legal else legal // 6
    p = lambda x: {"id": x.id, "name": x.name, "role": x.role} if x else None
    d = {
        "innings": cur.number, "striker": p(cur.striker), "non_striker": p(cur.non_striker),
        "bowler": p(cur.bowler), "need": need, "options": [p(o) for o in opts],
        "over_no": over_idx + 1,
        "this_over": [dict(t=t, k=k) for t, k in map(label, cur.balls.filter(over_number=over_idx))],
        "balls_left": m.overs_limit * 6 - legal, "target": None, "runs_needed": None,
    }
    if cur.number == 2:
        d["target"] = first_total + 1
        d["runs_needed"] = max(first_total + 1 - cur.total_runs, 0)
    return d


def match_state(m):
    inns = list(m.innings.select_related("batting_team", "bowling_team", "striker", "non_striker", "bowler"))
    cur = next((i for i in inns if not i.is_complete), None)
    return {
        "id": m.id, "title": str(m), "overs_limit": m.overs_limit, "status": m.status, "result": m.result,
        "toss": f"{m.toss_winner} won the toss and chose to {m.toss_decision}",
        "innings": [{"number": i.number, "team": i.batting_team.name, "runs": i.total_runs,
                     "wickets": i.wickets, "overs": i.overs_display, "run_rate": i.run_rate,
                     **scorecard(i)} for i in inns],
        "live": _live(m, cur, inns[0].total_runs) if cur else None,
    }


def match_brief(m):
    return {"id": m.id, "title": str(m), "status": m.status, "result": m.result,
            "date": m.created_at.strftime("%d %b %Y"),
            "scores": [f"{i.batting_team.name} {i.total_runs}/{i.wickets} ({i.overs_display})"
                       for i in m.innings.select_related("batting_team")]}


def player_stats():
    names = {p.id: (p.name, p.team.name) for p in Player.objects.select_related("team")}
    bat = Ball.objects.values("batter_id").annotate(
        runs=Sum("runs_off_bat"), faced=Count("id", filter=~Q(extra_type=WD)),
        fours=Count("id", filter=Q(runs_off_bat=4)), sixes=Count("id", filter=Q(runs_off_bat=6)))
    bowl = Ball.objects.values("bowler_id").annotate(
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
    return {"batting": sorted(batting, key=lambda x: -x["runs"])[:10],
            "bowling": sorted(bowling, key=lambda x: (-x["wickets"], x["econ"]))[:10]}
