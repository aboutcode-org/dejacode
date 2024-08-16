#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils.translation import gettext_lazy as _

import django_filters

from dje.filters import DataspacedFilterSet
from dje.filters import DefaultOrderingFilter
from dje.filters import SearchFilter
from dje.widgets import DropDownAsListWidget
from workflow.models import Request


class FollowedByMeFilter(django_filters.Filter):
    def filter(self, qs, value):
        if value == "yes":
            request = getattr(self.parent, "request", None)
            if request:
                return qs.followed_by(request.user)
        return qs


class RequestFilterSet(DataspacedFilterSet):
    related_only = [
        "status",
        "request_template",
        "requester",
        "assignee",
        "priority",
    ]
    q = SearchFilter(
        label=_("Search"),
        search_fields=[
            "title",
            "notes",
            "product_context__name",
            "product_context__version",
            "content_object_repr",
            "serialized_data",
        ],
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        empty_label="Recent activity (default)",
        choices=(
            ("-created_date", "Newest"),
            ("priority", "Priority"),
            ("status", "Status"),
            ("request_template", "Form"),
            ("requester", "Requester"),
            ("assignee", "Assignee"),
        ),
        widget=DropDownAsListWidget,
    )
    following = FollowedByMeFilter(label=_("Following"))

    class Meta:
        model = Request
        fields = (
            "q",
            "status",
            "request_template",
            "requester",
            "assignee",
            "priority",
            "following",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["request_template"].extra["to_field_name"] = "uuid"
        self.filters["request_template"].label = _("Form")
        self.filters["requester"].extra["to_field_name"] = "username"
        self.filters["assignee"].extra["to_field_name"] = "username"
        self.filters["priority"].extra["to_field_name"] = "label"

        self.filters["request_template"].extra["widget"] = DropDownAsListWidget(
            label="Form")
        for filter_name in ["status", "requester", "assignee", "priority"]:
            self.filters[filter_name].extra["widget"] = DropDownAsListWidget()
