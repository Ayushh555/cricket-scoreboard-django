from functools import wraps

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import services as svc
from .permissions import IsScorerOrReadOnly
from .models import Match, Player, Team


def rules(fn):
    @wraps(fn)
    def wrapper(request, *a, **kw):
        try:
            return fn(request, *a, **kw)
        except svc.RuleError as e:
            return Response({"error": str(e), "code": e.code, **e.extra}, status=400)
    return wrapper


# ---------- API ----------
@api_view(["GET", "POST"])
@rules
def teams(request):
    if request.method == "POST":
        svc.create_team(request.data.get("name"), request.data.get("players") or [], request.user)
    return Response([{"id": t.id, "name": t.name, "players": [p.name for p in t.players.order_by("id")],
                      "roster": [{"id": p.id, "name": p.name, "role": p.role} for p in t.players.order_by("id")],
                      "matches": Match.objects.filter(Q(team_a=t) | Q(team_b=t)).count()}
                     for t in Team.objects.filter(owner=request.user).prefetch_related("players")])


@api_view(["DELETE"])
@rules
def team_detail(request, pk):
    svc.delete_team(get_object_or_404(Team, pk=pk, owner=request.user), request.query_params.get("force") == "1")
    return Response({"ok": True})


@api_view(["DELETE"])
@rules
def player_detail(request, pk):
    svc.delete_player(get_object_or_404(Player, pk=pk, team__owner=request.user))
    return Response({"ok": True})


@api_view(["GET", "POST"])
@rules
def matches(request):
    if request.method == "POST":
        d = request.data
        m = svc.create_match(d.get("team_a"), d.get("team_b"), d.get("overs_limit", 6),
                             d.get("toss_winner"), d.get("toss_decision"), request.user,
                             d.get("last_man"), d.get("free_hit"), d.get("max_bowler"))
        return Response(svc.match_state(m), status=201)
    return Response([svc.match_brief(m) for m in Match.objects.filter(owner=request.user)[:30]])


def _state(pk):
    return Response(svc.match_state(get_object_or_404(Match, pk=pk)))


@api_view(["GET", "DELETE"])
@permission_classes([IsScorerOrReadOnly])      # the live share link reads this without an account
def match_detail(request, pk):
    if request.method == "DELETE":
        get_object_or_404(Match, pk=pk, owner=request.user).delete()      # signed in is enforced above
        return Response({"ok": True})
    return _state(pk)


@api_view(["POST"])
@rules
def end(request, pk):
    svc.end_match(get_object_or_404(Match, pk=pk, owner=request.user))
    return _state(pk)


@api_view(["POST"])
@rules
def ball(request, pk):
    d = request.data
    svc.add_ball(get_object_or_404(Match, pk=pk, owner=request.user), d.get("runs", 0), d.get("extra") or "",
                 d.get("wicket") or "", d.get("dismissed"), d.get("end") or "", str(d.get("cid") or "")[:40])
    return _state(pk)


@api_view(["POST"])
@rules
def undo(request, pk):
    svc.undo(get_object_or_404(Match, pk=pk, owner=request.user))
    return _state(pk)


@api_view(["POST"])
@rules
def select(request, pk):
    svc.select(get_object_or_404(Match, pk=pk, owner=request.user), request.data.get("role"), request.data.get("player"))
    return _state(pk)


@api_view(["GET"])
def stats(request):
    return Response(svc.player_stats(request.user))
