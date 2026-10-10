from django.urls import path

from . import admin_api, auth_views, views

urlpatterns = [
    path("api/auth/me/", auth_views.me),
    path("api/auth/login/", auth_views.login_view),
    path("api/auth/logout/", auth_views.logout_view),
    path("api/auth/register/", auth_views.register_view),
    path("api/auth/password/", auth_views.change_password),
    path("api/admin/overview/", admin_api.overview),
    path("api/admin/users/<int:pk>/", admin_api.user_detail),
    path("api/admin/users/<int:pk>/password/", admin_api.user_password),
    path("api/admin/matches/<int:pk>/", admin_api.match_delete),
    path("api/teams/", views.teams),
    path("api/teams/<int:pk>/", views.team_detail),
    path("api/players/<int:pk>/", views.player_detail),
    path("api/matches/", views.matches),
    path("api/matches/<int:pk>/", views.match_detail),
    path("api/matches/<int:pk>/ball/", views.ball),
    path("api/matches/<int:pk>/undo/", views.undo),
    path("api/matches/<int:pk>/end/", views.end),
    path("api/matches/<int:pk>/select/", views.select),
    path("api/stats/", views.stats),
]
