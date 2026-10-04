from django.urls import path

from . import views

urlpatterns = [
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
