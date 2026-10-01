import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST


def _body(request):
    try:
        d = json.loads(request.body or b"{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)


@ensure_csrf_cookie
@require_http_methods(["GET"])
def me(request):
    """Also sets the CSRF cookie, so call it once when a page loads."""
    u = request.user
    return JsonResponse({"authenticated": u.is_authenticated, "username": u.username if u.is_authenticated else None})


@require_POST
def register(request):
    d = _body(request)
    username = str(d.get("username") or "").strip()
    password = str(d.get("password") or "")
    if len(username) < 3:
        return _err("Username must be at least 3 characters.")
    if User.objects.filter(username__iexact=username).exists():
        return _err("That username is already taken.")
    try:
        validate_password(password, User(username=username))
    except ValidationError as e:
        return _err(" ".join(e.messages))
    user = User.objects.create_user(username=username, password=password)
    login(request, user)
    return JsonResponse({"authenticated": True, "username": user.username}, status=201)


@require_POST
def login_view(request):
    d = _body(request)
    user = authenticate(request, username=str(d.get("username") or "").strip(), password=str(d.get("password") or ""))
    if user is None:
        return _err("Wrong username or password.", 401)
    login(request, user)
    return JsonResponse({"authenticated": True, "username": user.username})


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"authenticated": False})
