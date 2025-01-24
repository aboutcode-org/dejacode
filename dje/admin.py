#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import csv
import operator
from collections import OrderedDict
from copy import copy
from functools import reduce

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.admin.sites import AdminSite
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import lookup_spawns_duplicates
from django.contrib.admin.utils import unquote
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.auth.views import LogoutView
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.contenttypes.models import ContentType
from django.core import checks
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import FieldError
from django.core.exceptions import PermissionDenied
from django.db import models
from django.forms.formsets import DELETION_FIELD_NAME
from django.http import HttpResponse
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.html import format_html
from django.utils.html import format_html_join
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.generic import RedirectView

from django_registration.backends.activation.views import RegistrationView

from dje.filters import IS_FILTER_LOOKUP_VAR
from dje.filters import CreatedByListFilter
from dje.filters import DataspaceFilter
from dje.filters import HistoryCreatedActionTimeListFilter
from dje.filters import HistoryModifiedActionTimeListFilter
from dje.filters import LimitToDataspaceListFilter
from dje.filters import MissingInFilter
from dje.forms import DataspaceAdminForm
from dje.forms import DataspacedAdminForm
from dje.forms import DejaCodeAuthenticationForm
from dje.importers import import_view
from dje.list_display import AsURL
from dje.mass_update import mass_update_action
from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.models import DejacodeUser
from dje.models import ExternalReference
from dje.models import ExternalSource
from dje.models import History
from dje.models import HistoryFieldsMixin
from dje.models import is_dataspace_related
from dje.notification import send_notification_email
from dje.notification import send_notification_email_on_queryset
from dje.permissions import get_protected_fields
from dje.search import advanced_search
from dje.utils import CHANGELIST_LINK_TEMPLATE
from dje.utils import class_wrap
from dje.utils import construct_changes_details_message
from dje.utils import get_previous_next
from dje.utils import group_by
from dje.utils import has_permission
from dje.utils import queryset_to_changelist_href
from dje.views import ActivityLog
from dje.views import clone_dataset_view
from dje.views import docs_models_view
from dje.views import manage_copy_defaults_view
from dje.views import manage_tab_permissions_view
from dje.views import object_compare_view
from dje.views import object_copy_view

EXTERNAL_SOURCE_LOOKUP = "external_references__external_source_id"

ADDITION = History.ADDITION
CHANGE = History.CHANGE
DELETION = History.DELETION


class DejaCodeAdminSite(AdminSite):
    login_template = "registration/login.html"
    login_form = DejaCodeAuthenticationForm
    site_title = _("DejaCode Administration")
    site_header = _("DejaCode Administration")
    index_title = _("DejaCode Administration")
    empty_value_display = ""

    def get_urls(self):
        """Override the admin:logout and admin:password_change views to the default ones."""
        urls = [
            path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
            path(
                "password_change/",
                RedirectView.as_view(url="/account/password_change/", permanent=True),
                name="password_change",
            ),
            path("docs/models/", docs_models_view, name="docs_models"),
        ]

        return urls + super().get_urls()


dejacode_site = DejaCodeAdminSite()


@admin.display(description="")
def get_hierarchy_link(obj):
    """Return a link to the Hierarchy view if the obj has at least 1 parent or 1 child."""
    if obj.has_parent_or_child():
        return format_html(
            '<a href="{}#hierarchy" target="_blank" class="hierarchy-icon"'
            ' title="Hierarchy">&nbsp;</a>',
            obj.get_absolute_url(),
        )


def get_additional_information_fieldset(pre_fields=None):
    fields = (
        "dataspace",
        "uuid",
        "created_date",
        "created_by",
        "last_modified_date",
        "last_modified_by",
    )

    if pre_fields:
        fields = pre_fields + fields

    return ("Additional Information", {"classes": ("grp-collapse grp-closed",), "fields": fields})


class ReferenceOnlyPermissions:
    def has_add_permission(self, request):
        """Limits the addition to Reference dataspace users."""
        perm = super().has_add_permission(request)
        return perm and request.user.dataspace.is_reference

    def has_change_permission(self, request, obj=None):
        """Limits the change to Reference dataspace users."""
        perm = super().has_change_permission(request, obj)
        return perm and request.user.dataspace.is_reference

    def has_delete_permission(self, request, obj=None):
        """Limits the deletion to Reference dataspace users."""
        perm = super().has_delete_permission(request, obj)
        return perm and request.user.dataspace.is_reference

    def has_view_permission(self, request, obj=None):
        perm = super().has_view_permission(request, obj)
        return perm and request.user.dataspace.is_reference


class DataspacedFKMixin:
    """
    Limit the QuerySet of ForeignKeys to the current Dataspace,
    or to the parent object in case of Inlines.
    On ADDITION, the Dataspace is taken from the User
    On MODIFICATION, it's taken on the current object instance or parent
    instance in case of Inlines.
    This class can be applied to ModelAdmins and Inlines.
    The declared limit_choices_to on the model field will be respected.
    """

    # The QuerySet for the fields in this list will be scoped by the Model content_type
    content_type_scope_fields = []

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        # If a QuerySet was given in the kwargs of the calling method, we then
        # assume that the filtering was done and we skip further processing.
        qs = kwargs.get("queryset", None)
        if qs is not None:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        related_model = db_field.related_model
        if is_dataspace_related(related_model):
            # No instance, ADDITION, get dataspace from user
            if not getattr(request, "_object", None):
                dataspace = request.user.dataspace
            # Parent instance, MODIFICATION, dataspace from instance
            else:
                dataspace = request._object.dataspace

            kwargs["queryset"] = db_field.related_model.objects.scope(dataspace).complex_filter(
                db_field.remote_field.limit_choices_to
            )

        if db_field.name in self.content_type_scope_fields:
            kwargs["queryset"] = kwargs["queryset"].filter(
                content_type=ContentType.objects.get_for_model(self.model)
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ProtectedFieldsMixin:
    def get_readonly_fields(self, request, obj=None):
        """Add field level permissions."""
        readonly_fields = super().get_readonly_fields(request, obj)

        protected_fields = get_protected_fields(self.model, request.user)
        if protected_fields:
            readonly_fields += tuple(protected_fields)

        return readonly_fields


class ChangelistPopupPermissionMixin:
    """
    Allow the changelist view access in popup mode for users without change permission.
    In the case of raw_id_fields feature, this view need be be available to select the related
    object.
    This mixin bypass the limitation in Django: https://code.djangoproject.com/ticket/11561
    Only the changelist is available, the form is never accessible.
    """

    def has_change_permission(self, request, obj=None):
        if obj is None and IS_POPUP_VAR in request.GET:
            return True
        return super().has_change_permission(request, obj)


class ProhibitDataspaceLookupMixin:
    """
    Prohibit all `dataspace` related lookups.
    Remove the possibility to look into other Dataspaces.
    """

    def lookup_allowed(self, lookup, value):
        if lookup.startswith("dataspace"):
            return False
        return super().lookup_allowed(lookup, value)

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        has_dataspace_filter = DataspaceFilter in self.list_filter

        if has_dataspace_filter:
            errors.append(
                checks.Error(f"Remove {DataspaceFilter} from {self}.list_filter", obj=self)
            )

        return errors

    def get_queryset(self, request):
        return super().get_queryset(request).scope_for_user(request.user)


class AdvancedSearchAdminMixin:
    def get_search_results(self, request, queryset, search_term):
        """Replace default search with advanced system."""
        use_distinct = False
        search_fields = self.get_search_fields(request)

        if search_fields and search_term:
            filters = []
            try:
                filters = advanced_search(search_term, search_fields)
            except FieldError as e:
                messages.error(request, e)
            except ValueError as e:
                messages.error(request, f"Search terms error: {e}")
            if filters:
                queryset = queryset.filter(filters)
                if not use_distinct:
                    for search_spec, __ in filters.children:
                        if lookup_spawns_duplicates(self.opts, search_spec):
                            use_distinct = True
                            break

        return queryset, use_distinct


class HistoryAdminMixin:
    def log_addition(self, request, object, change_message=None):
        history_entry = History.log_addition(request.user, object)

        if ADDITION in getattr(self, "email_notification_on", []):
            send_notification_email(request, object, ADDITION)

        return history_entry

    def log_change(self, request, object, message):
        """
        Add notification on object update.
        The notification system can be disabled by setting _disable_notification
        to True on the request.
        """
        serialized_data = getattr(request, "_serialized_data", None)
        history_entry = History.log_change(request.user, object, message, serialized_data)

        message = history_entry.get_change_message()
        disable_notification = getattr(request, "_disable_notification", False)
        if CHANGE in getattr(self, "email_notification_on", []) and not disable_notification:
            # Expending the base message with details
            changes_details = getattr(request, "changes_details", {})
            message += construct_changes_details_message(changes_details)
            send_notification_email(request, object, CHANGE, message)

        return history_entry

    def log_deletion(self, request, object, object_repr):
        """
        Log that an object will be deleted.
        Note that this method must be called before the deletion.
        """
        return History.log_deletion(request.user, object)

    def history_view(self, request, object_id, extra_context=None):
        response = super().history_view(request, object_id, extra_context)

        context_data = getattr(response, "context_data", None)
        if context_data:  # In case response is a HttpResponseRedirect
            obj = context_data["object"]

            history_qs = History.objects
            if is_dataspace_related(self.model):
                history_qs = history_qs.filter(object_dataspace__id=obj.dataspace_id)

            history_entries = (
                history_qs.filter(
                    object_id=unquote(object_id),
                    content_type=ContentType.objects.get_for_model(self.model),
                )
                .select_related()
                .order_by("-action_time")
            )

            obj_has_history_fields = isinstance(obj, HistoryFieldsMixin)
            if obj_has_history_fields:
                # Use the history fields from the model for the Addition entry.
                addition_entry = History(
                    action_time=obj.created_date,
                    user=obj.created_by,
                    change_message="Added.",
                )
                history_entries = history_entries.exclude(action_flag=History.ADDITION)
                history_entries = list(history_entries) + [addition_entry]

            response.context_data["action_list"] = history_entries

        return response


class ColoredIconAdminMixin:
    class Media:
        js = [
            "fontawesomefree/js/all.min.js",
        ]

    def colored_icon(self, obj):
        if obj.icon and obj.color_code:
            return obj.get_icon_as_html()


class DataspacedChangeList(ChangeList):
    def get_results(self, request):
        """
        Store the result_list ids in the session for the Previous and Next navigation button
        and "Save and go to next" feature.
        The session values are then used in the change_view() method of the ModelAdmin.

        Injects the preserved_filters on each object of the result_list to be used in
        list_display callable, as the request is not available there.
        Hierarchy links on ComponentAdmin and OwnerAdmin, as well as the annotation link
        on the LicenseAdmin requires this.
        This workaround could be removed once if the the following gets solved in Django:
        https://code.djangoproject.com/ticket/13659
        """
        super().get_results(request)
        for obj in self.result_list:
            obj._preserved_filters = self.preserved_filters
        self.set_reference_link(request)

    @property
    def has_filters_activated(self):
        return bool(self.get_filters_params())

    def get_filters_params(self, params=None):
        lookup_params = super().get_filters_params(params)
        if IS_FILTER_LOOKUP_VAR in lookup_params:
            del lookup_params[IS_FILTER_LOOKUP_VAR]
        return lookup_params

    def set_reference_link(self, request):
        """Add a 'View Reference Data' or 'View My Data 'link in the changelist header."""
        do_set_link = all(
            [
                DataspaceFilter in self.model_admin.list_filter,
                self.model_admin.lookup_allowed(DataspaceFilter.parameter_name, None),
                not self.is_popup,
            ]
        )

        if not do_set_link:
            return

        reference_dataspace = Dataspace.objects.get_reference()
        if reference_dataspace and reference_dataspace != request.user.dataspace:
            dataspace_id = request.GET.get(DataspaceFilter.parameter_name)
            if dataspace_id and dataspace_id != request.user.dataspace_id:
                self.my_dataspace_link = True
            else:
                params = f"?{DataspaceFilter.parameter_name}={reference_dataspace.id}"
                self.reference_params = params


class DataspacedAdmin(
    DataspacedFKMixin,
    ProtectedFieldsMixin,
    AdvancedSearchAdminMixin,
    HistoryAdminMixin,
    admin.ModelAdmin,
):
    formfield_overrides = {
        models.DateField: {"widget": AdminDateWidget(attrs={"placeholder": "YYYY-MM-DD"})},
    }
    list_filter = (DataspaceFilter,)
    readonly_fields = (
        "dataspace",
        "uuid",
    )
    actions = ["copy_to", "compare_with"]
    actions_to_remove = []
    email_notification_on = [ADDITION, CHANGE, DELETION]
    save_as = True

    # Display only the current count
    show_full_result_count = False

    # Display a warning if any of the identifier_fields has changed
    identifier_fields_warning = True

    # Default form, customized form should always extend DataspacedAdminForm
    form = DataspacedAdminForm

    # Using extended version of base templates to avoid code duplication
    change_form_template = "admin/change_form_extended.html"
    change_list_template = "admin/change_list_extended.html"

    # Set this to a BaseImporter extension of the Model to enable the import
    importer_class = None

    # Set this to a DejacodeMassUpdateForm to enable the mass update action
    mass_update_form = None

    # Set this to False to disable the Activity Log feature
    activity_log = True

    # Set this to True to enable the Previous and Next buttons in change view
    navigation_buttons = False

    preserve_filters = True

    # Do not display the View on site links by default
    # Set: view_on_site = DataspacedAdmin.changeform_view_on_site
    # for the default obj.get_absolute_url()
    view_on_site = False

    def __init__(self, model, admin_site):
        self.form.admin_site = admin_site
        super().__init__(model, admin_site)

    def check(self, **kwargs):
        errors = super().check(**kwargs)

        has_wrong_form_subclass = all(
            [
                not issubclass(self.form, DataspacedAdminForm),
                self.model._meta.unique_together != (("dataspace", "uuid"),),
            ]
        )

        if has_wrong_form_subclass:
            errors.extend(
                [checks.Error(f"{self.form} is not a subclass of {DataspacedAdminForm}", obj=self)]
            )

        return errors

    def changeform_view_on_site(self, obj):
        return obj.get_absolute_url()

    @admin.display(description=_("View"))
    def changelist_view_on_site(self, obj):
        return format_html('<a href="{}" target="_blank">View</a>', obj.get_absolute_url())

    @admin.display(description=_("URN"))
    def urn_link(self, instance):
        """Attach the URN link if URN is supported on the Model."""
        if instance.pk:
            return instance.urn_link
        return f"URN will be available once the {instance._meta.verbose_name} is saved."

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.scope_for_user_in_admin(request.user)

    def get_changelist(self, request, **kwargs):
        return DataspacedChangeList

    def get_list_filter(self, request):
        """Limit the availability of `MissingInFilter` to superusers."""
        list_filter = list(super().get_list_filter(request))

        if not request.user.is_superuser and MissingInFilter in list_filter:
            del list_filter[list_filter.index(MissingInFilter)]

        # Custom LogEntry-based filters when field not available on the model
        history_filters = {
            "created_by": CreatedByListFilter,
            "last_modified_by": None,
            "created_date": HistoryCreatedActionTimeListFilter,
            "last_modified_date": HistoryModifiedActionTimeListFilter,
        }

        for field_name, default_filter in history_filters.items():
            try:
                field = self.model._meta.get_field(field_name)
            except FieldDoesNotExist:
                if default_filter:
                    list_filter.append(default_filter)
                continue

            filtr = field_name
            if isinstance(field, models.ForeignKey):
                filtr = (field_name, LimitToDataspaceListFilter)
            list_filter.append(filtr)

        return list_filter

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)

        if issubclass(self.model, HistoryFieldsMixin):
            readonly_fields += (
                "created_date",
                "created_by",
                "last_modified_date",
                "last_modified_by",
            )

        return readonly_fields

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """
        Render the changelist using the current preserved filters to gather the
        previous and next id.
        """
        context = extra_context or {}

        # WARNING: request.GET is important as a condition since we do not want to run this
        # expensive operation in case no given filter/search/sort is applied.
        # For example when the admin form is reached directly from the user details view.
        if self.navigation_buttons and request.method == "GET" and request.GET:
            fake_request = copy(request)
            query_dict = fake_request.GET.copy()
            preserved_filters = query_dict.pop("_changelist_filters", "")
            if preserved_filters:
                preserved_filters = force_str(preserved_filters[0])
            fake_request.GET = QueryDict(preserved_filters)
            changelist_view = self.changelist_view(fake_request)

            # Sanity check, if the _changelist_filters were manually changed for example.
            if hasattr(changelist_view, "context_data"):
                # Do not use ".values_list('id', flat=True)" to avoid an extra query
                ids_list = [str(obj.id) for obj in changelist_view.context_data["cl"].result_list]
                previous_id, next_id = get_previous_next(ids_list, str(object_id))
                context.update(
                    {
                        "previous_id": previous_id,
                        "next_id": next_id,
                    }
                )

        if self.save_as and self.identifier_fields_warning:
            identifier_fields = self.model.get_identifier_fields()
            context["identifier_fields"] = identifier_fields

        return super().change_view(request, object_id, form_url, context)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        response = super().render_change_form(request, context, add, change, form_url, obj)
        # De-activating the 'Save as' option if the user is editing an Object
        # belonging to another Dataspace.
        # We are able to update the context_data at that point as the
        # TemplateResponse as not been rendered yet.
        if obj and obj.dataspace != request.user.dataspace:
            response.context_data["save_as"] = False
        return response

    @staticmethod
    def get_selected_ids_from_request(request, queryset):
        select_across = request.POST.get("select_across", 0)
        if int(select_across):
            # This is the "Selected all" case, we are using the all queryset
            object_ids = list(queryset.values_list("id", flat=True))
        else:
            object_ids = request.POST.getlist(ACTION_CHECKBOX_NAME)
        # Converting the ids list in a comma separated string, to be used
        # in the GET parameters
        return ",".join(str(id_) for id_ in object_ids)

    def base_action_with_redirect(self, request, queryset, viewname):
        ids = self.get_selected_ids_from_request(request, queryset)
        opts = self.model._meta
        preserved_filters = self.get_preserved_filters(request)
        view_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_{viewname}")
        url_with_params = "{}?{}".format(view_url, urlencode({"ids": ids}))
        redirect_url = add_preserved_filters(
            {"preserved_filters": preserved_filters, "opts": opts}, url_with_params
        )
        return redirect(redirect_url)

    @admin.display(description=_("Copy the selected objects"))
    def copy_to(self, request, queryset):
        """Copy the selected objects to another Dataspace."""
        return self.base_action_with_redirect(request, queryset, "copy")

    @admin.display(description=_("Compare the selected object"))
    def compare_with(self, request, queryset):
        """Compare one selected object with a matching object in another Dataspace."""
        return self.base_action_with_redirect(request, queryset, "compare")

    @admin.display(description=_("Check for updates in reference data"))
    def check_updates_in_reference(self, request, queryset):
        values = queryset.values_list("uuid", "last_modified_date")

        orm_lookups = [
            models.Q(**{"uuid": uuid, "last_modified_date__gt": last_modified_date})
            for uuid, last_modified_date in values
        ]

        return self.base_check_in_reference_action(request, self.model, orm_lookups)

    @admin.display(description=_("Check for newer versions in reference data"))
    def check_newer_version_in_reference(self, request, queryset):
        values = queryset.values_list("name", "version")

        orm_lookups = [
            models.Q(**{"name": name, "version__gt": version}) for name, version in values
        ]

        return self.base_check_in_reference_action(request, self.model, orm_lookups)

    @staticmethod
    def base_check_in_reference_action(request, model_class, orm_lookups):
        reference_dataspace = Dataspace.objects.get_reference()
        if not reference_dataspace or not orm_lookups:
            return

        updated_qs = model_class.objects.scope(reference_dataspace).filter(
            reduce(operator.or_, orm_lookups)
        )

        params = {DataspaceFilter.parameter_name: reference_dataspace.pk}
        changelist_href = queryset_to_changelist_href(updated_qs, params)
        if changelist_href:
            return redirect(changelist_href)

        messages.warning(request, "No updates available in the reference dataspace.")

    @staticmethod
    def get_changes_details(form):
        """
        Introspect a given form to collect the changes details.
        Original values are collected on the DB instance (pre-save value)
        and New values are collected on the form (post-save value)
        """
        if not form.instance.pk:
            return {}

        model_class = form.instance.__class__
        original_instance = model_class.objects.get(pk=form.instance.pk)

        changes_details = []
        # Using form.changed_data to only iterate on updated fields
        for field in form.changed_data:
            original_value = getattr(original_instance, field)
            new_value = getattr(form.instance, field)
            changes_details.append((field, original_value, new_value))

        return {form.instance: changes_details}

    def save_model(self, request, obj, form, change):
        """Set the created_by and last_modified_by fields at save time."""
        # This have no impact on save() if the model does not declare those fields.
        obj.last_modified_by = request.user
        if not change:
            obj.created_by = request.user

        # Injecting the results in the request for future use in the
        # log_change() method. This content will be used to add the changes
        # details into the notification message.
        # Using an OrderedDict to keep the main instance details first
        # The related objects changes (inlines) are gathered in
        # self.save_formset()
        request.changes_details = OrderedDict()
        if change and CHANGE in self.email_notification_on:
            request.changes_details.update(self.get_changes_details(form))

        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """
        Set the Dataspace on the Inline instance before it's saved. Using the
        Dataspace of the Model instance of this ModelAdmin.
        Also craft the change details of the Inlines.
        """
        for f in formset.forms:
            # Skip if nothing has changed in the current inline form
            if not f.changed_data:
                continue

            # Set the Dataspace on the Inline instance in case of addition of
            # the current inline.
            # The Dataspace is taken from the main form instance.
            if not f.instance.dataspace_id:
                f.instance.dataspace = form.instance.dataspace

            # Only in case of a 'change' on the main instance
            if change and CHANGE in self.email_notification_on:
                # As the `change` param is only about the main instance, we use
                # the pk of the inline instance to make sure we are in a
                # MODIFICATION case.
                #
                # If the pk of the inline instance is None, this is an ADDITION,
                # so skip the details creation.  Also, if DELETION_FIELD_NAME is
                # in changed_data, we are in an inline deletion case, skipping
                # too.
                if f.instance.pk and DELETION_FIELD_NAME not in f.changed_data:
                    # request.changes_details is created in self.save_model()
                    request.changes_details.update(self.get_changes_details(f))

        super().save_formset(request, form, formset, change)

    def delete_model(self, request, obj):
        # We are using this rather than self.log_deletion because it's not called
        # Here, History.log_deletion is called for  each object in the bulk.
        History.log_deletion(request.user, obj)
        super().delete_model(request, obj)
        if DELETION in self.email_notification_on:
            send_notification_email(request, obj, DELETION)

    def delete_queryset(self, request, queryset):
        """
        Add the email notification on bulk deletion through the default django
        'delete_selected' action.
        """
        send_notification_email_on_queryset(request, queryset, DELETION)
        super().delete_queryset(request, queryset)

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        urls = []

        if self.activity_log:
            urls += [
                path(
                    "activity_log/",
                    self.admin_site.admin_view(ActivityLog.as_view(model=self.model)),
                    name="{}_{}_activity_log".format(*info),
                )
            ]

        actions = getattr(self, "actions", [])
        actions_to_remove = getattr(self, "actions_to_remove", [])

        if "copy_to" in actions and "copy_to" not in actions_to_remove:
            urls += [
                path(
                    "copy/",
                    self.admin_site.admin_view(object_copy_view),
                    name="{}_{}_copy".format(*info),
                ),
            ]

        if "compare_with" in actions and "compare_with" not in actions_to_remove:
            urls += [
                path(
                    "compare/",
                    self.admin_site.admin_view(object_compare_view),
                    name="{}_{}_compare".format(*info),
                ),
            ]

        if self.importer_class:
            urls += [
                path(
                    "import/",
                    self.admin_site.admin_view(import_view),
                    {"importer_class": self.importer_class},
                    name="{}_{}_import".format(*info),
                ),
            ]

        return urls + super().get_urls()

    def get_form(self, request, obj=None, **kwargs):
        """
        Set the `obj` instance on the `request` for future processing.
        Set the serialized_data of the object on the `request` to be used in the
        `log_change` method.
        Set the `request` on the `form_class`.
        """
        if obj:
            request._object = obj
            request._serialized_data = obj.as_json()

        form_class = super().get_form(request, obj, **kwargs)
        form_class.request = request
        return form_class

    def get_fieldsets(self, request, obj=None):
        """Exclude form fields from the ADMIN_FORMS_CONFIGURATION settings."""
        fieldsets = super().get_fieldsets(request, obj)

        forms_config = settings.ADMIN_FORMS_CONFIGURATION
        if not forms_config:
            return fieldsets

        model_config = forms_config.get(self.model._meta.model_name, {})
        exclude = model_config.get("exclude", [])
        if not exclude:
            return fieldsets

        fieldsets_with_exclude = []
        for label, entry in fieldsets:
            fields = entry.get("fields")
            if fields:
                entry["fields"] = [field for field in fields if field not in exclude]
            fieldsets_with_exclude.append((label, entry))

        return fieldsets_with_exclude

    def get_inline_instances(self, request, obj=None):
        """Injects the ``request`` in each inline form to be used in validation."""
        base_instances = super().get_inline_instances(request, obj)

        instances = []
        request._object = obj
        for inline in base_instances:
            inline.form.request = request
            instances.append(inline)

        return instances

    def get_actions(self, request):
        """Limit the available actions based on who you are and what you are looking at."""
        if IS_POPUP_VAR in request.GET:
            return OrderedDict()

        actions = super().get_actions(request)
        is_user_dataspace = DataspaceFilter.parameter_name not in request.GET

        can_mass_update = all(
            [
                self.mass_update_form,
                has_permission(self.model, request.user, "change"),
                is_user_dataspace or request.user.dataspace.is_reference,
            ]
        )

        if can_mass_update:
            actions["mass_update"] = (mass_update_action, "mass_update", "Mass update")

        if not has_permission(self.model, request.user, "add") and "copy_to" in actions:
            del actions["copy_to"]

        if not request.user.dataspace.is_reference:
            if is_user_dataspace:  # The user is looking at his own Dataspace
                if "copy_to" in actions:
                    del actions["copy_to"]
                if "compare_with" in actions:
                    del actions["compare_with"]
            else:  # The user is looking at another Dataspace
                if "delete_selected" in actions:
                    del actions["delete_selected"]

        if request.user.dataspace.is_reference or not is_user_dataspace:
            if "check_updates_in_reference" in actions:
                del actions["check_updates_in_reference"]
            if "check_newer_version_in_reference" in actions:
                del actions["check_newer_version_in_reference"]

        for action in self.actions_to_remove:
            if action in actions:
                del actions[action]

        return actions

    @admin.display(description=_("Copy to my Dataspace"))
    def copy_link(self, obj):
        return format_html(
            '<strong><a href="{}&{}=1">{}</a></strong>',
            obj.get_copy_url(),
            IS_POPUP_VAR,
            _("Copy to my Dataspace"),
        )

    @staticmethod
    def hide_display_links(request):
        return all(
            [
                DataspaceFilter.parameter_name in request.GET,
                request.GET.get(DataspaceFilter.parameter_name) != str(request.user.dataspace_id),
            ]
        )

    def get_list_display(self, request):
        """
        Remove the view_on_site and hierarchy links in popup mode.
        Also insert the copy link when looking at another dataspace.
        """
        list_display = super().get_list_display(request)

        if IS_POPUP_VAR in request.GET:
            list_display = list(list_display)
            if "changelist_view_on_site" in list_display:
                list_display.remove("changelist_view_on_site")
            if get_hierarchy_link in list_display:
                list_display.remove(get_hierarchy_link)

        if self.hide_display_links(request):
            list_display = list(list_display)
            if "copy_to" not in self.actions_to_remove:
                list_display.insert(0, "copy_link")
            if get_hierarchy_link in list_display:
                list_display.remove(get_hierarchy_link)

        return list_display

    def get_list_display_links(self, request, list_display):
        """Remove all the display_links when looking at another dataspace."""
        if not self.hide_display_links(request):
            return super().get_list_display_links(request, list_display)

    def response_change(self, request, obj):
        """Add the logic for the "Save and go to next" feature."""
        next_id = request.POST.get("next_id")
        if "_next" in request.POST and next_id:
            opts = self.model._meta
            preserved_filters = self.get_preserved_filters(request)

            msg_dict = {
                "name": str(opts.verbose_name),
                "obj": str(obj),
            }
            msg = 'The {name} "{obj}" was changed successfully.'.format(**msg_dict)
            self.message_user(request, msg, messages.SUCCESS)

            viewname = f"admin:{opts.app_label}_{opts.model_name}_change"
            next_url = reverse(viewname, args=[next_id], current_app=self.admin_site.name)
            redirect_url = add_preserved_filters(
                {"preserved_filters": preserved_filters, "opts": opts}, next_url
            )
            return redirect(redirect_url)

        return super().response_change(request, obj)

    def lookup_allowed(self, lookup, value):
        if lookup in [EXTERNAL_SOURCE_LOOKUP]:
            return True
        return super().lookup_allowed(lookup, value)

    @staticmethod
    def _limited_permission(request, obj, has_perm):
        # Model permission
        if not has_perm:
            return False

        # Object instance permission
        if obj and obj.dataspace_id != request.user.dataspace_id:
            return request.user.dataspace.is_reference
        return True

    def has_add_permission(self, request):
        has_perm = super().has_add_permission(request)
        # Do not display the "Add" link in filter lookup popup mode
        if IS_FILTER_LOOKUP_VAR in request.GET:
            return False
        return has_perm

    def has_change_permission(self, request, obj=None):
        has_perm = super().has_change_permission(request, obj)
        return self._limited_permission(request, obj, has_perm)

    def has_delete_permission(self, request, obj=None):
        has_perm = super().has_delete_permission(request, obj)
        return self._limited_permission(request, obj, has_perm)

    def has_view_permission(self, request, obj=None):
        has_perm = super().has_view_permission(request, obj)
        return self._limited_permission(request, obj, has_perm)

    def has_importer(self):
        """Return True if the importer_class has been set."""
        if self.importer_class:
            return True

    def has_activity_log(self):
        """Return True if the activity_log has been set."""
        if self.activity_log:
            return True


class HiddenValueWidget(forms.TextInput):
    """Render a hidden value in the UI."""

    HIDDEN_VALUE = "*******"

    def render(self, name, value, attrs=None, renderer=None):
        value = self.HIDDEN_VALUE if value else None
        return super().render(name, value, attrs, renderer)


class DataspaceConfigurationForm(forms.ModelForm):
    """
    Configure Dataspace settings.

    This form includes fields for various API keys, with sensitive values
    hidden in the UI using the HiddenValueWidget.
    """

    hidden_value_fields = [
        "scancodeio_api_key",
        "vulnerablecode_api_key",
        "purldb_api_key",
    ]

    def __init__(self, *args, **kwargs):
        """Initialize the form and set HiddenValueWidget for specified fields."""
        super().__init__(*args, **kwargs)
        for field_name in self.hidden_value_fields:
            self.fields[field_name].widget = HiddenValueWidget()

    def clean(self):
        """Clean the form data, excluding hidden values from cleaned_data."""
        for field_name in self.hidden_value_fields:
            value = self.cleaned_data.get(field_name)
            if value == HiddenValueWidget.HIDDEN_VALUE:
                del self.cleaned_data[field_name]


class DataspaceConfigurationInline(DataspacedFKMixin, admin.StackedInline):
    model = DataspaceConfiguration
    form = DataspaceConfigurationForm
    verbose_name_plural = _("Configuration")
    verbose_name = _("Dataspace configuration")
    fields = [
        "homepage_layout",
        "scancodeio_url",
        "scancodeio_api_key",
        "vulnerablecode_url",
        "vulnerablecode_api_key",
        "vulnerabilities_risk_threshold",
        "purldb_url",
        "purldb_api_key",
    ]
    can_delete = False


@admin.register(Dataspace, site=dejacode_site)
class DataspaceAdmin(
    ReferenceOnlyPermissions,
    HistoryAdminMixin,
    admin.ModelAdmin,
):
    short_description = (
        "A Dataspace is an independent, exclusive set of DejaCode data, "
        "which can be either nexB reference data or installation-specific data."
    )

    long_description = (
        "Each DJE application User is associated with exactly one Dataspace, "
        "and the data owned by that Dataspace is presented to the user when "
        "accessing the application. "
        "An installation of DejaCode typically contains the following Dataspaces:"
        "nexB: Reference reference data from nexB"
        "{{mySite}}:  Production data for a specific DejaCode installation"
        "{{sandbox}}: Data for testing, training, or staging activities"
    )

    list_display = (
        "name",
        "full_name",
        AsURL("homepage_url", short_description="Homepage URL"),
        AsURL("contact_info", short_description="Contact information"),
    )
    fieldsets = (
        (
            "",
            {
                "fields": (
                    "name",
                    "homepage_url",
                    "notes",
                    "home_page_announcements",
                    "logo_url",
                )
            },
        ),
        (
            "Attribution Package Information",
            {
                "fields": (
                    "full_name",
                    "address",
                    "contact_info",
                    "open_source_information_url",
                    "open_source_download_url",
                )
            },
        ),
        (
            "User Interface Settings",
            {
                "fields": (
                    "show_license_profile_in_license_list_view",
                    "show_license_type_in_license_list_view",
                    "show_spdx_short_identifier_in_license_list_view",
                    "show_usage_policy_in_user_views",
                    "show_type_in_component_list_view",
                    "hide_empty_fields_in_component_details_view",
                )
            },
        ),
        (
            "Application Process Settings",
            {
                "fields": (
                    "set_usage_policy_on_new_component_from_licenses",
                    "enable_package_scanning",
                    "update_packages_from_scan",
                    "enable_purldb_access",
                    "enable_vulnerablecodedb_access",
                )
            },
        ),
    )
    search_fields = ("name",)
    inlines = [DataspaceConfigurationInline]
    form = DataspaceAdminForm
    change_form_template = "admin/dje/dataspace/change_form.html"
    change_list_template = "admin/change_list_extended.html"

    def has_change_permission(self, request, obj=None):
        """
        Bypass the ReferenceOnlyPermissions to allow regular Dataspace admins,
        with the right permission, to edit their own Dataspace.
        """
        return super(admin.ModelAdmin, self).has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        """Make Dataspace.name field readonly on edit except for reference Dataspace superusers."""
        readonly_fields = super().get_readonly_fields(request, obj)

        user = request.user
        if obj and not (user.dataspace.is_reference and user.is_superuser):
            readonly_fields += ("name",)

        return readonly_fields

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name

        urls = [
            path(
                "<pk>/clonedataset/",
                self.admin_site.admin_view(clone_dataset_view),
                name="{}_{}_clonedataset".format(*info),
            ),
            path(
                "<pk>/tab_permissions/",
                self.admin_site.admin_view(manage_tab_permissions_view),
                name="{}_{}_tab_permissions".format(*info),
            ),
            path(
                "<pk>/copy_defaults/",
                self.admin_site.admin_view(manage_copy_defaults_view),
                name="{}_{}_copy_defaults".format(*info),
            ),
        ]

        return urls + super().get_urls()

    def get_queryset(self, request):
        """
        Limit the QuerySet to the current user Dataspace. + the Reference one.
        If the user Dataspace is the Reference then show all.
        """
        qs = super().get_queryset(request)
        if not request.user.dataspace.is_reference:
            qs = qs.filter(id=request.user.dataspace_id)
        return qs

    def get_actions(self, request):
        """Remove the bulk delete action, it does not make sense for Dataspace."""
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["template_dataspace"] = settings.TEMPLATE_DATASPACE
        return super().changeform_view(request, object_id, form_url, extra_context)


class ChildRelationshipInline(DataspacedFKMixin, admin.TabularInline):
    fk_name = "parent"
    extra = 0
    classes = ("grp-collapse grp-open",)
    raw_id_fields = ("child",)
    autocomplete_lookup_fields = {"fk": ["child"]}
    verbose_name = _("Child")


class ExternalReferenceInline(DataspacedFKMixin, GenericTabularInline):
    model = ExternalReference
    extra = 0
    classes = ("grp-collapse grp-open",)


@admin.register(ExternalSource, site=dejacode_site)
class ExternalSourceAdmin(DataspacedAdmin):
    def references(self, obj):
        """
        Return links to the content_object changelist of ExternalReference instances,
        for the given ExternalSource instance, grouped per ContentType.
        """
        changelist_links = []
        queryset = obj.externalreference_set
        grouped = group_by(queryset, "content_type", count_on="object_id", distinct=True)

        for value in grouped:
            model_class = ContentType.objects.get(id=value["content_type"]).model_class()
            opts = model_class._meta
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            params = {EXTERNAL_SOURCE_LOOKUP: obj.id}
            href = f"{url}?{urlencode(params)}"
            changelist_link = format_html(
                CHANGELIST_LINK_TEMPLATE, href, value["count"], opts.verbose_name_plural
            )
            changelist_links.append([changelist_link])

        html_list = "<ul>{}</ul>".format(format_html_join("", "<li>{}</li>", changelist_links))
        return class_wrap(html_list, "width200")

    list_display = (
        "label",
        AsURL("homepage_url", short_description="Homepage URL"),
        "notes",
        "references",
    )
    search_fields = ("label",)
    list_filter = DataspacedAdmin.list_filter + (MissingInFilter,)
    activity_log = False

    short_description = (
        "An External source identifies a source for additional information "
        "about a DejaCode application object, such as component metadata, "
        "original license text and commentary, or detailed information about "
        "an organization."
    )

    long_description = (
        "Other examples of an external source include a repository (forge) of "
        "components available for download, or an information resource of "
        "security and quality alerts about components, or detailed discussions "
        "about the interpretation of a license."
    )


def send_activation_email(user, request):
    """Send the activation email re-using the logic from RegistrationView."""
    registration_view = RegistrationView()
    registration_view.request = request

    activation_key = registration_view.get_activation_key(user)
    context = registration_view.get_email_context(activation_key)
    context.update({"user": user})
    subject = render_to_string(registration_view.email_subject_template, context)
    message = render_to_string(registration_view.email_body_template, context)
    user.email_user(subject, message, settings.DEFAULT_FROM_EMAIL)


class DejacodeUserChangeForm(forms.ModelForm):
    class Meta:
        model = DejacodeUser
        exclude = ("password",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class DejacodeUserCreationForm(DejacodeUserChangeForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        user.set_unusable_password()
        if commit:
            user.save()
        return user


@admin.register(DejacodeUser, site=dejacode_site)
class DejacodeUserAdmin(
    DataspacedFKMixin,
    AdvancedSearchAdminMixin,
    HistoryAdminMixin,
    UserAdmin,
):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "data_email_notification",
        "workflow_email_notification",
        "updates_email_notification",
        "vulnerability_impact_notification",
        "company",
        "last_login",
        "last_api_access",
        "date_joined",
        "dataspace",
    )
    list_filter = (
        "dataspace",
        "date_joined",
        "last_login",
        "last_api_access",
        "is_active",
        "is_staff",
        "is_superuser",
    )
    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
    )
    add_fieldsets = (
        (None, {"fields": ("username", "dataspace")}),
        (_("Personal information"), {"fields": ("email", "first_name", "last_name", "company")}),
        (_("Profile"), {"fields": ("homepage_layout",)}),
        (
            _("Notifications"),
            {
                "fields": (
                    "data_email_notification",
                    "workflow_email_notification",
                    "updates_email_notification",
                    "vulnerability_impact_notification",
                )
            },
        ),
        (_("Permissions"), {"fields": ("is_staff", "is_superuser", "groups")}),
    )
    fieldsets = add_fieldsets[:-1] + (
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        (_("Important dates"), {"fields": ("last_login", "last_api_access", "date_joined")}),
    )
    form = DejacodeUserChangeForm
    add_form = DejacodeUserCreationForm
    change_list_template = "admin/change_list_extended.html"
    add_form_template = "admin/dje/dejacode_user/change_form.html"
    change_form_template = add_form_template
    activity_log = True
    readonly_fields = ("last_login", "last_api_access", "date_joined")
    actions = [
        "set_inactive",
        "export_as_csv",
    ]

    short_description = (
        "Users refer to the application users that can log on to the application. "
        "It is required to associate each User with a Dataspace, since this will "
        "provide a default value for various application work flows."
    )

    activation_email_msg = _("An activation email will be sent shortly to the email address.")

    def get_form(self, request, obj=None, **kwargs):
        """
        Remove the add_related links for the group and dataspace fields.
        Injects link to the group details in the group label and help_text.
        """
        form = super().get_form(request, obj, **kwargs)
        dataspace_widget = form.base_fields["dataspace"].widget
        dataspace_widget.can_add_related = False
        dataspace_widget.can_change_related = False
        dataspace_widget.can_delete_related = False

        groups_field = form.base_fields["groups"]
        groups_field.widget.can_add_related = False

        permission_details_url = reverse("admin:auth_group_permission_details")
        label_template = (
            '{} <a href="{}" target="_blank" class="group-details-link">  (permission details)</a>'
        )
        groups_field.label = format_html(label_template, groups_field.label, permission_details_url)

        return form

    def get_queryset(self, request):
        """Scope the QuerySet to the current user Dataspace."""
        qs = super().get_queryset(request)
        user_dataspace = request.user.dataspace
        if not user_dataspace.is_reference:
            qs = qs.scope(user_dataspace)
        return qs

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """
        Limit the choices of the ForeignKey based on the user dataspace.
        Note that we could use the DataspacedFKMixin here, but we would
        loose the ability to set the initial value.
        """
        if db_field.related_model is Dataspace:
            user_dataspace = request.user.dataspace
            if not user_dataspace.is_reference:
                queryset = Dataspace.objects.filter(pk=user_dataspace.pk)
                return forms.ModelChoiceField(queryset=queryset, initial=user_dataspace)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def user_change_password(self, request, id, form_url=""):
        """
        Remove the possibility to force a new password on a User.
        A Logged-in User can change his password from /account/password_change/
        If lost, recovery system available at /account/password_reset/
        """
        raise PermissionDenied

    def get_list_filter(self, request):
        """
        Remove the possibility of filtering by dataspace if current logged user
        is not part of the reference dataspace.
        We have to take this approach of "removing" the feature rather than
        "adding" it as the BaseModelAdmin.lookup_allowed() method is still using
        the  self.list_filter where it should call self.get_list_filter()
        instead.
        See #7828 and https://code.djangoproject.com/ticket/17646
        """
        list_filter = super().get_list_filter(request)
        if not request.user.dataspace.is_reference:
            list_filter = list(list_filter)
            list_filter.remove("dataspace")
        return list_filter

    def has_activity_log(self):
        """Return True if the activity_log has been set."""
        if self.activity_log:
            return True

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name

        urls = [
            path(
                "activity_log/",
                self.admin_site.admin_view(ActivityLog.as_view(model=self.model)),
                name="{}_{}_activity_log".format(*info),
            ),
            path(
                "<path:object_id>/send_activation_email/",
                self.admin_site.admin_view(self.send_activation_email),
                name="{}_{}_send_activation_email".format(*info),
            ),
        ]

        return urls + super().get_urls()

    def log_addition(self, request, object, change_message=None):
        send_activation_email(object, request)
        self.message_user(request, self.activation_email_msg, messages.SUCCESS)
        return super().log_addition(request, object, change_message)

    def delete_model(self, request, obj):
        """
        Instead of deleting the User, makes it inactive.
        Additionally, set the user's password to an unusable value.
        """
        obj.data_email_notification = False
        obj.workflow_email_notification = False
        obj.is_active = False
        obj.set_unusable_password()
        obj.save()
        History.log_change(request.user, obj, "Set as inactive.")

    def get_actions(self, request):
        """
        Remove the bulk delete action as this kind of delete bypass the
        ModelAdmin model_delete() methods where the is_active is set to None.
        """
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        if "export_as_csv" in actions and not request.user.is_superuser:
            del actions["export_as_csv"]
        return actions

    @admin.display(description=_("Set selected users as inactive"))
    def set_inactive(self, request, queryset):
        # Execute before the `update()` or the QuerySet will be empty
        for obj in queryset:
            History.log_change(request.user, obj, "Set as inactive.")

        count = queryset.update(
            is_active=False,
            data_email_notification=False,
            workflow_email_notification=False,
        )
        self.message_user(request, f"{count} users set as inactive.", messages.SUCCESS)

    @admin.display(description=_("Export selected users as CSV"))
    def export_as_csv(self, request, queryset):
        fieldnames = [
            "username",
            "first_name",
            "last_name",
            "email",
            "company",
            "dataspace",
            "is_active",
            "is_staff",
            "is_superuser",
            "data_email_notification",
            "workflow_email_notification",
            "date_joined",
            "last_login",
            "last_api_access",
            "groups",
        ]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="dejacode_user_export.csv"'

        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()

        # We could use `values(*fieldnames)` but  m2m are not properly supported by `values()`
        for user in queryset.all():
            user_data = {}
            for field in fieldnames:
                if field == "groups":
                    value = ", ".join(user.get_group_names())
                else:
                    value = getattr(user, field, "")
                user_data[field] = str(value)
            writer.writerow(user_data)

        return response

    def send_activation_email(self, request, object_id):
        """
        Set the User inactive a send an activation link to the email address.
        See also registration.admin.RegistrationAdmin.resend_activation_email
        """
        if not self.has_change_permission(request):
            raise PermissionDenied

        user = get_object_or_404(self.get_queryset(request), pk=unquote(object_id))
        # User needs to be de-activated for the activation_key to work.
        # Also needs a unusable_password for the proper redirection.
        # See ActivationView.get_user() for implementation details.
        user.is_active = False
        user.set_unusable_password()
        user.save()
        send_activation_email(user, request)
        self.message_user(request, self.activation_email_msg, messages.SUCCESS)
        return self.response_post_save_change(request, obj=user)


@admin.register(Group, site=dejacode_site)
class GroupAdmin(ReferenceOnlyPermissions, HistoryAdminMixin, GroupAdmin):
    short_description = (
        "A Group is a collection of application access permissions that control "
        "add, change, mass update, and delete of specific application objects."
    )
    long_description = (
        "A Group typically aligns with User business roles. For example, you "
        "can assign specific permissions to Engineering, Legal, and Data "
        "Administration Groups to allow access to the application pages "
        "appropriate to their business roles. Once Groups are defined, you "
        "can assign one or more Groups to each User."
    )
    allowed_action = (
        "add",
        "change",
        "delete",
        "view",
    )
    allowed_app_label = (
        "component_catalog",
        "license_library",
        "dje",
        "organization",
        "policy",
        "product_portfolio",
        "reporting",
        "workflow",
    )
    list_display = (
        "name",
        "get_permissions",
    )
    change_list_template = "admin/dje/group/change_list.html"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("permissions")

    @admin.display(description=_("Permissions"))
    def get_permissions(self, obj):
        return format_html("<br>".join(obj.permissions.values_list("name", flat=True)))

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """Limit the available Permissions."""
        form_field = super().formfield_for_manytomany(db_field, request, **kwargs)

        if db_field.name == "permissions":
            # Using `codename` as the `name` may be truncated
            action_queries = [
                models.Q(**{"codename__startswith": action}) for action in self.allowed_action
            ]

            form_field.queryset = form_field.queryset.filter(
                reduce(operator.or_, action_queries),
                content_type__app_label__in=self.allowed_app_label,
            )

        return form_field

    def get_urls(self):
        opts = self.model._meta
        urls = [
            path(
                "details/",
                self.admin_site.admin_view(self.permission_details_view),
                name=f"{opts.app_label}_{opts.model_name}_permission_details",
            ),
            path(
                "export_csv/",
                self.admin_site.admin_view(self.permission_export_csv),
                name=f"{opts.app_label}_{opts.model_name}_permission_export_csv",
            ),
        ]
        return urls + super().get_urls()

    @staticmethod
    def get_permission_group_mapping():
        group_qs = Group.objects.order_by("name")

        permission_qs = Permission.objects.filter(group__isnull=False).prefetch_related("group_set")

        permission_group = {}
        for perm in permission_qs:
            associated_groups = perm.group_set.values_list("name", flat=True)
            row = ["X" if group.name in associated_groups else "" for group in group_qs]
            perm_clean_name = perm.name.replace("Can ", "")
            permission_group[perm_clean_name] = row

        return group_qs, permission_group

    def permission_details_view(self, request):
        """Available in the User admin form, in the Groups section."""
        group_qs, permission_group = self.get_permission_group_mapping()
        context = {
            "groups": group_qs,
            "permission_group": permission_group,
        }
        return TemplateResponse(request, "admin/dje/group/groups_details.html", context)

    def permission_export_csv(self, request):
        group_qs, permission_group = self.get_permission_group_mapping()

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="dejacode_group_permission.csv"'

        csv_writer = csv.writer(response, dialect="excel")
        csv_writer.writerow([""] + list(group_qs.values_list("name", flat=True)))
        for perm_name, row in permission_group.items():
            csv_writer.writerow([perm_name] + row)

        return response


def register_axes_admin():
    from axes.admin import AccessAttemptAdmin
    from axes.models import AccessAttempt

    @admin.register(AccessAttempt, site=dejacode_site)
    class ReferenceAccessAttemptAdmin(ReferenceOnlyPermissions, AccessAttemptAdmin):
        pass


if settings.AXES_ENABLED:
    register_axes_admin()
