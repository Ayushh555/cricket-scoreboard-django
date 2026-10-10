from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
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
            "is_admin": request.user.is_superuser,
            "open_signup": settings.ALLOW_OPEN_SIGNUP,
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
    first = settings.ALLOW_FIRST_RUN_SIGNUP and not User.objects.exists()
    if not first and not settings.ALLOW_OPEN_SIGNUP:
        return Response({"error": "Sign-up is switched off. Ask the owner to add you."}, status=403)
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    if not 3 <= len(username) <= 30:
        return Response({"error": "Pick a username of 3 to 30 characters."}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return Response({"error": "That username is taken. Try another."}, status=400)
    try:
        validate_password(password, User(username=username))
    except ValidationError as e:
        return Response({"error": " ".join(e.messages)}, status=400)
    if first:      # the very first account is the owner (also works for /admin/)
        user = User.objects.create_superuser(username=username, password=password)
        login(request, user)
        return Response(_who(request), status=201)
    # Everyone else gets a normal account with their own teams and matches. They sign in next.
    User.objects.create_user(username=username, password=password)
    return Response({"created": True, "username": username}, status=201)


@api_view(["POST"])
@throttle_classes([LoginThrottle])
def change_password(request):
    if not request.user.check_password(request.data.get("current_password") or ""):
        return Response({"error": "Your current password is wrong."}, status=400)
    new = request.data.get("new_password") or ""
    try:
        validate_password(new, request.user)
    except ValidationError as e:
        return Response({"error": " ".join(e.messages)}, status=400)
    request.user.set_password(new)
    request.user.save(update_fields=["password"])
    update_session_auth_hash(request, request.user)          # stay signed in on this device
    return Response({"ok": True})
