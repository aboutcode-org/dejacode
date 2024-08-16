#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin
from django.contrib.admin.views.main import ORDER_VAR
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import NON_FIELD_ERRORS
from django.db.models import PositiveSmallIntegerField
from django.forms import HiddenInput
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from dje.admin import DataspacedAdmin
from dje.admin import DataspacedFKMixin
from dje.admin import dejacode_site
from dje.admin import get_additional_information_fieldset
from dje.client_data import add_client_data
from dje.filters import MissingInFilter
from dje.list_display import AsJoinList
from dje.list_display import AsLink
from dje.utils import CHANGELIST_LINK_TEMPLATE
from dje.utils import queryset_to_html_list
from reporting.filters import ReportingQueryListFilter
from reporting.forms import ColumnTemplateForm
from reporting.forms import QueryForm
from reporting.forms import ReportForm
from reporting.forms import ReportMassUpdateForm
from reporting.forms import get_model_data_for_column_template
from reporting.forms import get_model_data_for_order_field
from reporting.forms import get_model_data_for_query
from reporting.inlines import ColumnTemplateAssignedFieldInline
from reporting.inlines import FilterInline
from reporting.inlines import OrderFieldInline
from reporting.introspection import get_model_label
from reporting.models import Card
from reporting.models import CardLayout
from reporting.models import ColumnTemplate
from reporting.models import Filter
from reporting.models import LayoutAssignedCard
from reporting.models import OrderField
from reporting.models import Query
from reporting.models import Report


def get_content_type_map():
    return dict(
        [
            (c.pk, get_model_label(c.model_class()))
            for c in ContentType.objects.all()
            if c.model_class()
        ]
    )


def flatten_errors(formset_errors):
    """
    Convert a FormSet.errors, which is a list of dicts, into a flat list of
    error messages.
    """
    flattened = []
    for error_dict in formset_errors:
        for field_name, errors in error_dict.items():
            for error in errors.as_data():
                message = list(error)[0]
                if field_name != NON_FIELD_ERRORS:
                    val = f'Field "{field_name}": {message}'
                else:
                    val = message
                flattened.append(val)
    return flattened


@admin.register(Query, site=dejacode_site)
class QueryAdmin(DataspacedAdmin):
    form = QueryForm
    change_form_template = "admin/reporting/query/change_form.html"
    # We are using an inline for ``Filter``, but are not rendering the standard
    # Django inline UI in favor of a custom Ember-based inline UI.
    inlines = [FilterInline, OrderFieldInline]
    fieldsets = (
        ("", {"fields": ("name", "description", "content_type", "operator")}),
        get_additional_information_fieldset(),
        ("Preview", {"fields": ("get_preview",)}),
    )
    readonly_fields = DataspacedAdmin.readonly_fields + ("get_preview",)
    list_display = ("name", "description", "content_type",
                    "operator", "get_dataspace")
    list_filter = DataspacedAdmin.list_filter + (
        "content_type",
        MissingInFilter,
    )
    search_fields = ("name",)

    long_description = (
        "A Query provides you with the ability to select data from application "
        "licenses, components, and owners using the criteria that meet your "
        "business requirements. You can access a changelist of the data you "
        "select using the Preview feature, and you can also combine a query "
        "with a column template to create your own Report."
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "content_type",
            )
            .prefetch_related(
                "filters",
                "order_fields",
            )
        )

    def get_object(self, request, object_id, from_field=None):
        """
        Injects the `request` on the object instance.
        Required for `get_preview()`.
        """
        obj = super().get_object(request, object_id, from_field)
        if obj:
            obj._request = request
            return obj

    @admin.display(description=_("Results"))
    def get_preview(self, query_instance):
        """
        Return a preview of the Query results.
        The logic starts with a count and will not eval/render the QuerySet
        if over 100 results.
        Between 1 and 100 results, a 5 items list will be display, next to a
        link to the changelist for the QuerySet. See #9248.
        """
        if query_instance.filters.count() == 0:
            return "No filters defined"

        request = getattr(query_instance, "_request", None)
        if not request:
            return

        try:
            qs = query_instance.get_qs(user=request.user)
            qs_count = qs.count()
        except Exception as e:
            return f"Error: {e}"

        if not qs_count:
            return "No results."

        model = query_instance.content_type.model_class()
        model_admin = dejacode_site._registry.get(model)

        if not model_admin:  # Models like Request do not have a ModelAdmin.
            return f"{qs_count} results."

        params = {ReportingQueryListFilter.parameter_name: query_instance.id}

        order_list = query_instance.get_order_list_for_url(
            request, model_admin)
        if order_list:
            params[ORDER_VAR] = ".".join(order_list)

        if qs_count >= 100:
            url = query_instance.get_changelist_url()
            href = f"{url}?{urlencode(params)}"
            return format_html(
                CHANGELIST_LINK_TEMPLATE, href, qs_count, model._meta.verbose_name_plural
            )

        return queryset_to_html_list(qs, params, qs_limit=5)

    def get_query_options(self, request):
        """
        Return a dictionary of Query options to be injected in the client_data
        and user for the "Use a query as value" list of choices.
        The QuerySet is reused from self.get_queryset() and scoped to the
        current object dataspace on edition, or on the current user dataspace
        on addition.
        """
        # The object instance is set on the request in the DataspacedAdmin.get_form() method
        if request._object:  # Edition
            dataspace = request._object.dataspace
        else:  # Addition
            dataspace = request.user.dataspace

        queryset = self.get_queryset(request).scope(dataspace)

        return [
            {
                "id": query.pk,
                "name": query.name,
                "content_type": get_model_label(query.content_type.model_class()),
            }
            for query in queryset
        ]

    def get_client_data(self, request):
        return {
            "model_data": get_model_data_for_query(),
            "order_field_model_data": get_model_data_for_order_field(),
            "content_type_map": get_content_type_map(),
            "lookups": [
                {
                    "label": v,
                    "value": k,
                }
                for k, v in Filter.LOOKUP_CHOICES
            ],
            "query_options": self.get_query_options(request),
            "sort_options": [v for k, v in OrderField.SORT_CHOICES],
        }

    @staticmethod
    def get_filters_as_dicts(request, forms):
        filters = []

        for form in forms:
            pk = None
            if request.method == "GET":
                data = form.initial
                pk = form.instance.pk
            if request.method == "POST":
                data = form.cleaned_data
                # The 'id' field is a ModelChoiceField which validates to a model instance
                id = form.cleaned_data.get("id")
                if id:
                    pk = id.pk

            d = {
                "pk": pk,
                "field_name": data.get("field_name", ""),
                "lookup": data.get("lookup", ""),
                "value": data.get("value", ""),
                "runtime_parameter": data.get("runtime_parameter", ""),
                "negate": data.get("negate", ""),
            }
            filters.append(d)
        return filters

    @staticmethod
    def get_order_fields_as_dicts(request, forms):
        order_fields = []

        for form in forms:
            pk = None
            if request.method == "GET":
                data = form.initial
                pk = form.instance.pk
            if request.method == "POST":
                data = form.cleaned_data
                # The 'id' field is a ModelChoiceField which validates to a
                # model instance
                id = form.cleaned_data.get("id")
                if id:
                    pk = id.pk

            d = {
                "pk": pk,
                "field_name": data.get("field_name", ""),
                "seq": data.get("seq", ""),
                "sort": data.get("sort", ""),
            }
            order_fields.append(d)
        return order_fields

    def _changeform_view(self, request, object_id, form_url, extra_context):
        response = super()._changeform_view(request, object_id, form_url, extra_context)

        if response.status_code == 200:
            if request.method == "POST" and "_popup" in request.GET:
                return response

            add_client_data(request, **self.get_client_data(request))

            inline_admin_formsets = response.context_data["inline_admin_formsets"]
            filter_admin_formsets = [
                formset
                for formset in inline_admin_formsets
                if formset.opts.__class__ == FilterInline
            ]
            if not filter_admin_formsets:
                return response
            filter_formset = filter_admin_formsets[0].formset

            order_field_admin_formsets = [
                formset
                for formset in inline_admin_formsets
                if formset.opts.__class__ == OrderFieldInline
            ]
            if not order_field_admin_formsets:
                return response
            order_field_formset = order_field_admin_formsets[0].formset

            add_client_data(
                request,
                filter_formset_prefix=filter_formset.prefix,
                filter_formset_initial_form_count=filter_formset.initial_form_count(),
                filter_formset_has_errors=any(filter_formset.errors),
                filter_formset_all_errors=flatten_errors(
                    filter_formset.errors),
                order_field_formset_prefix=order_field_formset.prefix,
                order_field_formset_initial_form_count=order_field_formset.initial_form_count(),
                filters=self.get_filters_as_dicts(
                    request, filter_formset.forms),
                order_fields=self.get_order_fields_as_dicts(
                    request, order_field_formset.forms),
            )

        return response


@admin.register(ColumnTemplate, site=dejacode_site)
class ColumnTemplateAdmin(DataspacedAdmin):
    form = ColumnTemplateForm
    list_display = ("name", "description", "content_type",
                    "get_field_names", "get_dataspace")
    list_filter = DataspacedAdmin.list_filter + (
        "content_type",
        MissingInFilter,
    )
    fieldsets = (
        ("", {"fields": ("name", "description", "content_type")}),
        get_additional_information_fieldset(),
    )
    search_fields = ("name",)
    inlines = (ColumnTemplateAssignedFieldInline,)
    change_form_template = "admin/reporting/columntemplate/change_form.html"

    long_description = (
        "A Column template provides you with the ability to identify the data "
        "columns, with your own labels, to appear in a report using the column "
        "order that you specify. You can combine a column template with any "
        "query of the same object type (license, component, owner) to create "
        "your own Reports."
    )

    @admin.display(description=_("Assigned fields"))
    def get_field_names(self, instance):
        field_names = [
            assigned_field.field_name for assigned_field in instance.fields.all()]
        return format_html("<br>".join(field_names))

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("content_type").prefetch_related("fields")

    def get_client_data(self, request):
        model_data = get_model_data_for_column_template(request.user.dataspace)

        return {
            "model_data": model_data,
            "content_type_map": get_content_type_map(),
        }

    def get_column_template_assigned_fields_as_dicts(self, request, forms):
        fields = []

        for form in forms:
            pk = None
            if request.method == "GET":
                data = form.initial
                pk = form.instance.pk
            if request.method == "POST":
                data = form.cleaned_data
                # The 'id' field is a ModelChoiceField which validates to a model instance
                id = form.cleaned_data.get("id")
                if id:
                    pk = id.pk

            d = {
                "pk": pk,
                "field_name": data.get("field_name", ""),
                "display_name": data.get("display_name", ""),
                "seq": data.get("seq", ""),
            }
            fields.append(d)
        return fields

    def _changeform_view(self, request, object_id, form_url, extra_context):
        response = super()._changeform_view(request, object_id, form_url, extra_context)

        if response.status_code == 200:
            if request.method == "POST" and "_popup" in request.GET:
                return response

            add_client_data(request, **self.get_client_data(request))

            inline_admin_formsets = response.context_data["inline_admin_formsets"]
            assigned_field_formsets = [
                formset
                for formset in inline_admin_formsets
                if formset.opts.__class__ == ColumnTemplateAssignedFieldInline
            ]
            if not assigned_field_formsets:
                return response
            assigned_field_formset = assigned_field_formsets[0].formset

            initial_data = self.get_column_template_assigned_fields_as_dicts(
                request, assigned_field_formset.forms
            )

            initial_count = assigned_field_formset.initial_form_count()
            add_client_data(
                request,
                column_template_assigned_field_formset_prefix=assigned_field_formset.prefix,
                column_template_assigned_field_formset_initial_form_count=initial_count,
                column_template_assigned_field_formset_has_errors=any(
                    assigned_field_formset.errors
                ),
                column_template_assigned_fields=initial_data,
            )

        return response


@admin.register(Report, site=dejacode_site)
class ReportAdmin(DataspacedAdmin):
    list_display = (
        "changelist_view_on_site",
        "name",
        AsLink("query"),
        AsLink("column_template"),
        "group",
        "description",
        "user_available",
        "get_dataspace",
    )
    list_display_links = ("name",)
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "name",
                    "description",
                    "query",
                    "column_template",
                    "user_available",
                    "report_context",
                    "group",
                )
            },
        ),
        get_additional_information_fieldset(),
    )
    form = ReportForm
    list_filter = DataspacedAdmin.list_filter + (
        "query__content_type",
        "group",
        "user_available",
        MissingInFilter,
    )
    search_fields = ("name", "query__name", "column_template__name")
    view_on_site = DataspacedAdmin.changeform_view_on_site
    mass_update_form = ReportMassUpdateForm

    long_description = (
        "A Report combines the data selected by a Query and the output format "
        "of a Column Template. You can view the Report in this application, or "
        "you can export it to .html, .doc, .xls, and .json formats."
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "query",
            "column_template",
            "query__content_type",
            "column_template__content_type",
        )


@admin.register(Card, site=dejacode_site)
class CardAdmin(DataspacedAdmin):
    short_description = (
        "A Card provides you with the ability to make use of a Query that you "
        "would like to see on the DejaCode Home Page. "
    )
    long_description = (
        "You can define a Card for each Query that is useful for the Home Page, "
        "and you can create Card Layouts that combine Cards appropriate to "
        "specific user roles."
    )
    list_display = (
        "title",
        "query",
        "number_of_results",
        "display_changelist_link",
        "get_dataspace",
    )
    search_fields = ("title",)
    list_filter = ("query__content_type",) + DataspacedAdmin.list_filter
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "title",
                    "query",
                    "number_of_results",
                    "display_changelist_link",
                )
            },
        ),
        get_additional_information_fieldset(),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("query__content_type")


class LayoutAssignedCardInline(DataspacedFKMixin, admin.TabularInline):
    model = LayoutAssignedCard
    verbose_name_plural = "Cards"
    verbose_name = "Card"
    extra = 1
    sortable_field_name = "seq"
    formfield_overrides = {
        PositiveSmallIntegerField: {"widget": HiddenInput},
    }


@admin.register(CardLayout, site=dejacode_site)
class CardLayoutAdmin(DataspacedAdmin):
    short_description = (
        "A Card layout provides you with the ability to combine Cards that are "
        "appropriate for general viewing or for a specific user role. "
    )
    long_description = (
        "You can assign a general purpose Card Layout to your Dataspace. "
        "A User with specific interests can assign a specific Card Layout on "
        "the User Profile. Note that users only see those Cards for which they "
        "have View security on the Card data."
    )
    list_display = (
        "name",
        AsJoinList("cards_title", "<br>", short_description="Cards"),
        "get_dataspace",
    )
    search_fields = ("name",)
    fieldsets = (
        ("", {"fields": ("name",)}),
        get_additional_information_fieldset(),
    )
    inlines = [LayoutAssignedCardInline]
