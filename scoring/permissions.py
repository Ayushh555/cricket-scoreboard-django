from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsScorerOrReadOnly(BasePermission):
    """Anyone can watch (GET). Only a signed-in scorer can create, change, end or delete anything."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or bool(request.user and request.user.is_authenticated)


class IsScorer(BasePermission):
    """Default for every endpoint: you must be signed in. The shared live view opts out of this."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
