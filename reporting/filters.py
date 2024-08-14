#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.views.main import ORDER_VAR
from django.shortcuts import get_object_or_404
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from dje.filters import DataspacedFilterSet
from dje.filters import DataspaceFilter
from dje.filters import DefaultOrderingFilter
from dje.filters import SearchFilter
from dje.widgets import DropDownAsListWidget
from reporting.models import Query
from reporting.models import Report


class ReportingQueryListFilter(admin.SimpleListFilter):
    """
    Allows to filter a changelist given a reporting.Query instance
    This can only be used on a ModelAdmin for which the Model is supported by
    the reporting app.
    Only available on the user dataspace objects for security reason.
    If `order_fields` are available on this Query, the ordering will be added in
    the filter parameters.
    """

    title = _("reporting query")
    parameter_name = "reporting_query"

    def lookups(self, request, model_admin):
        # Limit the availability of this filter to current user dataspace objects
        if DataspaceFilter.parameter_name in request.GET:
            return

        query_qs = (
            Query.objects.scope(request.user.dataspace)
            .get_for_model(model_admin.model)
            .prefetch_related("order_fields")
        )

        lookups = []
        for query in query_qs:
            param_dict = {
                self.parameter_name: query._get_pk_val(),
            }

            ordering_from_query = query.get_order_list_for_url(
                request, model_admin)
            if ordering_from_query:
                param_dict[ORDER_VAR] = ".".join(ordering_from_query)

            lookups.append((query.name, param_dict))

        return lookups

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string({}, [self.parameter_name, ORDER_VAR]),
            "display": _("All"),
        }
        for title, param_dict in self.lookup_choices:
            yield {
                "selected": str(param_dict.get(self.parameter_name)) == str(self.value()),
                "query_string": changelist.get_query_string(param_dict, [ORDER_VAR]),
                "display": title,
            }

    def queryset(self, request, queryset):
        if not self.value():
            return queryset

        # This filter is only available on the user dataspace objects
        query_instance = get_object_or_404(
            Query,
            pk=self.value(),
            dataspace=request.user.dataspace,
        )

        try:
            qs = query_instance.get_qs(user=request.user)
        except Exception as e:  # Broad exception as get_qs is fairly unstable
            messages.error(request, f"{self.title} filter error: {e}")
            return

        msg = f"{capfirst(self.title)} filter active. Other filters may be ignored."
        messages.warning(request, msg)

        return qs


class ReportFilterSet(DataspacedFilterSet):
    q = SearchFilter(
        label=_("Search"),
        search_fields=[
            "name",
            "description",
        ],
    )
    sort = DefaultOrderingFilter(
        label=_("Sort"),
        fields=["name", "query__content_type"],
        field_labels={
            "query__content_type": "Object type",
        },
        empty_label="Default",
        widget=DropDownAsListWidget,
    )

    class Meta:
        model = Report
        fields = (
            "q",
            "query__content_type",
            "sort",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        content_type_filter = self.filters["query__content_type"]
        content_type_filter.label = _("Object type")
        content_type_filter.extra["to_field_name"] = "model"
        content_type_filter.extra["widget"] = DropDownAsListWidget(
            label="Object type")
        content_type_filter.field.label_from_instance = lambda obj: obj.model
