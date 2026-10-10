from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsScorerOrReadOnly(BasePermission):
    """Anyone can watch (GET). Only a signed-in user can write, and views limit that to their own matches."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or bool(request.user and request.user.is_authenticated)


class IsScorer(BasePermission):
    """Default for every endpoint: you must be signed in. The shared live view opts out of this."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsOwnerAdmin(BasePermission):
    """The site owner (superuser) only."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)
