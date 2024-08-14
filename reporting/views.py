#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
import io
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError
from django.forms.formsets import formset_factory
from django.http import Http404
from django.http import HttpResponse
from django.utils.encoding import smart_str
from django.utils.text import normalize_newlines
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.generic import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.list import MultipleObjectMixin

import saneyaml
import xlsxwriter

from dje.utils import get_preserved_filters
from dje.views import AdminLinksDropDownMixin
from dje.views import BootstrapCSSMixin
from dje.views import DataspacedFilterView
from dje.views import DownloadableMixin
from dje.views import HasPermissionMixin
from dje.views import PreviousNextPaginationMixin
from reporting.filters import ReportFilterSet
from reporting.forms import RuntimeFilterBaseFormSet
from reporting.forms import RuntimeFilterForm
from reporting.models import Report


class DetailListHybridView(SingleObjectMixin, MultipleObjectMixin, TemplateView):
    def _BaseDetailView_get(self, request, *args, **kwargs):
        self.object = self.get_object()

    def get_object_list(self):
        """
        Correspond to `get_queryset()` of `MultipleObjectMixin`.
        It was renamed so that it does not conflict with
        `SingleObjectMixin.get_queryset()` which is needed by
        `SingleObjectMixin.get_object()`.
        """
        raise NotImplementedError

    def _BaseListView_get(self, request, *args, **kwargs):
        self.object_list = self.get_object_list()
        allow_empty = self.get_allow_empty()

        if not allow_empty:
            # When pagination is enabled and object_list is a queryset,
            # it's better to do a cheap query than to load the un-paginated
            # queryset in memory.
            if self.get_paginate_by(self.object_list) is not None and hasattr(
                self.object_list, "exists"
            ):
                is_empty = not self.object_list.exists()
            else:
                is_empty = len(self.object_list) == 0
            if is_empty:
                raise Http404(
                    _(f"Empty list and '{self.__class__.__name__}.allow_empty' is False.")
                )

    def get(self, request, *args, **kwargs):
        self._BaseDetailView_get(request, *args, **kwargs)
        self._BaseListView_get(request, *args, **kwargs)
        return super().get(request, *args, **kwargs)


class ReportDetailsView(
    LoginRequiredMixin,
    PreviousNextPaginationMixin,
    BootstrapCSSMixin,
    DownloadableMixin,
    HasPermissionMixin,
    DetailListHybridView,
):
    model = Report
    template_name = "reporting/report_base.html"
    paginate_by = 100
    slug_field = "uuid"
    slug_url_kwarg = "uuid"

    def get_object_list(self):
        runtime_value_map = None
        if self.runtime_filter_formset.is_bound and self.runtime_filter_formset.is_valid():
            filters = [x.filter for x in self.runtime_filter_formset]
            runtime_value_map = dict(
                zip(filters, self.runtime_filter_formset.cleaned_data))

        object_list = []
        self.errors = []
        try:
            object_list = self.object.query.get_qs(
                runtime_value_map, user=self.request.user)
        except ValidationError as e:
            # Using the _non_form_errors to store the validation error, as we
            # cannot locate the exact field with the issue at that point.
            self.runtime_filter_formset._non_form_errors = e.messages
        except FieldDoesNotExist as e:
            self.errors.append(e)
        except ValueError:
            self.runtime_filter_formset._non_form_errors = [
                "Invalid value for runtime parameter"]

        return object_list

    def _BaseListView_get(self, request, *args, **kwargs):
        self.runtime_filter_formset = self.get_runtime_filter_formset(
            self.object)
        super()._BaseListView_get(request, *args, **kwargs)

    def get_root_filename(self):
        return slugify(self.object.name)

    def get_paginate_by(self, queryset):
        if self.format:  # Do not paginate if the response is downloaded as a file
            return
        return self.paginate_by

    def get_runtime_editable_filters(self, report):
        filters = list(report.query.filters.filter(runtime_parameter=True))
        for filter_ in filters:
            # '\u2192' is a right arrow character
            filter_.field_with_arrows = filter_.field_name.replace(
                "__", " \u2192 ")
        return filters

    def get_runtime_filter_formset(self, report):
        RuntimeFilterFormSet = formset_factory(
            form=RuntimeFilterForm,
            formset=RuntimeFilterBaseFormSet,
            extra=0,
        )
        return RuntimeFilterFormSet(**self.get_runtime_filter_formset_kwargs(report))

    def get_runtime_filter_formset_kwargs(self, report):
        filters = self.get_runtime_editable_filters(report)
        initial = [{"value": filter_.value} for filter_ in filters]

        kwargs = {
            "request": self.request,
            "filters": filters,
            "initial": initial,
        }

        # Decide whether to bind the formset.
        # If there is a query string, bind the formset, unless the number or
        # parameter is less than 3, as it's not likely to be formset's
        # management.
        # This handle the case where "format" and/or "page" are the only query
        # string parameter, then do not bind to avoid validation failure.
        if self.request.GET and len(self.request.GET) > 3:
            kwargs.update({"data": self.request.GET})

        return kwargs

    def get_query_string_params(self):
        """Return the query string parameters in a known order"""
        keys = self.request.GET.keys()
        return [(key, self.request.GET[key]) for key in sorted(keys)]

    def get_interpolated_report_context(self, request, report):
        if not report.report_context:
            return

        def get_time():
            now = datetime.datetime.now()
            return now.strftime("%Y-%m-%d %I:%M:%S %p")

        replacements = {
            "{{dataspace}}": lambda: request.user.dataspace,
            "{{date-time}}": get_time,
            "{{user}}": lambda: request.user,
        }

        context = report.report_context
        for string, func in replacements.items():
            context = context.replace(string, str(func()))
        return context

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        report = self.object
        model_class = report.column_template.get_model_class()
        # Only available in the UI since the link is relative to the current URL
        include_view_link = not self.format and hasattr(
            model_class, "get_absolute_url")
        interpolated_report_context = self.get_interpolated_report_context(
            request, report)
        multi_as_list = True if self.format in ["json", "yaml"] else False
        output = report.get_output(
            queryset=context["object_list"],
            user=request.user,
            include_view_link=include_view_link,
            multi_as_list=multi_as_list,
        )

        context.update(
            {
                "opts": self.model._meta,
                "preserved_filters": get_preserved_filters(request, self.model),
                "headers": report.column_template.as_headers(include_view_link),
                "runtime_filter_formset": self.runtime_filter_formset,
                "query_string_params": self.get_query_string_params(),
                "interpolated_report_context": interpolated_report_context,
                "errors": getattr(self, "errors", []),
                "output": output,
            }
        )

        return context

    def get_dump(self, dumper, **dumper_kwargs):
        """Return the data dump using provided kwargs."""
        context = self.get_context_data(**self.kwargs)
        data = [dict(zip(context["headers"], values))
                for values in context["output"]]
        return dumper(data, **dumper_kwargs)

    def get_json_response(self, **response_kwargs):
        """Return serialized results as json content response."""
        dump = self.get_dump(json.dumps, indent=2, default=smart_str)
        return HttpResponse(dump, **response_kwargs)

    def get_yaml_response(self, **response_kwargs):
        """Return serialized results as yaml content response."""
        dump = self.get_dump(saneyaml.dump)
        return HttpResponse(dump, **response_kwargs)

    def get_xlsx_response(self, **response_kwargs):
        """Return the results as `xlsx` format."""
        context = self.get_context_data(**self.kwargs)
        report_data = [context["headers"]] + context["output"]

        file_output = io.BytesIO()
        workbook = xlsxwriter.Workbook(file_output)
        worksheet = workbook.add_worksheet()

        for row_index, row in enumerate(report_data):
            for cell_index, cell in enumerate(row):
                worksheet.write_string(
                    row_index, cell_index, normalize_newlines(cell))

        workbook.close()

        return HttpResponse(file_output.getvalue(), **response_kwargs)

    def get_queryset(self):
        """
        Scope the QS to the user dataspace, as the entry point for this view is
        a UUID and it can be a shared value across dataspace, following a copy for example.
        """
        qs = Report.objects.scope(self.request.user.dataspace)
        if not self.request.user.is_staff:
            return qs.user_availables()
        return qs


class ReportListView(
    LoginRequiredMixin,
    AdminLinksDropDownMixin,
    DataspacedFilterView,
):
    """Display a list of Reports."""

    model = Report
    filterset_class = ReportFilterSet
    template_name = "reporting/report_list.html"
    template_list_table = "reporting/includes/report_list_table.html"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset()

        if not self.request.user.is_staff:
            qs = qs.user_availables()

        return qs.select_related("query__content_type").order_by("name", "query__content_type")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.GET.get("sort", None):
            context["object_list"] = self.object_list.order_by(
                "group", "name").group_by("group")
        else:
            context["object_list"] = {"": context["object_list"]}

        return context
