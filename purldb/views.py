#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.apps import apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import FieldDoesNotExist
from django.http import Http404
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.html import format_html_join
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from django.views.generic import TemplateView

import saneyaml
from crispy_forms.helper import FormHelper

from component_catalog.license_expression_dje import get_dataspace_licensing
from component_catalog.license_expression_dje import get_formatted_expression
from component_catalog.license_expression_dje import get_unique_license_keys
from dejacode_toolkit.purldb import PurlDB
from dje.templatetags.dje_tags import urlize_target_blank
from dje.utils import get_previous_next
from dje.views import APIWrapperListView
from dje.views import FieldLastLoop
from dje.views import Header
from dje.views import ObjectDetailsView
from dje.views import TableHeaderMixin
from dje.views import TabSetMixin
from dje.views import build_session_key
from purldb.filters import PurlDBFilterSet

Component = apps.get_model("component_catalog", "Component")
Package = apps.get_model("component_catalog", "package")

PURLDB_SESSION_KEY = build_session_key("purldb")


def include_purldb(user):
    return user.dataspace.enable_purldb_access


class PurlDBEnabled(UserPassesTestMixin):
    def test_func(self):
        return include_purldb(self.request.user)


def sort_data_by_fields(purldb_entry, fields_order):
    initial_data = purldb_entry.copy()
    sorted_data = {}

    for field_name in fields_order:
        value = initial_data.pop(field_name, None)
        if value:
            sorted_data[field_name] = value

    sorted_data.update(initial_data)
    return sorted_data


def get_purldb_tab_fields(purldb_entry, dataspace):
    from component_catalog.views import PackageDetailsView

    tab_essentials_fields = PackageDetailsView.tabset["essentials"]["fields"]
    sorted_data = sort_data_by_fields(purldb_entry, tab_essentials_fields)

    exclude = ["uuid"]
    tab_fields = []
    package_opts = Package._meta

    package_url = sorted_data.get("purl")
    if package_url:
        tab_fields.append(("Package URL", package_url, Package.package_url_help()))

    for field_name, value in sorted_data.items():
        if not value or field_name in exclude:
            continue

        try:
            model_field = package_opts.get_field(field_name)
        except FieldDoesNotExist:
            continue

        if field_name == "declared_license_expression":
            show_policy = dataspace.show_usage_policy_in_user_views
            licensing = get_dataspace_licensing(dataspace)
            value = format_html(get_formatted_expression(licensing, value, show_policy))
        elif field_name == "dependencies":
            value = json.dumps(value, indent=2)
        elif field_name == "size":
            value = f"{value} ({filesizeformat(value)})"
        elif field_name.endswith("url"):
            value = urlize_target_blank(value)
        elif isinstance(value, list):  # field such as `keywords`
            value = format_html_join("\n", "{}", ((entry,) for entry in value))

        label = capfirst(model_field.verbose_name)
        help_text = model_field.help_text
        tab_fields.append((label, value, help_text))

    source_packages_help = 'A list of source Package URLs (aka. "purl") for this package.'
    extra_fields = [
        ("source_packages", "Source packages", source_packages_help, saneyaml.dump),
    ]

    for field_name, label, help_text, value_func in extra_fields:
        value = sorted_data.get(field_name)
        if value:
            tab_fields.append((label, value_func(value), help_text))

    tab_fields.append(FieldLastLoop)

    return tab_fields


def inject_license_expression_formatted(dataspace, object_list):
    show_policy = dataspace.show_usage_policy_in_user_views

    license_keys = set()
    for obj in object_list:
        expression = obj.get("declared_license_expression")
        if expression:
            license_keys.update(get_unique_license_keys(expression))

    licensing = get_dataspace_licensing(dataspace, license_keys)

    for obj in object_list:
        expression = obj.get("declared_license_expression")
        if expression:
            formatted_expression = get_formatted_expression(licensing, expression, show_policy)
            obj["license_expression_formatted"] = format_html(formatted_expression)

    return object_list


class PurlDBListView(
    LoginRequiredMixin,
    PurlDBEnabled,
    TableHeaderMixin,
    APIWrapperListView,
):
    template_name = "purldb/purldb_list.html"
    template_list_table = "purldb/includes/purldb_list_table.html"
    model = Package
    table_headers = (
        Header("identifier", _("Identifier"), Package.identifier_help()),
        Header("type", _("Type")),
        Header("name", _("Name")),
        Header("version", _("Version")),
        Header("license_expression", _("License")),
        Header("download_url", _("Download URL")),
    )

    def get_queryset(self):
        self.filterset = PurlDBFilterSet(self.request.GET)
        filters_data = dict(self.filterset.data.items())

        self.list_data = (
            PurlDB(self.request.user.dataspace).get_package_list(
                search=self.request.GET.get("q", ""),
                page_size=self.paginate_by,
                page=self.request.GET.get("page", None),
                extra_payload=filters_data,
            )
            or {}
        )

        return self.list_data.get("results", [])

    @staticmethod
    def get_form_helper():
        helper = FormHelper()
        helper.form_method = "get"
        helper.form_tag = False
        helper.form_class = "form-horizontal"
        helper.label_class = "col-sm-2"
        helper.field_class = "col-sm-10"
        return helper

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_purldb"] = True

        object_uuids = [obj["uuid"] for obj in context["object_list"]]
        self.request.session[PURLDB_SESSION_KEY] = object_uuids

        context["object_list"] = inject_license_expression_formatted(
            dataspace=self.request.user.dataspace,
            object_list=context["object_list"],
        )

        context["filter"] = self.filterset
        context["form_helper"] = self.get_form_helper()

        return context


class PurlDBDetailsView(
    LoginRequiredMixin,
    PurlDBEnabled,
    TabSetMixin,
    DetailView,
):
    template_name = "purldb/purldb_details.html"
    pk_url_kwarg = "uuid"
    enforce_tab_authorization = False
    tabset = {
        "purldb": {},
    }

    def get_object(self, queryset=None):
        uuid = self.kwargs.get(self.pk_url_kwarg)
        obj = PurlDB(self.request.user.dataspace).get_package(uuid=uuid)
        if obj:
            return obj
        raise Http404

    def get_queryset(self):
        return

    def tab_purldb(self):
        purldb_entry = self.object
        dataspace = self.request.user.dataspace
        fields = get_purldb_tab_fields(purldb_entry, dataspace)
        return {
            "label": "PurlDB",
            "fields": fields,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        tabsets = ObjectDetailsView.normalized_tabsets(self.get_tabsets())

        user = self.request.user
        purldb_obj = self.object
        package = Package.objects.scope(user.dataspace).get_or_none(
            download_url=purldb_obj.get("download_url")
        )

        context.update(
            {
                "tabsets": tabsets,
                "purldb_obj": purldb_obj,
                "existing_package": package,
                "list_url": reverse("purldb:purldb_list"),
                "verbose_name_plural": "PurlDB",
                "can_add_package": user.has_perm("component_catalog.add_package"),
            }
        )

        session_uuids = self.request.session.get(PURLDB_SESSION_KEY)
        if session_uuids:
            previous_uuid, next_uuid = get_previous_next(session_uuids, purldb_obj["uuid"])
            view_name = "purldb:purldb_details"
            if previous_uuid:
                context["previous_object_url"] = reverse(view_name, args=[previous_uuid])
            if next_uuid:
                context["next_object_url"] = reverse(view_name, args=[next_uuid])

        return context


class PurlDBSearchTableView(
    LoginRequiredMixin,
    PurlDBEnabled,
    TemplateView,
):
    """Return HTML content to be injected in the Global search view through an AJAX call."""

    template_name = "purldb/includes/purldb_search_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        dataspace = self.request.user.dataspace
        search_query = self.request.GET.get("q")
        purldb_json = PurlDB(dataspace).get_package_list(search_query, page_size=20)

        if not (purldb_json and purldb_json.get("results", None)):
            raise Http404

        object_list = inject_license_expression_formatted(
            dataspace=dataspace,
            object_list=purldb_json["results"],
        )

        context.update(
            {
                "search_query": search_query,
                "object_count": purldb_json["count"],
                "object_list": object_list,
            }
        )

        return context
