from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    scope = "login"          # limits password guessing (see REST_FRAMEWORK in settings)


def _who(request):
    return {"authenticated": request.user.is_authenticated,
            "username": request.user.username if request.user.is_authenticated else "",
            # First run: nobody has an account yet, so the first visitor can create the scorer account.
            "can_register": settings.ALLOW_FIRST_RUN_SIGNUP and not User.objects.exists()}


@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
    return Response(_who(request))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login_view(request):
    user = authenticate(request, username=(request.data.get("username") or "").strip(),
                        password=request.data.get("password") or "")
    if user is None:
        return Response({"error": "Wrong username or password."}, status=400)
    login(request, user)
    return Response(_who(request))


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    logout(request)
    return Response(_who(request))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def register_view(request):
    if not settings.ALLOW_FIRST_RUN_SIGNUP:
        return Response({"error": "Sign-up is switched off. The owner creates accounts with createsuperuser."}, status=403)
    if User.objects.exists():
        return Response({"error": "An account already exists. Ask the owner to add you in /admin/."}, status=403)
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    if not 3 <= len(username) <= 30:
        return Response({"error": "Pick a username of 3 to 30 characters."}, status=400)
    try:
        validate_password(password, User(username=username))
    except ValidationError as e:
        return Response({"error": " ".join(e.messages)}, status=400)
    user = User.objects.create_superuser(username=username, password=password)   # also works for /admin/
    login(request, user)
    return Response(_who(request), status=201)
