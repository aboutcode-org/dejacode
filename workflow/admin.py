#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.template.defaultfilters import pluralize
from django.utils.translation import gettext as _

from dje.admin import DataspacedAdmin
from dje.admin import dejacode_site
from dje.forms import DataspacedAdminForm
from workflow.inlines import QuestionInline
from workflow.integrations import is_valid_issue_tracker_id
from workflow.models import Priority
from workflow.models import RequestTemplate


class PriorityForm(DataspacedAdminForm):
    def clean_color_code(self):
        color_code = self.cleaned_data.get("color_code", "")
        return "" if color_code == "#000000" else color_code

    class Meta:
        widgets = {
            "color_code": forms.TextInput(attrs={"type": "color"}),
        }


@admin.register(Priority, site=dejacode_site)
class PriorityAdmin(DataspacedAdmin):
    short_description = (
        "Request Priorities support management of Request workloads by "
        "Requesters and Reviewers using codes (along with icons and colors) "
        "that you can define to match your own business terminology."
    )
    long_description = (
        "If you are using the DejaCode Request API to integrate Requests with "
        "another workflow application, you can define your DejaCode Priorities "
        "to align with that application."
    )
    list_display = (
        "label",
        "position",
        "color_code",
    )
    search_fields = ("label",)
    form = PriorityForm
    activity_log = False
    save_as = False


class RequestTemplateAdminForm(DataspacedAdminForm):
    def clean_issue_tracker_id(self):
        issue_tracker_id = self.cleaned_data.get("issue_tracker_id")
        if issue_tracker_id and not is_valid_issue_tracker_id(issue_tracker_id):
            raise ValidationError(
                [
                    "Invalid issue tracker URL format. Supported formats include:",
                    "• GitHub: https://github.com/ORG/REPO_NAME",
                    "• GitLab: https://gitlab.com/GROUP/PROJECT_NAME",
                    "• Jira: https://YOUR_DOMAIN.atlassian.net/projects/PROJECTKEY",
                ]
            )
        return issue_tracker_id


@admin.register(RequestTemplate, site=dejacode_site)
class RequestTemplateAdmin(DataspacedAdmin):
    list_display = (
        "changelist_view_on_site",
        "name",
        "content_type",
        "is_active",
        "include_applies_to",
        "include_product",
        "default_assignee",
        "get_dataspace",
    )
    list_display_links = ("name",)
    list_filter = DataspacedAdmin.list_filter + (
        "content_type",
        "is_active",
        "include_applies_to",
        "include_product",
    )
    form = RequestTemplateAdminForm
    inlines = (QuestionInline,)
    actions = [
        "copy_to",
        "make_active",
        "make_inactive",
    ]
    actions_to_remove = ["compare_with"]
    # Disable the default notifications to admins.
    email_notification_on = []
    view_on_site = DataspacedAdmin.changeform_view_on_site

    change_form_template = "admin/workflow/requesttemplate/change_form.html"

    short_description = (
        "You can specify all the details you need in the request template to "
        "meet your business requirements for different kinds of requests, which"
        " you can name appropriately to comply with your organization's "
        "standards."
    )

    long_description = (
        "When your request template is ready for users, you can check the "
        "'is active' indicator so that requester can select it. Note that once"
        " a request has been created that uses a template, you can no longer "
        "modify that template. However, you can save an existing template to a "
        "new one, using the 'Save as' feature, make the changes you want "
        "to the new one, activate it, and then de-activate the older template "
        "from the 'Browse Request templates' page."
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "default_assignee",
            "content_type",
        )

    def has_delete_permission(self, request, obj=None):
        perm = super().has_delete_permission(request, obj)
        # Not deletable once at least 1 Request was submitted using this template
        if not perm or (obj and obj.requests.exists()):
            return False
        return True

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """
        Limit the options to "Save as new" if at least one Request was created
        using the current template instance.
        """
        obj = self.get_object(request, unquote(object_id))

        if obj and obj.requests.exists():
            if request.method == "POST" and "_saveasnew" not in request.POST:
                raise PermissionDenied

            extra_context = extra_context or {}
            extra_context["not_editable"] = True
            msg = _(
                "WARNING: Existing Requests are using this template. "
                "You can no longer modify this instance. "
                "The 'Save as' button is available to save your "
                "modification as a new request template."
            )
            self.message_user(request, msg, messages.WARNING)

        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        """Force the include_product to False when the ContentType is Product."""
        if obj.include_product and obj.content_type.name == "product":
            obj.include_product = False
        super().save_model(request, obj, form, change)

    @admin.display(description=_("Mark selected templates as active"))
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        message = "{} template{} w{} successfully marked as active.".format(
            updated, pluralize(updated), pluralize(updated, "as,ere")
        )
        self.message_user(request, message)

    @admin.display(description=_("Mark selected templates as inactive"))
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        message = "{} template{} w{} successfully marked as inactive.".format(
            updated, pluralize(updated), pluralize(updated, "as,ere")
        )
        self.message_user(request, message)
