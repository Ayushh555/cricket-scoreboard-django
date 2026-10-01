from functools import wraps

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services as svc
from .models import Match, Team


def rules(fn):
    @wraps(fn)
    def wrapper(request, *a, **kw):
        try:
            return fn(request, *a, **kw)
        except svc.RuleError as e:
            return Response({"error": str(e), "code": e.code}, status=400)
    return wrapper


# ---------- API ----------
def _team_list():
    return Response([{"id": t.id, "name": t.name, "players": [p.name for p in t.players.order_by("id")],
                      "roster": [{"name": p.name, "role": p.role} for p in t.players.order_by("id")]}
                     for t in Team.objects.filter(is_active=True).prefetch_related("players")])


@api_view(["GET", "POST"])
@rules
def teams(request):
    if request.method == "POST":
        svc.create_team(request.data.get("name"), request.data.get("players") or [])
    return _team_list()


# Deleting a team only archives it: its matches and stats stay. There is deliberately no API to delete matches;
# match records can only be erased from the admin site.
@api_view(["DELETE"])
@rules
def team_detail(request, pk):
    svc.delete_team(pk)
    return _team_list()


@api_view(["GET", "POST"])
@rules
def matches(request):
    if request.method == "POST":
        d = request.data
        m = svc.create_match(d.get("team_a"), d.get("team_b"), d.get("overs_limit", 6),
                             d.get("toss_winner"), d.get("toss_decision"))
        return Response(svc.match_state(m), status=201)
    return Response([svc.match_brief(m) for m in Match.objects.all()])


def _state(pk):
    return Response(svc.match_state(get_object_or_404(Match, pk=pk)))


@api_view(["GET"])
def match_detail(request, pk):
    return _state(pk)


@api_view(["POST"])
@rules
def ball(request, pk):
    d = request.data
    svc.add_ball(get_object_or_404(Match, pk=pk), d.get("runs", 0), d.get("extra") or "",
                 d.get("wicket") or "", d.get("dismissed"), d.get("end"))
    return _state(pk)


@api_view(["POST"])
@rules
def undo(request, pk):
    svc.undo(get_object_or_404(Match, pk=pk))
    return _state(pk)


@api_view(["POST"])
@rules
def end(request, pk):
    svc.end_match(get_object_or_404(Match, pk=pk))
    return _state(pk)


@api_view(["POST"])
@rules
def select(request, pk):
    svc.select(get_object_or_404(Match, pk=pk), request.data.get("role"), request.data.get("player"))
    return _state(pk)


@api_view(["GET"])
def stats(request):
    return Response(svc.player_stats())
