from django.contrib import admin

from .models import (
    CourseStaff,
    Proposal,
    Review,
    ReviewAssignment,
    ReviewEvent,
    ReviewerIdentity,
    Student,
    Team,
)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["student_id", "name", "email", "team"]
    list_filter = ["team"]


@admin.register(ReviewerIdentity)
class ReviewerIdentityAdmin(admin.ModelAdmin):
    list_display = ["code", "student"]


@admin.register(CourseStaff)
class CourseStaffAdmin(admin.ModelAdmin):
    list_display = ["uid", "name", "email", "registered"]


@admin.register(ReviewEvent)
class ReviewEventAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "kind", "is_open"]


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ["title", "event", "team", "file_token"]


@admin.register(ReviewAssignment)
class ReviewAssignmentAdmin(admin.ModelAdmin):
    list_display = ["event", "reviewer", "proposal"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["assignment", "submitted_at"]
