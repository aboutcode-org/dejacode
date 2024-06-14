#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import copy
import datetime
import logging
import operator
import os
from collections import defaultdict
from collections import namedtuple
from contextlib import suppress
from functools import partial
from functools import wraps
from urllib.parse import parse_qsl
from urllib.parse import unquote_plus
from urllib.parse import urlparse

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import get_deleted_objects
from django.contrib.auth import get_permission_codename
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.staticfiles import finders
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Value
from django.db.models.functions import Concat
from django.forms.formsets import formset_factory
from django.http import FileResponse
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.defaultfilters import pluralize
from django.test import RequestFactory
from django.urls import NoReverseMatch
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView
from django.views.generic import DetailView
from django.views.generic import FormView
from django.views.generic import ListView
from django.views.generic import TemplateView
from django.views.generic import UpdateView
from django.views.generic import View
from django.views.generic.detail import BaseDetailView
from django.views.generic.edit import DeleteView

import django_otp
from django_filters.views import FilterView
from grappelli.views.related import AutocompleteLookup
from grappelli.views.related import RelatedLookup
from notifications import views as notifications_views

from component_catalog.license_expression_dje import get_license_objects
from dejacode_toolkit.purldb import PurlDB
from dejacode_toolkit.scancodeio import ScanCodeIO
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje import outputs
from dje.copier import COPY_DEFAULT_EXCLUDE
from dje.copier import SKIP
from dje.copier import get_object_in
from dje.copier import get_or_create_in
from dje.decorators import accept_anonymous
from dje.forms import AccountProfileForm
from dje.forms import CopyConfigurationForm
from dje.forms import CopyDefaultsFormSet
from dje.forms import DataspaceChoiceForm
from dje.forms import DataspacedModelForm
from dje.forms import M2MCopyConfigurationForm
from dje.forms import MultiDataspaceChoiceForm
from dje.forms import TabPermissionsFormSet
from dje.models import Dataspace
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.models import HistoryFieldsMixin
from dje.models import is_secured
from dje.permissions import get_authorized_tabs
from dje.tasks import call_management_command
from dje.templatetags.dje_tags import urlize_target_blank
from dje.urn import URNValidationError
from dje.urn_resolver import resolve as urn_resolve
from dje.utils import chunked
from dje.utils import get_cpe_vuln_link
from dje.utils import get_help_text as ght
from dje.utils import get_instance_from_referer
from dje.utils import get_model_class_from_path
from dje.utils import get_object_compare_diff
from dje.utils import get_preserved_filters
from dje.utils import get_previous_next
from dje.utils import get_referer_resolver
from dje.utils import get_zipfile
from dje.utils import group_by_name_version
from dje.utils import group_by_simple
from dje.utils import has_permission
from dje.utils import queryset_to_changelist_href
from dje.utils import str_to_id_list

License = apps.get_model("license_library", "License")
Request = apps.get_model("workflow", "Request")
RequestTemplate = apps.get_model("workflow", "RequestTemplate")

logger = logging.getLogger("dje")

MIME_TYPES = {
    "xls": "application/vnd.ms-excel",
    "pdf": "application/pdf",
    "html": "text/html",
}

Header = namedtuple("Header", "field_name verbose_name help_text filter condition sort")
Header.__new__.__defaults__ = (None,) * len(Header._fields)

TabField = namedtuple("TabField", "field_name instance source value_func condition template value")
TabField.__new__.__defaults__ = (None,) * len(TabField._fields)

FieldSeparator = (None, None, None, "includes/field_separator.html")
FieldLastLoop = (None, None, None, "includes/field_last_loop.html")


class AcceptAnonymousMixin:
    """
    View mixin which accept Anonymous Users if the ANONYMOUS_USERS_DATASPACE
    setting is enabled.
    """

    @method_decorator(accept_anonymous)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class ReferenceDataspaceOnly(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.dataspace.is_reference


class IsStaffMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class IsSuperuserMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class HasPermissionMixin:
    def has_permission(self, action):
        opts = self.model._meta
        codename = get_permission_codename(action, opts)
        return self.request.user.has_perm(f"{opts.app_label}.{codename}")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_add_permission"] = self.has_permission("add")
        context["has_change_permission"] = self.has_permission("change")
        context["has_delete_permission"] = self.has_permission("delete")
        return context


class AdminLinksDropDownMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        opts = self.model._meta
        info = opts.app_label, opts.model_name

        context["changelist_url"] = reverse("admin:{}_{}_changelist".format(*info))
        context["addition_url"] = reverse("admin:{}_{}_add".format(*info))

        with suppress(NoReverseMatch):
            context["import_url"] = reverse("admin:{}_{}_import".format(*info))

        context["show_admin_links"] = self.request.user.is_staff and (
            context["has_add_permission"] or context["has_change_permission"]
        )

        return context


class GetDataspaceMixin:
    def dispatch(self, request, *args, **kwargs):
        self.dataspace = self.get_dataspace()
        self.is_user_dataspace = self.dataspace == self.request.user.dataspace
        return super().dispatch(request, *args, **kwargs)

    def get_dataspace(self):
        user_dataspace = self.request.user.dataspace
        dataspace_name = self.kwargs.get("dataspace", None)

        # User needs to be authenticated to look into reference data
        if self.request.user.is_anonymous and dataspace_name:
            raise Http404

        if dataspace_name and dataspace_name != user_dataspace.name:
            reference_dataspace = Dataspace.objects.get_reference()
            if reference_dataspace and reference_dataspace.name == dataspace_name:
                return reference_dataspace
            else:
                raise Http404

        return user_dataspace

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["dataspace"] = self.dataspace
        reference_dataspace = Dataspace.objects.get_reference()
        context["is_user_dataspace"] = self.is_user_dataspace

        include_reference = getattr(self, "include_reference_dataspace", False)
        if include_reference and reference_dataspace and self.request.user.is_authenticated:
            opts = self.model._meta
            viewname = f"{opts.app_label}:{opts.model_name}_list"
            is_reference_data = self.dataspace == reference_dataspace
            context["is_reference_data"] = is_reference_data
            if self.is_user_dataspace and not is_reference_data:
                context["reference_data_link"] = reverse(viewname, args=[reference_dataspace])
            if not self.is_user_dataspace and is_reference_data:
                context["my_data_link"] = reverse(viewname)

        return context


class DataspaceScopeMixin:
    """Mixin to scope the get_queryset() method to the current user dataspace."""

    # Set to True to include the object form the reference dataspace in the QuerySet
    include_reference_dataspace = False

    def get_queryset(self):
        """Return the `QuerySet` scoped to the current user dataspace."""
        qs = super().get_queryset()
        dataspace = self.request.user.dataspace
        return qs.scope(dataspace, include_reference=self.include_reference_dataspace)


class PreviousNextPaginationMixin:
    query_dict_page_param = "page"

    def get_previous_next(self, page_obj):
        """Return url links for the previous and next navigation."""
        previous_url = next_url = None

        query_dict = self.request.GET.copy()
        if page_obj.has_previous():
            query_dict[self.query_dict_page_param] = page_obj.previous_page_number()
            previous_url = query_dict.urlencode()
        if page_obj.has_next():
            query_dict[self.query_dict_page_param] = page_obj.next_page_number()
            next_url = query_dict.urlencode()

        return previous_url, next_url

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        page_obj = context_data.get("page_obj")
        if page_obj:
            previous_url, next_url = self.get_previous_next(page_obj)
            context_data.update(
                {
                    "previous_url": previous_url,
                    "next_url": next_url,
                }
            )

        return context_data


class TableHeaderMixin:
    table_headers = ()
    model = None
    filterset = None

    def get_table_headers(self):
        opts = self.model._meta

        sort_fields = []
        if self.filterset and "sort" in self.filterset.filters:
            sort_fields = list(self.filterset.filters["sort"].param_map.keys())

        return [
            Header(
                field_name=header.field_name,
                verbose_name=header.verbose_name or opts.get_field(header.field_name).verbose_name,
                help_text=header.help_text or ght(opts, header.field_name),
                filter=self.filterset.form[header.filter] if header.filter else None,
                condition=None,
                sort=header.field_name in sort_fields,
            )
            for header in self.table_headers
            if not header.condition or header.condition(self)
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["table_headers"] = self.get_table_headers()
        return context


class DataspacedFilterView(
    DataspaceScopeMixin,
    GetDataspaceMixin,
    HasPermissionMixin,
    TableHeaderMixin,
    PreviousNextPaginationMixin,
    FilterView,
):
    template_name = "object_list_base.html"
    template_list_table = None
    paginate_by = settings.PAGINATE_BY or 100
    # Required if `show_previous_and_next_object_links` enabled on the
    # details view.
    put_results_in_session = False
    group_name_version = False
    strict = False

    def get_filterset_kwargs(self, filterset_class):
        """
        Add the dataspace in the filterset kwargs.

        Deletes the page_kwarg from the data if present,
        so the current pagination value is not included in the filters.
        """
        kwargs = super().get_filterset_kwargs(filterset_class)

        if self.page_kwarg in self.request.GET:
            data = self.request.GET.copy()
            del data["page"]
            kwargs.update({"data": data})

        kwargs.update({"dataspace": self.dataspace})
        return kwargs

    def get_queryset(self):
        """Scope the QuerySet with the request User Dataspace."""
        return super().get_queryset().scope(self.dataspace)

    def get_extra_add_urls(self):
        extra_add_urls = []
        opts = self.model._meta

        with suppress(NoReverseMatch):
            import_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_import")
            extra_add_urls.append((f"Import {opts.verbose_name_plural}", import_url))

        return extra_add_urls

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        if self.put_results_in_session:
            session_key = build_session_key(self.model._meta.verbose_name)
            object_ids = [int(obj.id) for obj in context_data["object_list"]]
            self.request.session[session_key] = object_ids

        if self.group_name_version:
            if not self.request.GET.get("sort", None):
                name_version_groups = group_by_name_version(context_data["object_list"])
            else:
                name_version_groups = [[obj] for obj in context_data["object_list"]]

            context_data.update(
                {
                    "name_version_groups": name_version_groups,
                    "is_grouping_active": bool(
                        [1 for group in name_version_groups if len(group) > 1]
                    ),
                }
            )

        opts = self.model._meta

        add_url = None
        with suppress(NoReverseMatch):
            add_url = reverse(f"{opts.app_label}:{opts.model_name}_add")

        context_data.update(
            {
                "opts": opts,
                "add_url": add_url,
                "extra_add_urls": self.get_extra_add_urls(),
                "preserved_filters": get_preserved_filters(self.request, self.model),
                # Required for compatibility with navbar_header.html
                "search_query": self.request.GET.get("q", ""),
                "template_list_table": self.template_list_table,
            }
        )

        return context_data


class DataspacedModelFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if issubclass(self.get_form_class(), DataspacedModelForm):
            kwargs.update({"user": self.request.user})

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        opts = self.model._meta

        context.update(
            {
                "verbose_name": opts.verbose_name,
                "verbose_name_plural": opts.verbose_name_plural,
                "list_url": reverse(f"{opts.app_label}:{opts.model_name}_list"),
            }
        )

        return context


class GetDataspacedObjectMixin:
    def get_object(self, queryset=None):
        if queryset is None:  # Use a custom queryset if provided
            queryset = self.get_queryset()

        dataspace_name = self.kwargs.get("dataspace", None)
        queryset = queryset.scope_by_name(dataspace_name)

        fields = self.slug_url_kwarg
        if not isinstance(fields, (list, tuple)):
            fields = [fields]

        queryset_kwargs = {
            field_name: unquote_plus(str(self.kwargs.get(field_name, ""))) for field_name in fields
        }

        obj = get_object_or_404(queryset, **queryset_kwargs)

        user = self.request.user
        self.is_user_dataspace = obj.dataspace == user.dataspace

        self.show_licenses_policy = all(
            [self.is_user_dataspace, user.dataspace.show_usage_policy_in_user_views]
        )

        return obj


class LicenseDataForBuilderMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        licenses_data_for_builder = (
            License.objects.scope(self.request.user.dataspace)
            .filter(is_active=True)
            .data_for_expression_builder()
        )

        context.update(
            {
                "licenses_data_for_builder": licenses_data_for_builder,
            }
        )

        return context


class DataspacedCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    DataspacedModelFormMixin,
    CreateView,
):
    template_name = "object_form.html"

    def get_success_message(self, cleaned_data):
        if self.object:
            model_name = self.object._meta.verbose_name.title()
            return f'{model_name} "{self.object}" was successfully created.'


class DataspacedUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    GetDataspacedObjectMixin,
    DataspacedModelFormMixin,
    UpdateView,
):
    template_name = "object_form.html"

    def form_valid(self, form):
        if form.has_changed():
            model_name = self.model._meta.verbose_name.title()
            save_as_new = getattr(form, "save_as_new", None)
            action = "cloned" if save_as_new else "updated"
            msg = f'{model_name} "{self.object}" was successfully {action}.'
            messages.success(self.request, msg)
            return super().form_valid(form)
        else:
            messages.warning(self.request, "No fields changed.")
            return redirect(self.get_success_url())


class DataspacedDeleteView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    GetDataspacedObjectMixin,
    DataspacedModelFormMixin,
    DeleteView,
):
    template_name = "object_confirm_delete.html"

    def get_deletion_status(self):
        from dje.admin import dejacode_site

        objs = [self.object]
        __, __, perms_needed, protected = get_deleted_objects(objs, self.request, dejacode_site)

        return perms_needed, protected

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        perms_needed, protected = self.get_deletion_status()
        context.update(
            {
                "opts": self.object._meta,
                "perms_needed": perms_needed,
                "protected": protected,
            }
        )

        return context

    def form_valid(self, form):
        """Add success message and History entry."""
        self.object = self.get_object()
        perms_needed, protected = self.get_deletion_status()
        if perms_needed or protected:
            raise Http404("Permission denied")

        response = super().form_valid(form)

        model_name = self.object._meta.verbose_name.title()
        message = f'{model_name} "{self.object}" was successfully deleted.'
        messages.success(self.request, message)

        History.log_deletion(self.request.user, self.object)

        return response

    def get_success_url(self):
        if self.success_url:
            return super().get_success_url()

        opts = self.object._meta
        return reverse(f"{opts.app_label}:{opts.model_name}_list")


class TabContentView(
    GetDataspacedObjectMixin,
    DataspaceScopeMixin,
    DetailView,
):
    pass


class SendAboutFilesMixin:
    @staticmethod
    def get_filename(instance):
        """
        Return the value from the "filename" field when available or fallback to
        the string representation of the object.
        """
        filename = getattr(instance, "filename", None) or str(instance)
        for char in "/@?=#: ":
            filename = filename.replace(char, "_")
        return filename

    @staticmethod
    def get_zipped_response(about_files, filename):
        file_in_memory = get_zipfile(about_files)
        file_size = file_in_memory.tell()
        file_in_memory.seek(0)

        response = FileResponse(file_in_memory, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{filename}_about.zip"'
        response["Content-Length"] = file_size

        return response


class SendAboutFilesView(
    LoginRequiredMixin,
    DataspaceScopeMixin,
    GetDataspacedObjectMixin,
    SendAboutFilesMixin,
    BaseDetailView,
):
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        about_files = instance.get_about_files()
        filename = self.get_filename(instance)

        if not about_files:
            raise Http404("No packages available.")

        return self.get_zipped_response(about_files, filename)


class MultiSendAboutFilesView(
    LoginRequiredMixin,
    SendAboutFilesMixin,
    View,
):
    model = None

    def get(self, request):
        ids_str = request.GET.get("ids")
        ids = str_to_id_list(ids_str)

        queryset = self.model.objects.scope(self.request.user.dataspace).filter(id__in=ids)

        verbose_name = self.model._meta.verbose_name

        if not queryset:
            raise Http404(f"No {verbose_name} selected.")

        about_files = [
            about_file for instance in queryset for about_file in instance.get_about_files()
        ]

        return self.get_zipped_response(about_files, filename=verbose_name)


@accept_anonymous
def index_dispatch(request):
    """Redirect to the LOGIN_REDIRECT_URL."""
    return redirect(settings.LOGIN_REDIRECT_URL)


@login_required
def home_view(request):
    """Dataspace homepage."""
    documentation_urls = {}
    rtd_url = "https://dejacode.readthedocs.io/en/latest"

    documentation_urls = {
        "Documentation": "https://dejacode.readthedocs.io/en/latest/",
        "Tutorials": f"{rtd_url}/tutorial-1.html",
        "API documentation": reverse("api-docs:docs-index"),
        "How-To videos": "https://www.youtube.com/playlist?list=PLCq_LXeUqhkQj0u7M26fSHt1ebFhNCpCv",
    }

    support_urls = {
        "Report an issue": "https://github.com/nexB/dejacode/issues/new/",
    }

    sections = {
        "Documentation": documentation_urls,
        "Support": support_urls,
    }

    user = request.user
    if user.is_staff:
        documentation_urls["Models documentation"] = reverse("admin:docs_models")

    request_qs = Request.objects.for_list_view(user).open().order_by("-last_modified_date")

    cards = []
    homepage_layout = user.get_homepage_layout()
    if homepage_layout:
        cards = homepage_layout.cards_with_objects(user)

    context = {
        "sections": sections,
        "request_assigned_to_me": request_qs.assigned_to(user),
        "request_followed_by_me": request_qs.followed_by(user),
        "cards": cards,
    }
    return render(request, "dataspace_home.html", context)


@accept_anonymous
def urn_resolve_view(request, urn=None):
    """
    Given a URN, this view Return the details page of the Object.
    The URN needs to be well formatted and to target an existing Object.
    If not, an error page is returned.
    See the URN module for details on supported models.
    """
    # Supports value from the URL or submitted by the form in the urn_resolve.html template
    urn = urn or request.GET.get("urn")
    if not urn:
        return render(request, "urn_resolve.html")

    try:
        # The resolve method will return the corresponding Object
        instance = urn_resolve(urn, request.user.dataspace)
        # Redirecting the user to the details page of the Object
        return redirect(instance.get_absolute_url())
    except URNValidationError as e:
        error_message = e
    except ObjectDoesNotExist:
        # URN format and model is correct, but the Object request do no exists
        error_message = "The requested Object does not exist."
    except AttributeError:
        # The get_absolute_url() method is not implemented for this Model,
        # We do not have a details view for this Model.
        error_message = "Unsupported URN model."

    return render(
        request,
        "urn_resolve.html",
        {
            "error": error_message,
            "urn": urn,
        },
    )


def build_session_key(model_name, prefix=""):
    """Return a session key to be use to store data in the session."""
    if prefix:
        prefix += ":"
    return f"{prefix}{model_name}"


def normalize_tab_fields(tab_context):
    """
    Normalize to support Django 1.10 until proper code fix.
    {% for label, values, help_text, template_name in tab_context.fields %}
    """
    normalized_fields = []

    for field in tab_context["fields"]:
        if len(field) < 3:
            field += (None, None)
        if len(field) < 4:
            field += (None,)
        normalized_fields.append(field)

    tab_context["fields"] = normalized_fields

    return tab_context


class TabSetMixin:
    tabset = {}
    # The tab authorization is enabled by default.
    # This allows to turn off the authorization system on views like the PurlDB one.
    enforce_tab_authorization = True
    # When `True`, do not include any empty fields.
    hide_empty_fields = False

    def get_tabsets(self):
        """
        Return the tabsets data structure used in template rendering.
        The context for each tab declared in `self.tabset` is generated calling the
        related `self.tab_<LABEL>()` method.
        Available tabs can be configured using the `authorized_tabs` system.
        """
        tabsets = {}

        authorized_tabs = None
        if self.enforce_tab_authorization:
            authorized_tabs = get_authorized_tabs(self.model, self.request.user)

        if authorized_tabs and None in authorized_tabs:
            return {}

        for label, tab_definition in self.tabset.items():
            if authorized_tabs and label not in authorized_tabs:
                continue

            tab_context = getattr(self, f"tab_{label}")()
            if tab_context:
                tab_name = tab_definition.get("verbose_name")
                if not tab_name:
                    tab_name = _(capfirst(label.replace("_", " ")))

                tabsets[tab_name] = tab_context

        return tabsets

    def get_tab_fields(self, tab_fields):
        """
        Return list of fields suitable for the tab templates display using a list
        of `TabField` as input.
        """
        EMPTY_VALUES = ("", None, [])  # Used for conditions without absorbing `False` values.

        fields = []
        for tab_field in tab_fields:
            if not isinstance(tab_field, TabField):
                fields.append(tab_field)
                continue

            instance = tab_field.instance or self.object
            opts = instance._meta

            field = opts.get_field(tab_field.field_name)
            label = capfirst(field.verbose_name)

            source = tab_field.source or tab_field.field_name

            if tab_field.value not in EMPTY_VALUES:
                value = tab_field.value
            else:
                try:
                    # Support for dots in the `source` value, like 'owner.name'
                    value = operator.attrgetter(source)(instance)
                except AttributeError:
                    value = ""  # default to empty string

            if self.hide_empty_fields and value in EMPTY_VALUES:
                continue

            if callable(value):
                value = value()

            if tab_field.condition and not tab_field.condition(value):
                continue

            if tab_field.value_func:
                value = tab_field.value_func(value)

            template = None
            if tab_field.template:
                template = tab_field.template
            elif isinstance(field, models.BooleanField):
                template = "includes/boolean_icon.html"

            fields.append((label, value, field.help_text, template))

        return fields

    @staticmethod
    def get_owner_hierarchy(owner):
        opts = owner._meta
        parents = owner.get_parents()
        children = owner.get_children()

        extra = {}
        if parents or children:
            extra = {
                "template": "organization/tabs/tab_hierarchy.html",
                "context": {
                    "owner": owner,
                    "owner_parents": parents,
                    "owner_children": children,
                    "owner_verbose_name": opts.verbose_name,
                    "owner_verbose_name_plural": opts.verbose_name_plural,
                },
            }
        return extra

    def tab_owner(self):
        owner = self.object.owner
        if not owner:
            return

        tab_fields = [
            TabField("name", owner, source="get_absolute_link"),
            TabField("homepage_url", owner, value_func=urlize_target_blank),
            TabField("type", owner),
            TabField("contact_info", owner, value_func=urlize_target_blank),
            TabField("alias", owner),
            TabField("notes", owner),
        ]

        return {
            "fields": self.get_tab_fields(tab_fields),
            "extra": self.get_owner_hierarchy(owner),
        }

    def tab_components(self):
        component_qs = self.object.component_set.all()
        if component_qs:
            return {
                "fields": [
                    (None, component_qs, None, "tabs/tab_component.html"),
                ]
            }

    def tab_license(self):
        """Return a mapping of data for use in the license tab display or None."""
        obj = self.object
        licenses = get_license_objects(obj.license_expression, obj.licensing)

        if not licenses:
            return

        show_usage_policy = self.request.user.dataspace.show_usage_policy_in_user_views

        licence_expression_source = "license_expression_linked"
        if show_usage_policy:
            licence_expression_source = "get_license_expression_linked_with_policy"

        fields = [
            TabField("license_expression", source=licence_expression_source),
            TabField("declared_license_expression"),
            TabField("declared_license_expression_spdx"),
            TabField("other_license_expression"),
            TabField("other_license_expression_spdx"),
        ]

        if getattr(obj, "reference_notes", False):
            fields.append(TabField("reference_notes"))

        license_conditions_help = _(
            "A list of all the license conditions (obligations, restrictions, policies) that "
            'apply to this license. Click the link "Detailed license conditions" for further '
            "information."
        )

        licenses_per_table = 4
        licenses_tables = chunked(licenses, chunk_size=licenses_per_table)

        help_texts = {
            "guidance": ght(License, "guidance"),
            "category": ght(License, "category"),
            "license_conditions": license_conditions_help,
        }

        extra = {
            "template": "tabs/tab_licenses.html",
            "context": {
                "licenses_tables": licenses_tables,
                "help_texts": help_texts,
            },
        }

        return {
            "fields": self.get_tab_fields(fields),
            "extra": extra,
        }

    def tab_activity(self, exclude_product_context=False):
        user = self.request.user

        if not user.is_authenticated:
            return

        requests = self.object.get_requests(user)

        if requests and self.is_user_dataspace:
            values = {
                "requests": requests,
                "exclude_product_context": exclude_product_context,
            }
            activity_fields = [(None, values, None, "tabs/tab_activity.html")]
            label = f'Activity <span class="badge text-bg-request">{len(requests)}</span>'
            return {
                "fields": activity_fields,
                "label": format_html(label),
            }

    def tab_external_references(self):
        references = self.object.external_references.all()

        if references:
            references_fields = [(None, references, None, "tabs/tab_external.html")]
            help_texts = {
                "external_source_label": ght(ExternalSource._meta, "label"),
                "external_id": ght(ExternalReference._meta, "external_id"),
                "external_url": ght(ExternalReference._meta, "external_url"),
            }
            return {
                "fields": references_fields,
                "help_texts": help_texts,
            }

    def tab_history(self):
        if self.request.user.is_anonymous:
            return

        history_entries = (
            History.objects.get_for_object(self.object)
            .select_related("user")
            .order_by("-action_time")
        )

        tab_fields = [
            TabField("created_date"),
            TabField("created_by"),
            TabField("last_modified_date"),
            TabField("last_modified_by"),
            ("Changes", history_entries, None, "includes/field_history_changes.html"),
        ]

        return {
            "fields": self.get_tab_fields(tab_fields),
        }

    def get_package_fields(self, package, essential_tab=False):
        from component_catalog.models import PACKAGE_URL_FIELDS

        # Always displayed in the Package "Essentials" tab context but only
        # displayed if a value is available in the Component "Packages" tab.
        essential_else_bool = None if essential_tab else bool

        user = self.request.user
        expression_source = "license_expression_linked"
        if self.is_user_dataspace and user.dataspace.show_usage_policy_in_user_views:
            expression_source = "get_license_expression_linked_with_policy"

        def show_usage_policy(value):
            if user.dataspace.show_usage_policy_in_user_views and package.usage_policy_id:
                return True

        tab_fields = []

        if not essential_tab:
            tab_fields.append(
                (_("Identifier"), package.get_absolute_link(), package.identifier_help(), None)
            )

        package_url_fields_context = {
            "package": package,
            "help_texts": {field: ght(package._meta, field) for field in PACKAGE_URL_FIELDS},
        }

        tab_fields.extend(
            [
                (_("Package URL"), package.package_url, package.package_url_help(), None),
                (
                    "",
                    package_url_fields_context,
                    None,
                    "component_catalog/tabs/field_package_url_fields.html",
                ),
                TabField("filename", package, condition=essential_else_bool),
                TabField(
                    "usage_policy",
                    source="get_usage_policy_display_with_icon",
                    condition=show_usage_policy,
                ),
                TabField("download_url", package, value_func=urlize_target_blank),
            ]
        )

        if inferred_url := package.inferred_url:
            inferred_url_help = (
                "A URL deduced from the information available in a Package URL (purl)."
            )
            tab_fields.append(
                (_("Inferred URL"), urlize_target_blank(inferred_url), inferred_url_help, None)
            )

        tab_fields.extend(
            [
                TabField("size", package, source="size_formatted"),
                TabField("release_date", package, condition=essential_else_bool),
                TabField("primary_language", package, condition=essential_else_bool),
                TabField("cpe", condition=bool, value_func=get_cpe_vuln_link),
                TabField("description", package, condition=bool),
                TabField("keywords", package, value_func=lambda x: "\n".join(x)),
                TabField("project", condition=bool),
                TabField("notes", package, condition=bool),
            ]
        )

        if essential_tab:
            tab_fields.append(TabField("dataspace"))
        else:
            tab_fields.extend(
                [
                    TabField(
                        "license_expression", package, source=expression_source, condition=bool
                    ),
                    TabField("copyright", package, condition=bool),
                    TabField("notice_text", package, condition=bool),
                    TabField("homepage_url", package, condition=bool),
                    TabField("reference_notes", package, condition=bool),
                    FieldLastLoop,
                ]
            )

        return self.get_tab_fields(tab_fields)

    @staticmethod
    def normalized_tabsets(tabsets):
        """Normalize the `fields` for all the provided `tabsets`."""
        return {
            tab_name: normalize_tab_fields(tab_context) for tab_name, tab_context in tabsets.items()
        }


class ObjectDetailsView(
    DataspaceScopeMixin,
    HasPermissionMixin,
    GetDataspacedObjectMixin,
    TabSetMixin,
    DetailView,
):
    template_name = "object_details_base.html"
    # The following requires put_results_in_session = True on the list view.
    show_previous_and_next_object_links = False

    def get_referer_link(self):
        """
        Look in the HTTP_REFERER to find the origin of the request.
        If the user is coming from a object details view, we add
        the referer object URL in the context to be displayed in the UI.
        """
        resolver = get_referer_resolver(self.request)
        if resolver and "details" in resolver.url_name:
            try:
                verbose_name = resolver.func.view_class.model._meta.verbose_name
            except AttributeError:
                return
            referer_path = urlparse(self.request.META.get("HTTP_REFERER")).path
            if referer_path != self.request.path:
                return f'<a href="{referer_path}">Return to {verbose_name}</a>'

    def get_context_data(self, **kwargs):
        """
        Add the` previous` and `next` object in the context.
        Also adds the RequestTemplate if the workflow app is enabled and if the
        user is authenticated (not anonymous).
        """
        context = super().get_context_data(**kwargs)
        opts = self.model._meta
        user = self.request.user
        is_reference_data = self.object.dataspace.is_reference

        # User needs to be authenticated to look into reference data
        if self.request.user.is_anonymous and is_reference_data and not self.is_user_dataspace:
            raise Http404

        viewname = f"{opts.app_label}:{opts.model_name}_list"
        view_args = []
        if is_reference_data and not self.is_user_dataspace:
            view_args = [self.object.dataspace]
        list_url = reverse(viewname, args=view_args)

        copy_or_update_link = None
        if user.is_staff and context["has_change_permission"]:
            reference = Dataspace.objects.get_reference()
            if not is_reference_data and self.is_user_dataspace:
                object_in_reference = get_object_in(self.object, reference)
                if object_in_reference:
                    copy_or_update_link = {
                        "label": "Check for Updates",
                        "url": object_in_reference.get_compare_url(),
                    }

            elif is_reference_data and not self.is_user_dataspace:
                if get_object_in(self.object, user.dataspace):
                    copy_or_update_link = {
                        "label": "Check for Updates",
                        "url": self.object.get_compare_url(),
                    }
                else:
                    copy_or_update_link = {
                        "label": "Copy to my Dataspace",
                        "url": self.object.get_copy_url(),
                    }

        context.update(
            {
                "tabsets": self.normalized_tabsets(self.get_tabsets()),
                "verbose_name": opts.verbose_name,
                "verbose_name_plural": opts.verbose_name_plural,
                "is_reference_data": is_reference_data,
                "is_user_dataspace": self.is_user_dataspace,
                "show_licenses_policy": self.show_licenses_policy,
                "list_url": list_url,
                "opts": opts,  # Required for the preserved_filters
                "preserved_filters": get_preserved_filters(self.request, self.model),
                "copy_or_update_link": copy_or_update_link,
                "referer_link": self.get_referer_link(),
            }
        )

        if self.show_previous_and_next_object_links:
            session_key = build_session_key(opts.verbose_name)
            session_ids = self.request.session.get(session_key)
            if session_ids:
                previous_id, next_id = get_previous_next(session_ids, int(self.object.id))
                if previous_id:
                    with suppress(ObjectDoesNotExist):
                        previous_object = self.model.objects.get(id=previous_id)
                        context["previous_object_url"] = previous_object.get_absolute_url()
                if next_id:
                    with suppress(ObjectDoesNotExist):
                        next_object = self.model.objects.get(id=next_id)
                        context["next_object_url"] = next_object.get_absolute_url()

        if user.is_authenticated and self.is_user_dataspace:
            context["request_templates"] = (
                RequestTemplate.objects.scope(self.object.dataspace)
                .actives()
                .filter(include_applies_to=True)
                .for_content_type(ContentType.objects.get_for_model(self.model))
            )

        return context


@login_required
def object_copy_view(request):
    """
    Copy objects across Dataspaces.
    This is the view called by the "copy objects" admin action.
    The first step is to present to the user the list of Object to be copied
    into his Dataspace and the list of Object that already exists
    in the target and give the choice to update those.
    If the User is a member of the Reference Dataspace, he's allowed
    to copy from any source Dataspace and to select any destination.
    This result as an extra step of presenting the target Dataspace list of
    choices.
    """
    user_dataspace = request.user.dataspace
    # Declared here as it required in GET and POST cases.
    M2MConfigurationFormSet = formset_factory(
        wraps(M2MCopyConfigurationForm)(partial(M2MCopyConfigurationForm, user=request.user)),
        extra=0,
    )

    model_class = get_model_class_from_path(request.path)

    # Default entry point of the view, requested using a GET
    # At that stage, we are only looking at what the User requested,
    # making sure everything is in order, present him what is going to
    # happens and ask for his confirmation.
    if request.method == "GET":
        requested_ids = request.GET.get("ids", "")

        # In case the view is not requested with the proper parameters
        if not requested_ids:
            raise Http404

        opts = model_class._meta
        preserved_filters = get_preserved_filters(
            request, model_class, parameter_name="_changelist_filters"
        )
        changelist_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
        redirect_url = add_preserved_filters(
            {"preserved_filters": preserved_filters, "opts": opts}, changelist_url
        )

        # Ids of objects to be copied
        ids = requested_ids.split(",")

        # Limit the copy to 100 Objects at the time, as it's the number of
        # Objects we display per page, default value for the list_per_page
        # of the ModelAdmin
        COPY_NB_OBJECT_LIMIT = 100
        if len(ids) > COPY_NB_OBJECT_LIMIT:
            msg = (
                f"Maximum of objects that can be copied at once is "
                f"limited to {COPY_NB_OBJECT_LIMIT} (by system-wide settings)"
            )
            messages.warning(request, msg)
            return redirect(redirect_url)

        # Let's find the Source Dataspace using the first id
        # This block will redirect the user to the list if the
        # first id of the list do not exist
        try:
            source_object = model_class.objects.get(id=ids[0])
        except ObjectDoesNotExist:
            return redirect(redirect_url)

        # No custom permission for 'copy', we use the 'add' one
        if not has_permission(source_object, request.user, "add"):
            messages.error(request, _("Sorry you do not have rights to execute this action"))
            return redirect(redirect_url)

        source = source_object.dataspace
        # As a non-Reference Dataspace User, I can only use the Reference
        # data as the source and my Dataspace as the target
        # As a Reference User, I can choose both, source and target.
        if user_dataspace.is_reference:
            # The following is only used when the User is in the Reference
            targets_from_request = request.GET.getlist("target")
            # If the target has been set, then we can continue
            if targets_from_request:
                data = {"target": targets_from_request}
                choice_form = MultiDataspaceChoiceForm(source, request.user, data=data)
                if not choice_form.is_valid():
                    return redirect(redirect_url)
                targets = choice_form.cleaned_data["target"]
            # else, we build a form to offer the choice to the user,
            # choices do not include the current source
            else:
                initial = {
                    "ids": requested_ids,
                    "_changelist_filters": dict(parse_qsl(preserved_filters)).get(
                        "_changelist_filters"
                    ),
                }
                is_popup = request.GET.get(IS_POPUP_VAR, False)
                if is_popup:
                    initial["_popup"] = is_popup
                choice_form = MultiDataspaceChoiceForm(source, request.user, initial=initial)
                return render(
                    request,
                    "admin/object_copy_dataspace_form.html",
                    {
                        "form": choice_form,
                        "opts": opts,
                        "is_popup": is_popup,
                        "preserved_filters": preserved_filters,
                    },
                )
        elif not source.is_reference:
            # As a non-Reference User my only "external" source of data allowed
            # is the Reference Dataspace
            return redirect(redirect_url)
        else:
            targets = [user_dataspace]

        # At this stage, we have the Source and Target Dataspaces
        # Let's see which objects are eligible for copy, or offer the update
        copy_candidates = []
        update_candidates = []

        # Building a QuerySet based on the given ids, if an non-authorized or
        # non-existing id was injected it will be ignored thanks to the
        # id__in and the dataspace scoping.
        queryset = model_class.objects.scope(source).filter(id__in=ids)

        for target in targets:
            for source_instance in queryset:
                matched_object = get_object_in(source_instance, target)
                if matched_object:
                    # Inject the source_instance for future usage in the template
                    update_candidates.append((matched_object, source_instance))
                else:
                    copy_candidates.append((source_instance, target))

        initial = {
            "source": source,
            "targets": targets,
            "ct": ContentType.objects.get_for_model(model_class).id,
        }
        form = CopyConfigurationForm(request.user, initial=initial)

        # Many2Many exclude on copy/update
        m2m_initial = [
            {"ct": ContentType.objects.get_for_model(m2m_field.remote_field.through).id}
            for m2m_field in model_class._meta.many_to_many
        ]

        # Also handle relational fields if explicitly declared on the Model using the
        # get_extra_relational_fields method.
        for field_name in model_class.get_extra_relational_fields():
            related_model = model_class._meta.get_field(field_name).related_model
            if related_model().get_exclude_candidates_fields():
                ct = ContentType.objects.get_for_model(related_model)
                m2m_initial.append({"ct": ct.id})

        m2m_formset = M2MConfigurationFormSet(initial=m2m_initial)

        return render(
            request,
            "admin/object_copy.html",
            {
                "copy_candidates": copy_candidates,
                "update_candidates": update_candidates,
                "form": form,
                "m2m_formset": m2m_formset,
                "opts": source_object._meta,
                "preserved_filters": preserved_filters,
            },
        )

    # Second section of the view, following the POST
    if request.method == "POST":
        config_form = CopyConfigurationForm(request.user, request.POST)

        if not config_form.is_valid():
            raise Http404

        model_class = config_form.model_class
        opts = model_class._meta
        preserved_filters = get_preserved_filters(
            request, model_class, parameter_name="_changelist_filters"
        )

        # We use False rather than empty list to keep track of the non-selection
        # vs unknown in lower level copy method.
        exclude_copy = {model_class: config_form.cleaned_data.get("exclude_copy")}
        exclude_update = {model_class: config_form.cleaned_data.get("exclude_update")}

        # Append the m2m copy configuration
        for m2m_form in M2MConfigurationFormSet(request.POST):
            if not m2m_form.is_valid():
                continue
            m2m_model_class = m2m_form.model_class
            cleaned_data = m2m_form.cleaned_data
            skip_on_copy = cleaned_data.get("skip_on_copy")
            skip_on_update = cleaned_data.get("skip_on_update")
            exclude_copy.update(
                {m2m_model_class: SKIP if skip_on_copy else cleaned_data.get("exclude_copy")}
            )
            exclude_update.update(
                {m2m_model_class: SKIP if skip_on_update else cleaned_data.get("exclude_update")}
            )

        copy_candidates = request.POST.get("copy_candidates", "")
        selected_for_update = request.POST.getlist("select_for_update")

        source, copied, updated, errors = config_form.submit(
            copy_candidates, selected_for_update, exclude_copy, exclude_update
        )

        if copied or updated:
            msg = "Copied/updated from {} dataspace.".format(
                source.name if source.is_reference else "another"
            )

        if errors:
            errors_count = len(errors)
            msg = "{} object w{} not copied/updated.".format(
                errors_count, pluralize(errors_count, "as,ere")
            )
            messages.error(request, msg)

        object_for_raw_id_lookup = None
        if request.GET.get(IS_POPUP_VAR, 0):
            object_for_raw_id_lookup = copied + updated
            if len(object_for_raw_id_lookup) == 1:
                object_for_raw_id_lookup = object_for_raw_id_lookup[0][1]
            else:
                object_for_raw_id_lookup = None

        return render(
            request,
            "admin/object_copy_results.html",
            {
                "copied": copied,
                "updated": updated,
                "errors": errors,
                "opts": opts,
                "preserved_filters": preserved_filters,
                "object_for_raw_id_lookup": object_for_raw_id_lookup,
            },
        )


@login_required
def dataspace_choice_for_compare_view(request):
    ids = request.GET.getlist("ids")
    if not ids:
        raise Http404
    object_id = ids[0]

    model_class = get_model_class_from_path(request.path)
    object_to_compare = model_class.objects.get(id=object_id)

    preserved_filters = get_preserved_filters(
        request, model_class, parameter_name="_changelist_filters"
    )

    user_dataspace = request.user.dataspace
    choice_form = DataspaceChoiceForm(
        object_to_compare.dataspace,
        request.user,
        initial={
            "ids": object_id,
            "target": user_dataspace.id,
            "_changelist_filters": dict(parse_qsl(preserved_filters)).get("_changelist_filters"),
        },
    )

    return render(
        request,
        "admin/object_compare_dataspace_form.html",
        {
            "form": choice_form,
            "object_to_compare": object_to_compare,
            "opts": model_class._meta,
            "preserved_filters": preserved_filters,
        },
    )


@login_required
def object_compare_view(request):
    target_dataspace_id = request.GET.get("target", "")
    ids = request.GET.get("ids", "").split(",")

    model_class = get_model_class_from_path(request.path)
    opts = model_class._meta
    preserved_filters = get_preserved_filters(
        request, model_class, parameter_name="_changelist_filters"
    )
    changelist_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
    redirect_url = add_preserved_filters(
        {"preserved_filters": preserved_filters, "opts": opts}, changelist_url
    )

    if len(ids) != 1:
        messages.warning(
            request, "Compare allows 1 object only. Please select 1 object to compare."
        )
        return redirect(redirect_url)

    if request.user.dataspace.is_reference:
        if not target_dataspace_id:
            return dataspace_choice_for_compare_view(request)
        try:
            target_dataspace = Dataspace.objects.get(pk=target_dataspace_id)
        except ObjectDoesNotExist:
            return redirect(redirect_url)
    else:
        target_dataspace = request.user.dataspace

    try:
        source_object = model_class.objects.get(id=ids[0])
    except ObjectDoesNotExist:
        return redirect(redirect_url)

    target_object = get_object_in(source_object, target_dataspace)
    if not target_object:
        error = f'No related object in the Dataspace "{target_dataspace}"'
        messages.warning(request, error)
        return redirect(redirect_url)

    # First section of the view, presenting the per filed diff.
    if request.method == "GET":
        excluded = [
            "last_modified_date",
            "created_date",
            "completion_level",
            "usage_policy",
            "guidance",
            "guidance_url",
        ]

        compare_diff, compare_diff_m2m = get_object_compare_diff(
            source_object, target_object, excluded
        )

        return render(
            request,
            "admin/object_compare.html",
            {
                "source_object": source_object,
                "target_object": target_object,
                "compare_diff": compare_diff,
                "compare_diff_m2m": compare_diff_m2m,
                "opts": opts,
                "preserved_filters": preserved_filters,
            },
        )

    # POST section of the view
    updated_fields = []

    for field_name in request.POST.getlist("checkbox_select"):
        field = source_object._meta.get_field(field_name)
        field_value = getattr(source_object, field_name)

        if isinstance(field, models.ForeignKey):
            if field_value is not None:
                fk_in_target = get_or_create_in(field_value, target_dataspace, request.user)
                if fk_in_target:
                    setattr(target_object, field_name, fk_in_target)
                    updated_fields.append(field_name)
            else:
                setattr(target_object, field_name, None)
                updated_fields.append(field_name)
        else:
            setattr(target_object, field_name, field_value)
            updated_fields.append(field_name)

    # Saving only at the end of the process, if at least one field was modified
    if updated_fields:
        target_object.save()
        message = 'Changed {}, values updated from "{}".'.format(
            ", ".join(updated_fields), source_object.dataspace.name
        )
        History.log_addition(request.user, target_object, message)
        messages.success(request, message)

    return redirect(redirect_url)


@login_required
def clone_dataset_view(request, pk):
    """Call the clonedataset management command as a an async task."""
    changelist_url = reverse("admin:dje_dataspace_changelist")
    user = request.user
    template_dataspace = settings.TEMPLATE_DATASPACE

    if not all(
        [
            template_dataspace,
            user.is_superuser,
            user.dataspace.is_reference,
        ]
    ):
        return redirect(changelist_url)

    try:
        reference = Dataspace.objects.get(name=template_dataspace)
        target = Dataspace.objects.get(pk=pk)
    except Dataspace.DoesNotExist:
        return redirect(changelist_url)

    call_management_command.delay(
        "clonedataset",
        reference.name,
        target.name,
        user.username,
        user_id=user.id,
        product_portfolio=True,
    )

    msg = "Cloning task in progress."
    if user.email:
        msg += f' An email will be sent to "{user.email}" on completion.'
    messages.success(request, msg)

    return redirect(changelist_url)


class HierarchyView(DataspaceScopeMixin, DetailView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        opts = self.model._meta
        children = self.object.get_children()

        context.update(
            {
                "opts": opts,
                "verbose_name": opts.verbose_name,
                "parents": self.object.get_parents(),
                "children": children,
                "related_parents": self.object.related_parents.all(),
                "related_children": self.object.related_children.all(),
                "children_changelist_link": queryset_to_changelist_href(children),
                # The following is only used for the admin, we should remove it once
                # the Hierarchy in admin is removed in favor of the single User UI view.
                "content_type_id": ContentType.objects.get_for_model(self.model).id,
                # Only used on the admin side
                "preserved_filters": get_preserved_filters(
                    self.request, self.model, parameter_name="_changelist_filters"
                ),
            }
        )

        return context


class DataspaceAwareRelatedLookup(RelatedLookup):
    """
    Rxtend Grappelli's ``RelatedLookup`` view class so that the data it
    Return is scoped to the current user's dataspace.

    The security scoping is applied when the related manager is flagged as `is_secured`.
    """

    def get_queryset(self):
        if is_secured(self.model._default_manager):
            perm = get_permission_codename("change", self.model._meta)
            qs = self.model._default_manager.get_queryset(self.request.user, perm)
            qs = self.get_filtered_queryset(qs)
        else:
            qs = super().get_queryset()

        user_dataspace = self.request.user.dataspace
        if not user_dataspace.is_reference:
            qs = qs.scope(user_dataspace)
        return qs


class DataspaceAwareAutocompleteLookup(AutocompleteLookup):
    """
    Extend Grappelli's ``AutocompleteLookup`` view class so that the data
    it Return is scoped to the current user's dataspace.

    The correct behavior is for the autocomplete results to be scoped to the
    dataspace of the object that the user is editing.
    Otherwise if the user is a member of the reference dataspace, the autocomplete
    results will contain objects from other dataspaces.
    In case the user is in the reference dataspace, we use the HTTP_REFERER from
    the request to determine the edited object and scope the result to its
    dataspace.
    The proper way to do this should be to patch Grappelli's JavaScript source
    code to pass parameters about the edited object in the ajax request.

    https://github.com/sehmaschine/django-grappelli/issues/362

    The security scoping is applied when the related manager is flagged as `is_secured`.
    """

    def set_dataspace_scope(self, qs):
        """
        Limit the queryset scope to the user dataspace.
        If the user is a reference dataspace user, he may been editing an object
        from another dataspace, in that case we are trying to limit the
        results to this dataspace.
        """
        user_dataspace = self.request.user.dataspace

        # If the user is a reference dataspace user, we look into the the `HTTP_REFERER`
        # to determine if he's looking at another dataspace object.
        if user_dataspace.is_reference:
            instance = get_instance_from_referer(self.request)
            if instance:
                return qs.scope(instance.dataspace)

        return qs.scope(user_dataspace)

    def get_annotated_queryset(self, qs):
        """
        Add some annotations to assist the search fields defined in
        GRAPPELLI_AUTOCOMPLETE_SEARCH_FIELDS.
        """
        if self.model._meta.model_name in ["product", "component"]:
            qs = qs.annotate(name_version=Concat("name", Value(" "), "version"))

        if self.model._meta.model_name == "package":
            qs = qs.annotate(
                type_name_version=Concat("type", Value(" "), "name", Value(" "), "version"),
            )

        return qs

    def get_searched_queryset(self, qs):
        """
        Add support for search `Package` directly from a Package URL input term
        such as: 'pkg:type/name@version'.
        """
        term = self.GET.get("term")
        if self.model._meta.model_name == "package" and term.startswith("pkg:"):
            return qs.for_package_url(term)

        return super().get_searched_queryset(qs)

    def get_queryset(self):
        if is_secured(self.model._default_manager):
            perm = get_permission_codename("change", self.model._meta)
            qs = self.model._default_manager.get_queryset(self.request.user, perm)
        else:
            qs = self.set_dataspace_scope(self.model._default_manager.all())

        qs = self.get_annotated_queryset(qs)
        qs = self.get_filtered_queryset(qs)
        qs = self.get_searched_queryset(qs)
        return qs.distinct()


class GlobalSearchListView(AcceptAnonymousMixin, TemplateView):
    template_name = "global_search.html"
    SearchResult = namedtuple("SearchResult", ["object_list", "paginator_count"])

    def get_list_view_results(self, view_class, dataspace):
        request = RequestFactory().get("", self.request.GET)
        # Fake User.dataspace using deepcopy() to avoid any side-effects on the UI.
        request.user = copy.deepcopy(self.request.user)
        request.user.dataspace = dataspace
        request.session = {}
        response = view_class.as_view()(request)
        return self.SearchResult(
            object_list=response.context_data["object_list"],
            paginator_count=response.context_data["paginator"].count,
        )

    def get_context_data(self, **kwargs):
        # Avoid circular references
        from component_catalog.views import ComponentListView
        from component_catalog.views import PackageListView
        from license_library.views import LicenseListView
        from organization.views import OwnerListView
        from product_portfolio.views import ProductListView

        get_result = self.get_list_view_results
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "")
        if not search_query:
            return context

        user = self.request.user
        user_dataspace = user.dataspace
        reference_dataspace = Dataspace.objects.get_reference()

        context.update(
            {
                "search_query": search_query,
                "component_results": get_result(ComponentListView, user_dataspace),
                "package_results": get_result(PackageListView, user_dataspace),
                "license_results": get_result(LicenseListView, user_dataspace),
                "owner_results": get_result(OwnerListView, user_dataspace),
            }
        )

        include_products = all(
            [
                user.is_authenticated,
                user.has_perm("product_portfolio.view_product"),
            ]
        )

        if include_products:
            context.update(
                {
                    "include_products": True,
                    "product_results": get_result(ProductListView, user_dataspace),
                }
            )

        insert_reference_data = all(
            [
                self.request.user.is_authenticated,
                reference_dataspace,
                user_dataspace != reference_dataspace,
            ]
        )

        if insert_reference_data:
            context.update(
                {
                    "reference_component_results": get_result(
                        ComponentListView, reference_dataspace
                    ),
                    "reference_license_results": get_result(LicenseListView, reference_dataspace),
                    "reference_package_results": get_result(PackageListView, reference_dataspace),
                    "reference_owner_results": get_result(OwnerListView, reference_dataspace),
                    "reference_dataspace": reference_dataspace,
                }
            )

        context["include_purldb"] = all(
            [user_dataspace.enable_purldb_access, PurlDB(user).is_available()]
        )

        return context


class DownloadableMixin:
    """
    Output override methods can be defined using the pattern
    ``get_format_response()``.  For example, you can customize the json output
    by defining a method called ``get_json_response()``.
    """

    content_type_map = {
        "doc": "application/msword",
        "html": "text/html",
        "json": "application/json",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "yaml": "application/x-yaml",
    }

    def get(self, request, *args, **kwargs):
        self.format = self.get_format()
        return super().get(request, *args, **kwargs)

    def get_format(self):
        if "format" in self.request.GET:
            return self.request.GET.get("format")

    def get_root_filename(self):
        if "filename" in self.request.GET:
            return self.request.GET.get("filename")

    def get_filename(self, format):
        return f"{self.get_root_filename()}.{format}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["downloaded"] = bool(self.format)
        context["format"] = self.format
        return context

    def render_to_response(self, context, **response_kwargs):
        use_custom_response = False

        if self.format:
            content_type = self.content_type_map[self.format]
            response_kwargs["content_type"] = content_type
            if hasattr(self, f"get_{self.format}_response"):
                use_custom_response = True
                response = getattr(self, f"get_{self.format}_response")(**response_kwargs)

        if not use_custom_response:
            response = super().render_to_response(context, **response_kwargs)

        # If format is defined, make the browser download the response as a file
        if self.format:
            filename = self.get_filename(self.format)
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class BootstrapCSSMixin:
    def get_bootstrap_css_code(self):
        # Use the staticfiles.finders to get the absolute path of the file
        bootstrap_css_path = os.path.join("bootstrap-5.3.2", "css", "bootstrap.min.css")
        bootstrap_css_file_path = finders.find(bootstrap_css_path)

        with open(bootstrap_css_file_path) as f:
            css_code = f.read()
        return css_code

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bootstrap_css_code"] = self.get_bootstrap_css_code()
        return context


class ActivityLog(
    LoginRequiredMixin,
    BootstrapCSSMixin,
    DownloadableMixin,
    TemplateView,
):
    template_name = "activity_log.html"
    model = None
    action_flag_map = {
        History.ADDITION: "Addition",
        History.CHANGE: "Change",
        History.DELETION: "Deletion",
    }

    def get_days(self):
        days = self.request.GET.get("days", None)
        try:
            return int(days)
        except (TypeError, ValueError):
            return 90  # Default value

    def get_history_entries(self, days):
        """
        Return all the History entries, filtered by the number of days and
        scoped using the current user Dataspace.
        """
        user_dataspace_id = self.request.user.dataspace_id
        content_type = ContentType.objects.get_for_model(self.model)

        start = timezone.now() - datetime.timedelta(days=days)

        history_entries = History.objects.filter(
            object_dataspace_id=user_dataspace_id,
            content_type=content_type,
            action_time__gt=start,
        )

        has_history_fields = issubclass(self.model, HistoryFieldsMixin)
        if has_history_fields:
            # Use the history fields from the model for the Addition entries
            history_entries = history_entries.exclude(action_flag=History.ADDITION)

            objects = self.model.objects.scope_by_id(user_dataspace_id).filter(
                created_date__gt=start
            )

            addition_entries = []
            for obj in objects:
                addition_entries.append(
                    History(
                        action_time=obj.created_date,
                        user=obj.created_by,
                        object_dataspace=obj.dataspace,
                        content_type=content_type,
                        object_id=obj.id,
                        action_flag=History.ADDITION,
                        change_message="Added.",
                    )
                )

            history_entries = list(history_entries) + addition_entries

        return history_entries

    @staticmethod
    def get_object_or_repr(history_entry):
        try:
            return history_entry.get_edited_object()
        except ObjectDoesNotExist:
            return history_entry.object_repr

    def get_objects(self, days):
        history_entries = self.get_history_entries(days)

        objects = []
        for history_entry in history_entries:
            objects.append(
                {
                    "history": history_entry,
                    "obj": self.get_object_or_repr(history_entry),
                    "action": self.action_flag_map[history_entry.action_flag],
                }
            )

        return objects

    def get_format(self):
        return "html"

    def get_root_filename(self):
        model_name = self.model._meta.model_name
        return f"{model_name}_activity_log"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        days = self.get_days()
        context.update(
            {
                "days": days,
                "objects": self.get_objects(days),
                "verbose_name": self.model._meta.verbose_name,
                "dataspace": self.request.user.dataspace,
                "now": timezone.now(),
            }
        )
        return context


class AccountProfileView(
    LoginRequiredMixin,
    FormView,
):
    template_name = "account/profile.html"
    form_class = AccountProfileForm
    success_url = reverse_lazy("account_profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update(
            {
                "user_has_device": django_otp.user_has_device(self.request.user),
            }
        )

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        if getattr(form, "changed_data", None):
            form.save()
            messages.success(self.request, _("Profile updated."))
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        """Add the ability to regenerate the API key."""
        if request.POST.get("regenerate-api-key"):
            request.user.regenerate_api_key()
            messages.success(request, _("Your API key was regenerated."))
            return self.form_valid(None)

        return super().post(request, *args, **kwargs)


@login_required
def docs_models_view(request):
    from dje.admin import dejacode_site

    apps_white_list = [
        "organization",
        "license_library",
        "component_catalog",
        "product_portfolio",
        "workflow",
        "reporting",
        "policy",
    ]

    model_classes = [
        model for model in apps.get_models() if model._meta.app_label in apps_white_list
    ]

    def get_limited_fields(model):
        return [
            f
            for f in model._meta.get_fields()
            if not f.auto_created and f.name not in ["dataspace", "uuid"]
        ]

    help_data = defaultdict(list)
    for model in model_classes:
        opts = model._meta
        app_verbose_name = apps.app_configs.get(opts.app_label).verbose_name
        model_admin = dejacode_site._registry.get(model)
        help_data[app_verbose_name].append(
            {
                "verbose_name": opts.verbose_name,
                "short_description": getattr(model_admin, "short_description", ""),
                "long_description": getattr(model_admin, "long_description", ""),
                "fields": get_limited_fields(model),
            }
        )

    context = {
        "help_data": dict(help_data),
        "document": {"title": "Models documentation"},
    }

    return render(request, "admin/docs/models.html", context)


@login_required
def manage_copy_defaults_view(request, pk):
    changelist_url = reverse("admin:dje_dataspace_changelist")

    supported_apps = [
        "dje",
        "organization",
        "license_library",
        "component_catalog",
        "product_portfolio",
        "workflow",
        "reporting",
        "policy",
        "notification",
    ]

    try:
        dataspace = Dataspace.objects.get(pk=unquote_plus(pk))
    except Dataspace.DoesNotExist:
        return redirect(changelist_url)

    if not request.user.is_superuser or dataspace != request.user.dataspace:
        return redirect(changelist_url)

    if request.method == "POST":
        formset = CopyDefaultsFormSet(request.POST)
        if formset.is_valid():
            formset.save(dataspace)
            formset.log_change(request, dataspace, "Changed copy defaults configuration.")
            messages.success(request, _("Copy defaults updated."))
        else:
            messages.error(request, _("Error, please refresh the page and try again."))
    else:
        initial = [
            {"app_name": str(apps.get_app_config(app_label).verbose_name)}
            for app_label in supported_apps
        ]
        formset = CopyDefaultsFormSet(initial=initial)
        formset.load(dataspace, default=COPY_DEFAULT_EXCLUDE)

    context = {
        "formset": formset,
        "object": dataspace,
        "opts": dataspace._meta,
    }

    return render(request, "admin/dje/dataspace/copy_defaults_form.html", context)


@login_required
def manage_tab_permissions_view(request, pk):
    changelist_url = reverse("admin:dje_dataspace_changelist")

    try:
        dataspace = Dataspace.objects.get(pk=unquote_plus(pk))
    except Dataspace.DoesNotExist:
        return redirect(changelist_url)

    if not request.user.is_superuser or dataspace != request.user.dataspace:
        return redirect(changelist_url)

    if request.method == "POST":
        formset = TabPermissionsFormSet(request.POST)
        if formset.is_valid():
            formset.save(dataspace)
            formset.log_change(request, dataspace, "Changed tab permissions configuration.")
            messages.success(request, _("Tab permissions updated."))
        else:
            messages.error(request, _("Error, please refresh the page and try again."))
    else:
        initial = [{"group_name": group.name} for group in Group.objects.all()]
        formset = TabPermissionsFormSet(initial=initial)
        formset.load(dataspace)

    context = {
        "formset": formset,
        "object": dataspace,
        "opts": dataspace._meta,
    }

    return render(request, "admin/dje/dataspace/tab_permissions_form.html", context)


class APIWrapperPaginator(Paginator):
    """
    Force a `forced_number` to 1 to always end up with bottom=0 and top=self.per_page
    since we are not using a QuerySet but always a list of self.per_page-elements
    returned by the API.
    """

    def page(self, number):
        number = self.validate_number(number)
        forced_number = 1
        bottom = (forced_number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count
        return self._get_page(self.object_list[bottom:top], number, self)


class APIWrapperListView(
    PreviousNextPaginationMixin,
    ListView,
):
    paginate_by = 100
    paginator_class = APIWrapperPaginator

    def get_paginator(self, *args, **kwargs):
        Paginator = super().get_paginator(*args, **kwargs)
        Paginator.count = self.list_data.get("count", 0)
        return Paginator

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data.update(
            {
                "search_query": self.request.GET.get("q", ""),
                "template_list_table": self.template_list_table,
            }
        )
        return context_data


class NotificationsCountMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_notifications = self.request.user.notifications
        grouped = group_by_simple(self.object_list, "action_object_content_type")

        context.update(
            {
                "all_count": user_notifications.all().count(),
                "unread_count": user_notifications.unread().count(),
                "grouped_notifications": grouped,
            }
        )
        return context


class UnreadNotificationsList(
    NotificationsCountMixin,
    notifications_views.UnreadNotificationsList,
):
    pass


class AllNotificationsList(
    NotificationsCountMixin,
    notifications_views.AllNotificationsList,
):
    pass


class IntegrationsStatusView(
    LoginRequiredMixin,
    IsStaffMixin,
    TemplateView,
):
    template_name = "integrations_status.html"
    # Make sure additional integration have a `module.label` set
    # along the `is_configured` and `is_available` functions.
    integrations = [
        ScanCodeIO,
        PurlDB,
        VulnerableCode,
    ]

    def get_integration_status(self, integration_class):
        """
        Return the current status of the provided `integration_module`.
        Only check the availability if the integration is configured.
        """
        is_configured = False
        is_available = False
        error_log = ""

        integration = integration_class(user=self.request.user)

        if integration.is_configured():
            is_configured = True
            try:
                is_available = integration.is_available(raise_exceptions=True)
            except Exception as exception:
                error_log = str(exception)

        status = {
            "is_configured": is_configured,
            "is_available": is_available,
            "error_log": error_log,
        }

        if self.request.user.is_superuser:
            status["service_url"] = integration.service_url
            status["has_api_key"] = bool(integration.service_api_key)

        return status

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        integrations_status = {
            integration_class.label: self.get_integration_status(integration_class)
            for integration_class in self.integrations
        }

        context.update(
            {
                "integrations_status": integrations_status,
            }
        )
        return context


class ExportSPDXDocumentView(
    LoginRequiredMixin,
    DataspaceScopeMixin,
    GetDataspacedObjectMixin,
    BaseDetailView,
):
    def get(self, request, *args, **kwargs):
        spdx_document = outputs.get_spdx_document(self.get_object(), self.request.user)
        spdx_document_json = spdx_document.as_json()

        return outputs.get_attachment_response(
            file_content=spdx_document_json,
            filename=outputs.get_spdx_filename(spdx_document),
            content_type="application/json",
        )


class ExportCycloneDXBOMView(
    LoginRequiredMixin,
    DataspaceScopeMixin,
    GetDataspacedObjectMixin,
    BaseDetailView,
):
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        spec_version = self.request.GET.get("spec_version")

        cyclonedx_bom = outputs.get_cyclonedx_bom(instance, self.request.user)

        try:
            cyclonedx_bom_json = outputs.get_cyclonedx_bom_json(cyclonedx_bom, spec_version)
        except ValueError:
            raise Http404(f"Spec version {spec_version} not supported")

        return outputs.get_attachment_response(
            file_content=cyclonedx_bom_json,
            filename=outputs.get_cyclonedx_filename(instance),
            content_type="application/json",
        )
