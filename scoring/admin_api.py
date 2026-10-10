"""Owner-only management: see every account and match, switch accounts off, reset passwords, delete."""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Match, Team
from .permissions import IsOwnerAdmin


def _others(request, pk):
    """Any account except yourself and other owners."""
    u = get_object_or_404(User, pk=pk)
    if u.pk == request.user.pk or u.is_superuser:
        return u, Response({"error": "You can't change an owner account here."}, status=400)
    return u, None


@api_view(["GET"])
@permission_classes([IsOwnerAdmin])
def overview(request):
    users = User.objects.annotate(n_teams=Count("teams", distinct=True),
                                  n_matches=Count("matches", distinct=True)).order_by("-date_joined")
    matches = Match.objects.select_related("owner", "team_a", "team_b")[:50]
    return Response({
        "totals": {"users": User.objects.count(), "teams": Team.objects.count(),
                   "matches": Match.objects.count(),
                   "live": Match.objects.filter(status=Match.Status.LIVE).count()},
        "users": [{"id": u.id, "username": u.username, "owner": u.is_superuser, "active": u.is_active,
                   "joined": u.date_joined.strftime("%d %b %Y"),
                   "last_login": u.last_login.strftime("%d %b %Y") if u.last_login else "never",
                   "teams": u.n_teams, "matches": u.n_matches, "me": u.pk == request.user.pk} for u in users],
        "matches": [{"id": m.id, "title": str(m), "status": m.status,
                     "owner": m.owner.username if m.owner else "(none)",
                     "date": m.created_at.strftime("%d %b %Y")} for m in matches],
    })


@api_view(["PATCH", "DELETE"])
@permission_classes([IsOwnerAdmin])
def user_detail(request, pk):
    u, err = _others(request, pk)
    if err:
        return err
    if request.method == "DELETE":
        with transaction.atomic():      # matches first: teams are protected while a match still uses them
            Match.objects.filter(owner=u).delete()
            Match.objects.filter(team_a__owner=u).delete(); Match.objects.filter(team_b__owner=u).delete()
            u.delete()                  # then their teams and the account
        return Response({"ok": True})
    if "active" in request.data:
        u.is_active = bool(request.data["active"])
        u.save(update_fields=["is_active"])
    return Response({"ok": True, "active": u.is_active})


@api_view(["POST"])
@permission_classes([IsOwnerAdmin])
def user_password(request, pk):
    u, err = _others(request, pk)
    if err:
        return err
    pw = request.data.get("password") or ""
    try:
        validate_password(pw, u)
    except ValidationError as e:
        return Response({"error": " ".join(e.messages)}, status=400)
    u.set_password(pw)
    u.save(update_fields=["password"])
    return Response({"ok": True})


@api_view(["DELETE"])
@permission_classes([IsOwnerAdmin])
def match_delete(request, pk):
    get_object_or_404(Match, pk=pk).delete()
    return Response({"ok": True})
