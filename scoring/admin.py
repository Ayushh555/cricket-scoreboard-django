from django.contrib import admin

from .models import Ball, Innings, Match, Player, Team


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 5


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    # "Delete team" in the app only unticks is_active. Real deletion (and match records) lives here, in the admin.
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = [PlayerInline]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "overs_limit", "status", "created_at")
    list_filter = ("status",)


@admin.register(Innings)
class InningsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "total_runs", "wickets", "overs_display", "is_complete")


@admin.register(Ball)
class BallAdmin(admin.ModelAdmin):
    list_display = ("innings", "over_number", "ball_in_over", "batter", "bowler",
                    "runs_off_bat", "extra_type", "wicket_type")
    list_filter = ("innings__match", "innings")
