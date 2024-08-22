#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from rest_framework import permissions
from rest_framework.filters import OrderingFilter
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import BrowsableAPIRenderer


def get_view_name(view_cls):
    """Force the Upper case on 'Api' spelling."""
    from rest_framework.views import get_view_name as get_view_name_restframework

    name = get_view_name_restframework(view_cls)
    return name.replace("Api", "API")


class PageSizePagination(PageNumberPagination):
    """
    Add the page_size parameter. Default results per page is 10.
    A page_size parameter can be provided, limited to 100 results per page max.
    For example:

    http://api.example.org/accounts/?page=4&page_size=100
    """

    page_size = 10
    max_page_size = 100
    page_size_query_param = "page_size"


class DJEBrowsableAPIRenderer(BrowsableAPIRenderer):
    """
    Remove the HTML forms in the Browsable API.
    The Django admin forms is the preferred method.
    """

    def get_rendered_html_form(self, data, view, method, request):
        if method in ["PUT", "POST"]:
            return

        return super().get_rendered_html_form(data, view, method, request)

    def get_raw_data_form(self, data, view, method, request):
        if getattr(view, "name", "") == "Package Add":
            return
        return super().get_raw_data_form(data, view, method, request)

    def get_context(self, data, accepted_media_type, renderer_context):
        """Remove the license_annotations link from the API Root list."""
        if renderer_context["view"].__class__.__name__ == "APIRootView":
            data.pop("license_annotations", None)
        return super().get_context(data, accepted_media_type, renderer_context)


class DJESearchFilter(SearchFilter):
    search_autocomplete_params = "autocomplete"

    def get_schema_fields(self, view):
        """Inject the list of search fields in the description."""
        schema_fields = super().get_schema_fields(view)

        search_fields = getattr(view, "search_fields", None)
        if not search_fields:
            return []

        search_fields_str = ", ".join(search_fields)
        schema_fields[0].schema.description += f" Search on: {search_fields_str}"
        return schema_fields

    def is_autocomplete(self, request):
        return request.query_params.get(self.search_autocomplete_params, False)

    def get_search_fields(self, view, request):
        """
        Add a way to get another set of `search_fields` defined in the
        `search_fields_autocomplete` if the `self.search_autocomplete_params`
        is provided in the request query params.

        This is use for autocomplete lookups through the API where we only
        want to lookup in a subset of the fields, usually the fields that are
        displayed in the autocomplete results.
        """
        if self.is_autocomplete(request):
            search_fields_autocomplete = getattr(view, "search_fields_autocomplete", None)
            if search_fields_autocomplete:
                return search_fields_autocomplete

        return super().get_search_fields(view, request)

    def get_search_terms(self, request):
        """Add PackageURL fields search support for autocomplete request."""
        search_terms = super().get_search_terms(request)

        view = request.parser_context.get("view")

        if self.is_autocomplete(request) and view.basename == "package":
            params = " ".join(search_terms)
            params = params.replace("pkg:", "")
            params = params.replace("@", " ")
            params = params.replace("/", " ")
            search_terms = params.split()

        return search_terms


class DJEOrderingFilter(OrderingFilter):
    def get_default_valid_fields(self, queryset, view, context={}):
        """
        Force that no ordering fields are available by default,
        as opposed to *all* the fields when `ordering_fields` is `None`.
        """
        return []

    def get_schema_fields(self, view):
        """Inject the list of ordering fields in the description."""
        schema_fields = super().get_schema_fields(view)

        ordering_fields = getattr(view, "ordering_fields", self.ordering_fields)
        if ordering_fields:
            ordering_fields_str = ", ".join(ordering_fields)
            schema_fields[0].schema.description += f" Ordering on: {ordering_fields_str}"

        return schema_fields


class TabPermission(permissions.BasePermission):
    """
    Allow access only to superusers if the tab_permission are enabled
    for the user Dataspace.
    """

    def has_permission(self, request, view):
        """Return `True` if permission is granted, `False` otherwise."""
        if request.user.is_superuser:
            return True

        if not request.user.dataspace.tab_permissions_enabled:
            return True
