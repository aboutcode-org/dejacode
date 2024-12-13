#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import logging
import operator
import uuid
from collections import defaultdict
from contextlib import suppress
from functools import reduce
from itertools import groupby
from operator import attrgetter

from django.apps import apps
from django.conf import settings
from django.contrib.admin.models import ADDITION
from django.contrib.admin.models import CHANGE
from django.contrib.admin.models import DELETION
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core import checks
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.core.serializers import serialize
from django.core.serializers.base import SerializationError
from django.core.validators import EMPTY_VALUES
from django.db import models
from django.dispatch import receiver
from django.forms.utils import flatatt
from django.template.defaultfilters import capfirst
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.html import smart_urlquote
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from notifications.models import Notification
from rest_framework.authtoken.models import Token

from dje.fields import LastModifiedByField
from dje.tasks import send_mail_task

logger = logging.getLogger("dje")


DATASPACE_FIELD_HELP_TEXT = _(
    "A Dataspace is an independent, exclusive set of DejaCode data, which can be"
    " either nexB master reference data or installation-specific data."
)

# PackageURL._fields
PURL_FIELDS = ("type", "namespace", "name", "version", "qualifiers", "subpath")


def is_dataspace_related(model_class):
    """
    Return True if the given model_class has a ForeignKey field related to
    the Dataspace model.
    """
    return any(
        1
        for f in model_class._meta.get_fields()
        if f.many_to_one and (f.related_model == Dataspace or f.related_model == "dje.Dataspace")
    )


def is_content_type_related(model_class):
    """
    Return True if the given model_class has a ForeignKey field related to
    the ContentType model.
    """
    return any(
        1
        for field in model_class._meta.get_fields()
        if field.many_to_one and field.related_model == ContentType
    )


class DataspaceManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)

    def get_reference(self):
        """
        Return the reference Dataspace of the instance or None.

        Return the default reference Dataspace if not configured or
        configured with an empty or None Dataspace name.

        Return None if configured with a non-existing Dataspace name.

        The reference Dataspace is configured with the setting REFERENCE_DATASPACE
        set with the name of an existing Dataspace.
        The default reference Dataspace name is "nexB".
        """
        reference_name = settings.REFERENCE_DATASPACE
        if not reference_name:
            # Force "nexB" if the setting is set with an empty string or None
            reference_name = "nexB"

        with suppress(models.ObjectDoesNotExist):
            return self.get(name=reference_name)


class Dataspace(models.Model):
    """
    The Dataspace is a way to keep data for each organization data
    separated and still store them in the same database, schema or table.
    Therefore the Dataspace is part of the primary key of most models
    and it part of a unicity constraint for these models.
    For a given installation there can be several Owner Org defined, but only
    one reference.

    This is an important concept used throughout DejaCode to
    separate the reference data provided by nexB from the data used in a given
    installation of DJE.

    It is essentially a notion of tenant in a DJE installation and is used to
    segregate org-specific and/or org-private records enabling both
    multi-tenancy as well as nexB-provided reference data and org-specific or
    customized data.

    This separation has several purposes such as allowing:
     * orderly and simpler data update from the nexB reference data and inter
     Dataspace data exchange
     * Dataspace specific data customizations (for instance license
     tags configurations or some preferences)
     * multi-tenancy where different organizations can share the same DJE
     instance
    """

    uuid = models.UUIDField(
        _("UUID"),
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )

    name = models.SlugField(
        unique=True,
        max_length=20,
        help_text=_(
            'Unique name of a Dataspace. The name "nexB" is reserved for '
            "the creators/maintainers of the system software. Dataspace name "
            "only allows letters, numbers, underscores and hyphens."
        ),
    )

    homepage_url = models.URLField(
        _("Homepage URL"),
        max_length=1024,
        blank=True,
        help_text=_("The homepage URL of the Dataspace owner."),
    )

    contact_info = models.CharField(
        _("Contact information"),
        max_length=500,
        blank=True,
        help_text=_(
            "A dedicated email address or URL for contacting the owner of "
            "the Dataspace. Can be used for Attribution Package generation."
        ),
    )

    notes = models.TextField(
        blank=True,
        help_text=_("Extended Notes about a Dataspace."),
    )

    show_license_profile_in_license_list_view = models.BooleanField(
        default=False,
        verbose_name=format_lazy(
            "Show {license_profile} in license list view",
            license_profile=_("license profile"),
        ),
        help_text=format_lazy(
            "When true (checked), include the {license_profile} column in the license list view.",
            license_profile=_("license profile"),
        ),
    )

    show_license_type_in_license_list_view = models.BooleanField(
        default=True,
        help_text=_(
            "When true (checked), include the license type column in the license list view.",
        ),
    )

    show_spdx_short_identifier_in_license_list_view = models.BooleanField(
        verbose_name=_("show SPDX short identifier in license list view"),
        default=False,
        help_text=_(
            "When true (checked), include the SPDX short identifier in the license list view.",
        ),
    )

    show_usage_policy_in_user_views = models.BooleanField(
        default=True,
        help_text=_(
            "When true (checked), include the usage policy in user views that "
            "show licenses or components.",
        ),
    )

    show_type_in_component_list_view = models.BooleanField(
        default=False,
        help_text=_(
            "When true (checked), include the type column in the component list view.",
        ),
    )

    hide_empty_fields_in_component_details_view = models.BooleanField(
        default=False,
        help_text=_("When true (checked), hide empty fields in the component details view."),
    )

    set_usage_policy_on_new_component_from_licenses = models.BooleanField(
        _("set usage policy on component or package from license policy"),
        default=False,
        help_text=_(
            "When true (checked), the application will automatically assign a usage "
            "policy to a component or package when its license expression is set or "
            "updated when you create, import, edit, or copy that component or package, "
            "based on the associated policies that you have defined on the license policy."
        ),
    )

    logo_url = models.URLField(
        _("Logo URL"),
        max_length=1024,
        blank=True,
        help_text=_("URL to a Dataspace Logo. If set, it will be included in reports."),
    )

    full_name = models.CharField(
        max_length=100,
        blank=True,
        help_text=_(
            "The full name of the Dataspace organization. "
            "Can be used for Attribution Package generation."
        ),
    )

    address = models.TextField(
        blank=True,
        help_text=(
            "The address of the Dataspace organization. "
            "Can be used for Attribution Package generation."
        ),
    )

    open_source_information_url = models.URLField(
        _("Open Source Information URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "A public URL where you publish information about the Dataspace "
            "organization's Open Source policies and procedures. "
            "Can be used for Attribution Package generation."
        ),
    )

    open_source_download_url = models.URLField(
        _("Open Source Download URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "A public URL where you provide copies of Open Source software that "
            "require Redistribution when you use them in your products. Can be "
            "used for Attribution Package generation."
        ),
    )

    home_page_announcements = models.TextField(
        blank=True,
        help_text=_(
            "Use this field to enter text to appear on the DejaCode home page, "
            "normally for the purpose of providing your user community with "
            "general-purpose announcements about using DejaCode. "
            "Note that you can include URL's in the text if you want to direct "
            "users to detailed instructions and announcements."
        ),
    )

    enable_package_scanning = models.BooleanField(
        default=False,
        help_text=_(
            'When true (checked), allows a user to click the "Scan Package" button when viewing '
            "a Package, initiating a call to ScanCode.io to scan the Package based on its URL. "
            "This setting also activates a DejaCode feature to submit any Package created using "
            'the "Add Package" button to ScanCode.io for scanning, and it activates the Scans '
            "choice from the DejaCode Tools dropdown menu."
        ),
    )

    update_packages_from_scan = models.BooleanField(
        _("Update packages automatically from scan"),
        default=False,
        help_text=_(
            "When true (checked), enables an automatic DejaCode process to update "
            "selected Package fields (such as license expression, primary language, "
            "copyright, etc.) when a package scan is completed, depending on the "
            "quality of the scan results."
        ),
    )

    enable_purldb_access = models.BooleanField(
        _("Enable PurlDB access"),
        default=False,
        help_text=_(
            "When true (checked), enables user access to the PurlDB option from the Tools menu, "
            "which presents a list of PurlDB data mined and scanned automatically from multiple "
            "public sources. Users can view PurlDB details and can create DejaCode Package "
            "definitions using those details, and DejaCode also presents a new PurlDB tab when "
            "viewing the details of a Package with matching key values. This option also enhances "
            "the Global Search feature to extend the search scope beyond the standard DejaCode "
            "objects (Packages, Components, Licenses, Owners) and perform an asynchronous query of "
            "the PurlDB to find relevant data."
        ),
    )

    enable_vulnerablecodedb_access = models.BooleanField(
        _("Enable VulnerableCodeDB access"),
        default=False,
        help_text=_(
            "When true (checked), authorizes DejaCode to access the VulnerableCodeDB "
            "using a Package URL (purl) to determine if there are any reported "
            "vulnerabilities for a specific Package and return the Vulnerability ID "
            "and related URLs to a Vulnerabilities tab in the Package details user "
            "view."
        ),
    )

    vulnerabilities_updated_at = models.DateTimeField(
        _("Last vulnerability data update"),
        auto_now=False,
        null=True,
        blank=True,
        help_text=_("The date and time when the local vulnerability database was last updated. "),
    )

    objects = DataspaceManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_admin_url(self):
        opts = self._meta
        viewname = f"admin:{opts.app_label}_{opts.model_name}_change"
        return reverse(viewname, args=[self.pk])

    def natural_key(self):
        return (self.name,)

    @cached_property
    def is_reference(self):
        """Return True if this Dataspace is the reference."""
        reference = self.__class__._default_manager.get_reference()
        return True if reference and self == reference else False

    def get_configuration(self, field_name=None):
        """
        Return the associated DataspaceConfiguration.
        If a `field_name` is provided, Return the value for that field from
        the `DataspaceConfiguration`.
        """
        try:
            configuration = self.configuration
        except ObjectDoesNotExist:
            return

        if field_name:
            return getattr(configuration, field_name, None)
        return configuration

    @property
    def has_configuration(self):
        """Return True if an associated DataspaceConfiguration instance exists."""
        return bool(self.get_configuration())

    @property
    def tab_permissions_enabled(self):
        return bool(self.get_configuration("tab_permissions"))


class DataspaceConfiguration(models.Model):
    dataspace = models.OneToOneField(
        to="dje.Dataspace",
        on_delete=models.CASCADE,
        related_name="configuration",
    )

    tab_permissions = models.JSONField(
        blank=True,
        default=dict,
    )

    copy_defaults = models.JSONField(
        blank=True,
        null=True,
    )

    homepage_layout = models.ForeignKey(
        to="reporting.CardLayout",
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.CASCADE,
        serialize=False,
        help_text=_(
            "Select a general purpose Card layout that provides timely query "
            "results on the DejaCode homepage to your application users."
        ),
    )

    scancodeio_url = models.URLField(
        _("ScanCode.io URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "Enter the URL of your organization's private ScanCode.io instance, "
            "if available. If not, DejaCode will use the public ScanCode.io instance "
            "to scan your Packages."
        ),
    )

    scancodeio_api_key = models.CharField(
        _("ScanCode.io API key"),
        max_length=40,
        blank=True,
        help_text=_(
            "If your organization's private ScanCode.io instance requires an API key "
            "for access, provide it here. Otherwise, you can leave this field empty."
        ),
    )

    vulnerablecode_url = models.URLField(
        _("VulnerableCode URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "If your organization has a private VulnerableCode instance, enter its URL "
            "here. Otherwise, DejaCode will use the public VulnerableCode to check for "
            "vulnerabilities"
        ),
    )

    vulnerablecode_api_key = models.CharField(
        _("VulnerableCode API key"),
        max_length=40,
        blank=True,
        help_text=_(
            "If your private VulnerableCode instance requires an API key for access, "
            "input it here. If not, you can leave this field blank."
        ),
    )

    purldb_url = models.URLField(
        _("PurlDB URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "Enter the URL of your organization's private PurlDB instance, if "
            "applicable. If not, DejaCode will utilize the public PurlDB to offer a "
            "database of Packages collected from public sources."
        ),
    )

    purldb_api_key = models.CharField(
        _("PurlDB API key"),
        max_length=40,
        blank=True,
        help_text=_(
            "If your organization's private PurlDB instance requires an API key for "
            "access, provide it here. If not, you can leave this field empty."
        ),
    )

    def __str__(self):
        return f"Configuration for {self.dataspace}"


class DataspacedQuerySet(models.QuerySet):
    """
    QuerySet for the DataspacedModel to be used on the Models as
    DataspacedManager (using Manager.from_queryset)

    Provide filters related to the Dataspace system.
    """

    def get_by_natural_key(self, dataspace_name, uuid):
        return self.get(dataspace__name=dataspace_name, uuid=uuid)

    def scope(self, dataspace, include_reference=False):
        """
        Limit the QuerySet results to the provided `dataspace`.
        The reference Dataspace results can be included using the
        `include_reference` argument.
        When a string is provided for `dataspace` in place of a Dataspace
        instance, the `scope_by_name` method will be called.
        """
        if type(dataspace) is str:
            return self.scope_by_name(dataspace_name=dataspace)

        dataspaces = {dataspace}
        if include_reference:
            reference = Dataspace.objects.get_reference()
            if reference:
                dataspaces.add(reference)

        return self.filter(dataspace__in=dataspaces)

    def scope_by_name(self, dataspace_name):
        return self.filter(dataspace__name=dataspace_name)

    def scope_by_id(self, dataspace_id):
        return self.filter(dataspace__id=dataspace_id)

    def scope_for_user(self, user):
        return self.filter(dataspace=user.dataspace)

    def scope_for_user_in_admin(self, user):
        # Used in DataspacedAdmin.get_queryset()
        if user.dataspace.is_reference:
            return self  # no filtering
        return self.scope(user.dataspace, include_reference=True)

    def get_or_none(self, *args, **kwargs):
        """Return a single object matching the given keyword arguments, `None` otherwise."""
        with suppress(self.model.DoesNotExist, ValidationError):
            return self.get(*args, **kwargs)

    def group_by(self, field_name):
        """Return a dict of QS instances grouped by the given `field_name`."""
        # Not using a dict comprehension to support QS without `.order_by(field_name)`.
        grouped = defaultdict(list)

        for field_value, group in groupby(self, attrgetter(field_name)):
            grouped[field_value].extend(list(group))

        return dict(grouped)


# https://docs.djangoproject.com/en/dev/topics/db/managers/#from-queryset
# This Manager (or a subclass) is required on a  DataspacedModel subclass.
# This is enforced in the check() method of the model.
# To inherit from the DataspacedManager and DataspacedQuerySet methods, use:
# `DataspacedManager.from_queryset(DejacodeUserQuerySet)`
# To only get the DataspacedQuerySet methods:
# `models.Manager.from_queryset(DataspacedQuerySet)`
class DataspacedManager(models.Manager.from_queryset(DataspacedQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related("dataspace")


def is_secured(manager):
    """Return True if the `is_secured` attribute is set to True."""
    if not issubclass(manager.__class__, models.Manager):
        raise AssertionError
    return getattr(manager, "is_secured", False)


def get_unsecured_manager(model_class):
    """
    Return the `unsecured_objects` manager if the default one `is_secured'.
    WARNING: This is only to be used in places where a User context is not available for
    the secured manager, like management commands.
    """
    manager = model_class._default_manager
    if is_secured(manager):
        manager = model_class.unsecured_objects
    return manager


def secure_queryset_relational_fields(queryset, user):
    """
    Apply manager security scoping to each secured foreign key fields.

    For example, the `workflow.Request.product_context` FK is related to the `Product` model
    which has a secured manager.
    The `queryset` will be restricted to the `user` object permissions.
    """
    opts = queryset.model._meta
    foreign_keys = [
        field
        for field in opts.get_fields(include_parents=True, include_hidden=False)
        if field.many_to_one
    ]

    for fk_field in foreign_keys:
        if isinstance(fk_field, GenericForeignKey):
            continue  # Those require to be handheld separately

        related_manager = fk_field.related_model._default_manager
        if is_secured(related_manager):
            queryset = queryset.filter(
                models.Q(**{fk_field.name + "__in": related_manager.get_queryset(user)})
                | models.Q(**{fk_field.name + "__isnull": True})
            )

    if user:
        return queryset.scope(user.dataspace)
    return queryset


class ProductSecuredQuerySet(DataspacedQuerySet):
    def product_secured(self, user=None, perms="view_product"):
        """Filter based on the Product object permission."""
        if not user:
            return self.none()

        Product = apps.get_model("product_portfolio", "Product")
        product_qs = Product.objects.get_queryset(user, perms)
        return self.filter(product__in=product_qs)

    def product(self, product):
        """Filter based on the provided ``product`` object."""
        return self.filter(product=product)


class DataspacedModel(models.Model):
    """Abstract base model for all models that are keyed by Dataspace."""

    dataspace = models.ForeignKey(
        to="dje.Dataspace",
        on_delete=models.PROTECT,
        editable=False,
        help_text=DATASPACE_FIELD_HELP_TEXT,
    )

    # This field does not have unique=True because subclasses of
    # ``DataspacedModel`` should declare a unique_together meta option
    # for ``dataspace`` and ``uuid``.  Objects that inherit from
    # ``DataspacedModel`` and that are copied between dataspaces will
    # have the same uuid.  This means that an object's universally unique
    # identifier (uuid) may *not* be universally unique to a database row.
    uuid = models.UUIDField(
        _("UUID"),
        default=uuid.uuid4,
        editable=False,
    )

    # From: https://docs.djangoproject.com/en/dev/topics/db/managers/
    # "Managers from abstract base classes are always inherited by the child
    # class, [...]. Abstract base classes are designed to capture information
    # and behavior that is common to their child classes. Defining common
    # managers is an appropriate part of this common information."
    # As a result, all DataspacedModel models will inherit from the
    # appropriate DataspacedManager by default.
    # When the `objects` attribute is overridden in the child class, we enforce
    # that the Manager class defined is a child of the DataspacedManager
    # using the Django "System check framework".
    objects = DataspacedManager()

    def get_dataspace(self):
        return self.dataspace

    get_dataspace.short_description = _("Dataspace")
    get_dataspace.admin_order_field = "dataspace"

    class Meta:
        abstract = True

    def natural_key(self):
        return self.dataspace.name, self.uuid

    @classmethod
    def check(cls, **kwargs):
        """
        Enforce the usage of DataspacedManager (or child class) as the
        default Manager using the Django "System check framework".
        Note that Manager generated from a subclass of DataspacedQuerySet are valid:
            Manager(models.Manager.from_queryset(DataspacedQuerySet))
        """
        errors = super().check(**kwargs)
        enforced_manager = DataspacedManager
        enforced_queryset = DataspacedQuerySet

        has_valid_manager = any(
            [
                isinstance(cls._default_manager, enforced_manager),
                issubclass(cls._default_manager._queryset_class, enforced_queryset),
            ]
        )

        if not has_valid_manager:
            manager_name = enforced_manager.__name__
            errors.append(
                checks.Error(
                    f"Manager is not a subclass of {manager_name}",
                    hint=f"Set the proper {manager_name} Manager",
                    obj=cls,
                )
            )

        if cls._meta.managed and not cls._meta.unique_together:
            errors.append(
                checks.Error(
                    "`unique_together` must be defined on DataspacedModel.",
                    hint="Add a value for unique_together on this model Meta class.",
                    obj=cls,
                )
            )

        return errors

    def save(self, *args, **kwargs):
        """Enforces related object to share the same Dataspace as self."""
        # A `copy` argument is provided when calling save() from the copy.
        # It needs to be poped before calling the super().save()
        kwargs.pop("copy", None)

        # For these model classes, related objects can still be saved even if
        # they have a dataspace which is not the current one.
        allowed_models = [Dataspace, get_user_model(), ContentType]

        for field in self.local_foreign_fields:
            if field.related_model not in allowed_models:
                attr_value = getattr(self, field.name)
                if attr_value and attr_value.dataspace != self.dataspace:
                    raise ValueError(
                        f'The Dataspace of the related object: "{attr_value}" '
                        f'is not "{self.dataspace}"'
                    )

        self.clean_extra_spaces_in_identifier_fields()
        super().save(*args, **kwargs)

    @classmethod
    def model_fields(cls):
        """Return the list of fields name available on this model."""
        return [field.name for field in cls._meta.get_fields()]

    @classmethod
    def create_from_data(cls, user, data, validate=False):
        """
        Create and Return an instance of this `cls` using the provided `data`.
        The instance is created in the provided `user` Dataspace.

        If `validate` is enabled, the data with be validated using the `full_clean`
        method before attempting the `save`. This has the benefit of catching
        data issues and returning those as `ValidationError` instead of `DatabaseError`
        at save time, that will have an impact in the database transaction management.
        """
        model_fields = cls.model_fields()
        cleaned_data = {
            field_name: value
            for field_name, value in data.items()
            if field_name in model_fields and value not in EMPTY_VALUES
        }

        if isinstance(user, DejacodeUser):
            initial_values = {
                "dataspace": user.dataspace,
                "created_by": user,
            }
        # Support for providing a Dataspace directly in place of a User
        elif isinstance(user, Dataspace):
            initial_values = {
                "dataspace": user,
            }

        instance = cls(
            **initial_values,
            **cleaned_data,
        )

        if validate:
            instance.full_clean()
        instance.save()

        return instance

    def update_from_data(self, user, data, override=False, override_unknown=False):
        """
        Update this object instance with the provided `data`.
        The `save()` method is called only if at least one field was modified.

        The user is optional, providing None, as some context of automatic update are
        not associated to a specific user.
        We do not want to promote this as the default behavior thus we keep the user
        a required parameter.

        By default, only empty values will be set on the instance, protecting the
        existing values.
        When `override` is True, all the values from the `data` dict will be set on the
        instance, erasing any existing values.
        When `override_unknown` is True, field value currently set as "unknown" will be
        replace by the value from the `data` dict.
        """
        model_fields = self.model_fields()
        updated_fields = []

        for field_name, value in data.items():
            skip_reasons = [
                value in EMPTY_VALUES,
                field_name not in model_fields,
                field_name in PURL_FIELDS,
            ]
            if any(skip_reasons):
                continue

            current_value = getattr(self, field_name, None)
            update_conditions = [
                not current_value,
                current_value != value and override,
                current_value == "unknown" and override_unknown,
            ]
            if any(update_conditions):
                setattr(self, field_name, value)
                updated_fields.append(field_name)

        if updated_fields:
            if user:
                self.last_modified_by = user
                self.save(update_fields=[*updated_fields, "last_modified_by"])
            else:
                self.save(update_fields=updated_fields)

        return updated_fields

    def update(self, **kwargs):
        """
        Update this instance with the provided ``kwargs`` values.
        The full ``save()`` process will be triggered, including signals, and the
        ``update_fields`` is automatically set.
        """
        for field_name, value in kwargs.items():
            setattr(self, field_name, value)

        self.save(update_fields=list(kwargs.keys()))

    def as_json(self):
        try:
            serialized_data = serialize(
                "json",
                [self],
                use_natural_foreign_keys=True,
                use_natural_primary_keys=True,
            )
        except (SerializationError, ValueError):
            serialized_data = None

        return serialized_data

    def get_verbose_name(self):
        return self._meta.verbose_name

    def get_url(self, name, params):
        opts = self._meta
        viewname = f"{opts.app_label}:{opts.model_name}_{name}"
        return reverse(viewname, args=params)

    def get_admin_url(self):
        opts = self._meta
        viewname = f"admin:{opts.app_label}_{opts.model_name}_change"
        try:
            url = reverse(viewname, args=[self.pk])
        except NoReverseMatch:
            return
        return url

    def get_change_url(self):
        """
        Return the admin URL by default.
        Override this method if the object has a custom change view.
        """
        return self.get_admin_url()

    def get_admin_action_url(self, name):
        opts = self._meta
        try:
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_{name}")
        except NoReverseMatch:
            return
        return f"{url}?ids={self.pk}"

    def get_copy_url(self):
        return self.get_admin_action_url("copy")

    def get_api_copy_to_my_dataspace_url(self):
        model_name = self._meta.model_name
        return reverse(f"api_v2:{model_name}-copy-to-my-dataspace", args=[self.uuid])

    def get_compare_url(self):
        return self.get_admin_action_url("compare")

    def get_html_link(self, href, **attrs):
        """
        Return a HTML link using the given href and __str__ of the object
        as value.

        Anything given as kwargs will be added as attributes on the anchor.
        instance.get_html_link('a_href', target='_blank', title='Title')

        A dict can be also be given like this:
        attributes = **{'target': '_blank', 'title': 'Title'}

        A special 'field_name' attribute can be used to replace the __str__ value
        by the given model field value of the instance.
        """
        value = attrs.pop("value", None)
        if not value:
            field_name = attrs.pop("field_name", None)
            value = getattr(self, field_name) if field_name else self

        final_attrs = {"href": smart_urlquote(href)}
        if attrs is not None:
            final_attrs.update(attrs)

        return format_html("<a{}>{}</a>", flatatt(final_attrs), value)

    def get_admin_link(self, **attrs):
        """Return a HTML link using the get_admin_url() as href."""
        admin_url = self.get_admin_url()
        if admin_url:
            return self.get_html_link(self.get_admin_url(), **attrs)

    def get_absolute_link(self, **attrs):
        """Return a HTML link using the get_absolute_url() as href."""
        if hasattr(self, "get_absolute_url"):
            return self.get_html_link(self.get_absolute_url(), **attrs)

    @property
    def urn_link(self):
        """Require the `urn` property to be implemented on the Model."""
        urn = getattr(self, "urn", None)
        if urn:
            return format_html('<a href="{}">{}</a>', reverse("urn_resolve", args=[urn]), urn)

    def _get_local_foreign_fields(self):
        """
        Return a list of ForeignKey type fields of the model.
        GenericForeignKey are not included, filtered out with field.concrete
        """
        return [field for field in self._meta.get_fields() if field.many_to_one and field.concrete]

    local_foreign_fields = property(_get_local_foreign_fields)

    @classmethod
    def get_identifier_fields(cls, *args, **kwargs):
        """
        Return a list of the fields, based on the Meta unique_together, to be
        used to match a unique instance within a Dataspace.
        """
        unique_fields = cls._meta.unique_together

        # Using only the first part of the declared unicity
        if type(unique_fields[0]) is tuple:
            unique_fields = unique_fields[0]

        return [str(field_name) for field_name in unique_fields if field_name != "dataspace"]

    def get_exclude_candidates_fields(self):
        """
        Return the fields supported by the copy exclude feature.
        This exclude all the fields like the dataspace, id, uuid and
        field that do not accept a NULL value.
        """
        from dje.copier import ALWAYS_EXCLUDE

        fields = []
        for field in self._meta.fields:
            skip_conditions = [
                field.related_model is Dataspace,
                isinstance(field, models.AutoField),
                isinstance(field, models.UUIDField),
                not field.null and not field.blank and not field.has_default(),
                field.name in ALWAYS_EXCLUDE,
            ]

            if not any(skip_conditions):
                fields.append(field)

        return fields

    @classmethod
    def get_exclude_choices(cls):
        return sorted(
            (
                (field.name, capfirst(field.verbose_name))
                for field in cls().get_exclude_candidates_fields()
            ),
            key=operator.itemgetter(1),  # Sorts the choices by their verbose_name
        )

    def unique_filters_for(self, target):
        """
        Return a dictionary of filters based on unicity constraints.
        (i.e. the Model Meta "unique_together" of the object.)

        The filters are used to "match" an existing entry in the
        "target" Dataspace.

        The result of the match is used to know if it's a copy or update case.
        Only the first field (or set of fields) declared in the unique_together
        is used as a unique_filters.

        This function is used during the Object "copy" and "update" to another
        Dataspace.
        """
        unique_filters = {}

        for field_name in self.get_identifier_fields():
            field_instance = getattr(self, field_name)

            if isinstance(field_instance, DataspacedModel):
                # In this case, the current field_instance is a FK to another
                # DataspacedModel instance.
                # Trying to match the object in "target"...
                manager = field_instance.__class__.objects
                # ...with the UUID first
                result = manager.filter(uuid=self.uuid, dataspace=target)
                # ... with current unique_filters_for method if nothing matched
                if not result:
                    filters = field_instance.unique_filters_for(target)
                    result = manager.filter(**filters)

                if result:
                    unique_filters.update({field_name: result[0]})
                else:
                    unique_filters.update({field_name: None})
            else:
                unique_filters.update({field_name: field_instance})

        unique_filters.update({"dataspace": target})
        return unique_filters

    @staticmethod
    def get_extra_relational_fields():
        """
        Return a list of related_name as declared on the "Many" part of the
        relation.
        Hook to explicitly declare the relational fields,
        like OneToMany and GenericForeignKey pointing to this Model.
        This is one by the object_copy feature.
        Default: '<fk_model_name>_set'
        """
        return []

    def clean(self, from_api=False):
        if self.id:  # Addition only
            return

        self.validate_case_insensitive_unique_on()
        self.validate_against_reference_data(from_api)

    def validate_case_insensitive_unique_on(self):
        """
        Validate uniqueness via case-insensitive match, using the field
        set on this Model `case_insensitive_unique_on` property.
        The validation is only applied on Addition.
        """
        errors = {}

        for field_name in getattr(self, "case_insensitive_unique_on", []):
            value = getattr(self, field_name, None)
            if not value:
                return

            msg = (
                'The application object that you are creating already exists as "{}". '
                "Note that a different case in the object name is not sufficient to "
                "make it unique."
            )

            qs = (
                self.__class__._default_manager.scope(self.dataspace)
                .filter(**{f"{field_name}__iexact": value})
                .exclude(**{f"{field_name}__exact": value})
            )

            if qs.exists():
                error = msg.format(getattr(qs.first(), field_name))
                errors.setdefault(field_name, []).append(error)

        if errors:
            raise ValidationError(errors)

    def validate_against_reference_data(self, from_api=False):
        """
        Validate values set on a non-reference dataspace instance against reference data.

        Inspired by django.db.models.Model._perform_unique_checks()
        """
        LIMITED_TO_MODELS = [
            "Owner",
            "License",
            "LicenseCategory",
            "LicenseProfile",
            "LicenseStatus",
            "LicenseStyle",
            "LicenseTag",
            "Component",
            "ComponentKeyword",
            "ComponentStatus",
            "ComponentType",
            "Package",
        ]

        if self.__class__.__name__ not in LIMITED_TO_MODELS:
            return

        reference_dataspace = Dataspace.objects.get_reference()
        dataspace = getattr(self, "dataspace", None)
        run_validation = all(
            [
                dataspace,
                reference_dataspace,
                dataspace != reference_dataspace,
            ]
        )
        if not run_validation:
            return

        or_queries = []
        involved_lookup_fields = []
        uniques_lookups = [fields for fields in self._meta.unique_together if "uuid" not in fields]

        for fields in uniques_lookups:
            lookup_kwargs = {}
            for field_name in fields:
                lookup_value = None
                if field_name != "dataspace":
                    lookup_value = getattr(self, field_name, None)
                if lookup_value is None:
                    continue
                lookup_kwargs[str(field_name)] = lookup_value
                involved_lookup_fields.append(field_name)

            if lookup_kwargs:
                or_queries.append(models.Q(**lookup_kwargs))

        if not or_queries:
            return

        qs = self.__class__._default_manager.filter(reduce(operator.or_, or_queries))

        if qs.scope(self.dataspace).exists():
            return  # Skip validation if the object already exists in my own Dataspace

        if qs.scope(reference_dataspace).exists():
            reference_object = qs.first()
            msg = (
                "The application object that you are creating already exists as {} "
                "in the reference dataspace."
            )

            if not from_api:
                copy_link = self.get_html_link(
                    reference_object.get_copy_url(),
                    value=_("Copy to my Dataspace"),
                    target="_blank",
                )
                msg += f" {copy_link}"
                if hasattr(reference_object, "get_absolute_url"):
                    reference_object = reference_object.get_absolute_link(target="_blank")
            else:
                copy_link = reference_object.get_api_copy_to_my_dataspace_url()
                msg += (
                    f" Use the following URL to copy the reference object to your "
                    f"local Dataspace: {copy_link}"
                )

            error = format_html(msg, reference_object)

            if from_api:
                errors = {
                    "error": error,
                    "copy_url": copy_link,
                }
            else:
                errors = {field: error for field in involved_lookup_fields}

            raise ValidationError(errors)

    def clean_extra_spaces_in_identifier_fields(self):
        """Remove extra spaces in identifier fields value."""
        for field_name in self.get_identifier_fields():
            field_instance = self._meta.get_field(field_name)
            if isinstance(field_instance, models.CharField):
                field_value = getattr(self, field_name, "")
                if "  " in field_value:
                    setattr(self, field_name, " ".join(field_value.split()))

    def mark_all_notifications_as_read(self, user):
        unread_notifications_qs = Notification.objects.unread().filter(
            action_object_content_type__model=self._meta.model_name,
            action_object_object_id=self.id,
            recipient=user,
        )
        # Trigger a single UPDATE query on the "unread" Notification.
        # Even if the QS is empty, this is faster than checking is the QS contains
        # entries first.
        unread_notifications_qs.update(unread=False)


class HistoryDateFieldsMixin(models.Model):
    created_date = models.DateTimeField(
        auto_now_add=True,  # Automatically set to now on object creation
        db_index=True,
        help_text=_("The date and time the object was created."),
    )

    last_modified_date = models.DateTimeField(
        auto_now=True,  # Automatically set to now on object save()
        db_index=True,
        help_text=_("The date and time the object was last modified."),
    )

    class Meta:
        abstract = True


class HistoryUserFieldsMixin(models.Model):
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_%(class)ss",
        null=True,
        editable=False,
        serialize=False,
        help_text=_("The application user who created the object."),
    )

    last_modified_by = LastModifiedByField()

    class Meta:
        abstract = True


class HistoryFieldsMixin(HistoryUserFieldsMixin, HistoryDateFieldsMixin):
    """Add the created_date, last_modified_date, created_by, last_modified_by fields."""

    class Meta:
        abstract = True


class ParentChildModelMixin:
    """
    Provide methods for Parent/Child m2m relationship.
    It requires to be associate with a 'through' Model that extends from
    ParentChildRelationshipModel and that declares 2 FKs 'parent' and 'child'
    to this Model.
    One ManyToManyField can be explicitly declared on this Model to enable the
    copy of children only (parent copy is not wanted/supported).

    children = models.ManyToManyField(
        'self', through='ParentChildRelationshipModel', symmetrical=False)
    """

    def get_parents(self):
        """
        Return the direct parents of the self Object as a QuerySet.
        The default ordering is set on the m2m Model.
        """
        parents_ids = self.related_parents.values("parent__id")
        return self.__class__._default_manager.filter(id__in=parents_ids)

    def get_children(self):
        """
        Return the direct children of the self Object as a QuerySet.
        The default ordering is set on the m2m Model.
        """
        children_ids = self.related_children.values("child__id")
        return self.__class__._default_manager.filter(id__in=children_ids)

    def is_parent_of(self, obj):
        """Return True if the self Object is a direct parent of the given one."""
        return self in obj.get_parents()

    def is_child_of(self, obj):
        """Return True if the self Object is a direct child of the given one."""
        return self in obj.get_children()

    def get_ancestors(self):
        """Return a set of all the ancestors of the self object."""
        ancestors = set()
        for parent in self.get_parents():
            ancestors.add(parent)
            ancestors.update(parent.get_ancestors())
        return ancestors

    def get_descendants(self, set_direct_parent=False):
        """Return a set of all the descendants of the self object."""
        descendants = set()
        for child in self.get_children():
            if set_direct_parent:
                child.direct_parent = self
            descendants.add(child)
            descendants.update(child.get_descendants())
        return descendants

    def get_ancestor_ids(self):
        """Return a list of ids of all the ancestors of the self object."""
        return [instance.id for instance in self.get_ancestors()]

    def get_descendant_ids(self):
        """Return a list of ids of all the descendants of the self object."""
        return [instance.id for instance in self.get_descendants()]

    def get_related_ancestors(self):
        """
        Return a set of all the *related* ancestors of the self object.
        Where get_ancestors() Return the objects at the end of the relation,
        this return the intermediary 'through' objects.
        """
        ancestors = set()
        for related_parent in self.related_parents.all():
            ancestors.add(related_parent)
            ancestors.update(related_parent.parent.get_related_ancestors())
        return ancestors

    def get_related_descendants(self):
        """
        Return a set of all the *related* descendants of the self object.
        Where get_descendants() Return the objects at the end of the relation,
        this return the intermediary 'through' objects.
        """
        descendants = set()
        for related_child in self.related_children.all():
            descendants.add(related_child)
            descendants.update(related_child.child.get_related_descendants())
        return descendants

    def is_ancestor_of(self, obj):
        """Return True if the current self Object is an ancestor of the given one."""
        return self in obj.get_ancestors()

    def is_descendant_of(self, obj):
        """Return True if the self Object is a descendant of the given one."""
        return self in obj.get_descendants()

    def has_parent_or_child(self):
        """
        Return True if the self Object is part of at least 1 m2m relation,
        either as a child or as a parent.
        """
        return self.related_parents.exists() or self.related_children.exists()


class ParentChildRelationshipModel(DataspacedModel):
    """
    Define a parent/child relation.

    This Model needs to be used with the ParentChildModel.
    The 2 following fields are required to be declared this way:

    parent = models.ForeignKey(ParentChildModel, related_name='related_children')
    child = models.ForeignKey(ParentChildModel,  related_name='related_parents')

    Extra fields are possible.
    """

    class Meta:
        abstract = True
        unique_together = (("parent", "child"), ("dataspace", "uuid"))
        ordering = ["parent", "child"]

    def __str__(self):
        return f"Parent: {self.parent} ; Child: {self.child}"

    def clean(self, from_api=False):
        # If one of the main Object (child or parent) is not saved in the DB
        # yet then no further validation possible.
        if not self.child_id or not self.parent_id:
            return

        if self.parent == self.child:
            raise ValidationError("This Object cannot be his own child or parent.")

        if self.parent.is_descendant_of(self.child):
            raise ValidationError(
                "The current Object is a descendant of the selected child, "
                "it cannot also be a parent for it."
            )

        super().clean(from_api)


def colored_icon_mixin_factory(verbose_name, icon_blank):
    class ColoredIconMixin(models.Model):
        icon = models.CharField(
            blank=icon_blank,
            max_length=50,
            help_text=format_lazy(
                "You can choose an icon to associate with the {verbose_name} "
                "from the available icons at "
                "https://fontawesome.com/icons?d=gallery&m=free",
                verbose_name=_(verbose_name),
            ),
        )

        color_code = models.CharField(
            blank=True,
            max_length=7,
            help_text=_(
                "You can specify a valid HTML color code (e.g. #FFFFFF) to apply " "to your icon."
            ),
        )

        class Meta:
            abstract = True

        def get_color_code(self):
            if self.color_code:
                return f"#{self.color_code.lstrip('#')}"
            return "#000000"

        def get_icon_as_html(self):
            if self.icon:
                return format_html(
                    '<i class="{}" style="color: {};"></i>',
                    self.icon,
                    self.get_color_code(),
                )

    return ColoredIconMixin


class DejacodeUserQuerySet(DataspacedQuerySet):
    def actives(self):
        return self.filter(is_active=True)

    def standards(self):
        return self.filter(is_staff=False)

    def admins(self):
        return self.filter(is_staff=True)


class DejacodeUserManager(BaseUserManager, DataspacedManager.from_queryset(DejacodeUserQuerySet)):
    def create_user(self, username, email, password, dataspace, **extra_fields):
        """
        Create and saves a User with the given username, email, password and
        dataspace.
        """
        if not username:
            raise ValueError("The given username must be set")

        if not email:
            raise ValueError("Users must have an email address")

        if not dataspace:
            raise ValueError("Users must have a Dataspace")

        defaults = {
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
        }

        groups = extra_fields.pop("groups", [])
        defaults.update(extra_fields)
        email = DejacodeUserManager.normalize_email(email)
        now = timezone.now()

        user = self.model(
            username=username,
            email=email,
            dataspace=dataspace,
            last_login=now,
            date_joined=now,
            **defaults,
        )
        user.set_password(password)
        user.save(using=self._db)

        for group_name in groups:
            with suppress(Group.DoesNotExist):
                user.groups.add(Group.objects.get(name=group_name))

        return user

    def create_superuser(self, username, email, password, dataspace=None, **extra_fields):
        """
        Create and saves a superuser with the given username, email, password
        and dataspace.
        In case no dataspace instance is given, we're using the 'nexB' one.
        """
        if not dataspace:
            dataspace = Dataspace.objects.get(name="nexB")

        extra_fields.update(
            {
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            }
        )

        return self.create_user(username, email, password, dataspace, **extra_fields)

    def create_inactive_user(self, username, email, password, dataspace, **extra_fields):
        """
        Create and saves a user with the given username, email, password
        and dataspace. Force the is_active to False.
        """
        user = self.create_user(username, email, password, dataspace, **extra_fields)
        user.is_active = False
        user.save(using=self._db)
        return user

    def get_data_update_recipients(self, dataspace):
        """
        Return the Users with `data_email_notification` enabled for a given dataspace
        as a flat list of email addresses.
        """
        qs = self.get_queryset().filter(data_email_notification=True, dataspace=dataspace)
        # Need to be converted as a list to be serializable
        return list(qs.distinct().values_list("email", flat=True))


class DejacodeUser(AbstractUser):
    uuid = models.UUIDField(
        _("UUID"),
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )

    dataspace = models.ForeignKey(
        to="dje.Dataspace",
        on_delete=models.PROTECT,
        help_text=DATASPACE_FIELD_HELP_TEXT,
    )

    data_email_notification = models.BooleanField(
        default=False,
        help_text=_(
            "Check this to send email notifications to the user regarding DejaCode data updates; "
            "note that the volume could be very large, so this option is normally enabled only "
            "during system setup and rollout to monitor application activity."
        ),
    )

    workflow_email_notification = models.BooleanField(
        default=False,
        help_text=_(
            "Check this to send email notifications to the user for associated workflow requests; "
            "otherwise, request notifications alerts will appear in the DejaCode notifications "
            "form."
        ),
    )

    updates_email_notification = models.BooleanField(
        default=False,
        help_text=_(
            "Check this to receive email notifications with updates on DejaCode "
            "features and news."
        ),
    )

    company = models.CharField(
        max_length=30,
        blank=True,
        help_text=_(
            "The company the user is associated with. "
            "This can be submitted during the signup process."
        ),
    )

    last_api_access = models.DateTimeField(
        verbose_name=_("last API access"),
        blank=True,
        null=True,
    )

    homepage_layout = models.ForeignKey(
        to="reporting.CardLayout",
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
        serialize=False,
        help_text=_(
            "Select a Card layout that provides the query results on the "
            "DejaCode homepage that are useful and interesting to you."
        ),
    )

    objects = DejacodeUserManager()

    class Meta:
        ordering = ["username"]

    def save(self, *args, **kwargs):
        """
        Send an email to the user when his password has been changed.

        The password can be changed from those locations:
         - Change password user view : /account/password_change/
         - Password reset user view: /account/password_reset/
         - Management command: ./manage.py changepassword
         - Model instance: set_password() + save()
        """
        from dje.notification import send_password_changed_email

        # self._password will be set to None during a hasher upgrade as we do not
        # want to notify in that case, as it's not considered a password changes.
        # See AbstractBaseUser.check_password.setter
        password_changed = self._password is not None
        user_exists = bool(self.pk)

        super().save(*args, **kwargs)

        # Do not notify users that are setting their initial password during registration
        if password_changed and user_exists and self.last_login:
            send_password_changed_email(self)

    @property
    def last_active(self):
        activity_date_fields = [
            self.date_joined,
            self.last_login,
            self.last_api_access,
        ]
        return max([field for field in activity_date_fields if field])

    def get_group_names(self):
        """
        Return the group names assigned to the User through the DB and LDAP
        authentication (when enabled).
        """
        group_names_from_db = list(self.groups.values_list("name", flat=True))

        ldap_user = getattr(self, "ldap_user", None)
        if ldap_user:
            return list(set(group_names_from_db).union(ldap_user.group_names))

        return group_names_from_db

    def get_homepage_layout(self):
        """
        Return the User `homepage_layout`, from the this instance first,
        or fallback on the Dataspace layout, if set.
        """
        return self.homepage_layout or self.dataspace.get_configuration("homepage_layout")

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Wrap the method in a task."""
        send_mail_task.delay(subject, message, from_email, [self.email], **kwargs)

    def regenerate_api_key(self):
        """
        Regenerate the user API key.
        Since the `key` value is the primary key on the Token `model`,
        the old key needs to be deleted first, a new one is then created.
        """
        self.auth_token.delete()
        Token.objects.create(user=self)

    def serialize_user_data(self):
        fields = [
            "email",
            "first_name",
            "last_name",
            "username",
            "company",
            "last_login",
            "date_joined",
            "last_api_access",
            "last_active",
            "is_superuser",
            "is_staff",
            "is_active",
            "updates_email_notification",
            "dataspace",
        ]

        return {
            field: str(value) for field in fields if (value := getattr(self, field)) is not None
        }

    def serialize_hook(self, hook):
        return {
            "hook": hook.dict(),
            **self.serialize_user_data(),
        }


@receiver(models.signals.post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)


class HistoryManager(DataspacedManager):
    def get_queryset(self):
        return super().get_queryset().select_related(None)

    def get_for_object(self, obj, **kwargs):
        if hasattr(obj, "dataspace_id"):
            kwargs["object_dataspace__id"] = obj.dataspace_id

        return self.filter(
            object_id=obj.pk,
            content_type=ContentType.objects.get_for_model(obj).pk,
            **kwargs,
        )

    def log_action(self, user, obj, action_flag, message="", serialized_data=None):
        """
        Create a History entry for a given `obj` on Addition, Change, and Deletion.
        We do not log addition for object that inherit the HistoryFieldsMixin since
        the `created_by` and `created_date` are already set on its model.
        """
        is_addition = action_flag == History.ADDITION
        obj_has_history_fields = isinstance(obj, HistoryFieldsMixin)
        has_generic_message = message == [{"added": {}}]

        if is_addition and obj_has_history_fields and has_generic_message:
            return

        if isinstance(message, list):
            message = json.dumps(message)

        return self.model.objects.create(
            user_id=user.pk,
            content_type_id=ContentType.objects.get_for_model(obj).pk,
            object_id=obj.pk,
            object_repr=str(obj)[:200],
            action_flag=action_flag,
            change_message=message,
            object_dataspace=getattr(obj, "dataspace", None),
            serialized_data=serialized_data,
        )


class History(models.Model):
    ADDITION = ADDITION
    CHANGE = CHANGE
    DELETION = DELETION

    ACTION_FLAG_CHOICES = (
        (ADDITION, _("Addition")),
        (CHANGE, _("Change")),
        (DELETION, _("Deletion")),
    )

    object_dataspace = models.ForeignKey(
        to="dje.Dataspace",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        editable=False,
    )

    serialized_data = models.TextField(
        null=True,
        blank=True,
        editable=False,
        help_text=_("Serialized data of the instance just before this change."),
    )

    # The following fields are directly taken from django.contrib.admin.models.LogEntry
    # Since the LogEntry is not abstract we cannot properly inherit from it.

    action_time = models.DateTimeField(
        _("action time"),
        default=timezone.now,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.CASCADE,
        verbose_name=_("user"),
    )

    content_type = models.ForeignKey(
        ContentType,
        models.SET_NULL,
        verbose_name=_("content type"),
        blank=True,
        null=True,
    )

    object_id = models.TextField(
        _("object id"),
        blank=True,
        null=True,
    )

    object_repr = models.CharField(
        _("object repr"),
        max_length=200,
    )

    action_flag = models.PositiveSmallIntegerField(
        _("action flag"),
        choices=ACTION_FLAG_CHOICES,
    )

    # change_message is either a string or a JSON structure
    change_message = models.TextField(
        _("change message"),
        blank=True,
    )

    objects = HistoryManager()

    class Meta:
        verbose_name = _("history entry")
        verbose_name_plural = _("history entries")
        ordering = ("-action_time",)

    # Clone the method from Django's LogEntry model.
    __repr__ = LogEntry.__repr__
    __str__ = LogEntry.__str__
    is_addition = LogEntry.is_addition
    is_change = LogEntry.is_change
    is_deletion = LogEntry.is_deletion
    get_change_message = LogEntry.get_change_message
    get_edited_object = LogEntry.get_edited_object
    get_admin_url = LogEntry.get_edited_object

    @classmethod
    def log_addition(cls, user, obj, message=None):
        """Create History entry on Addition with the proper `change_message`."""
        if not message:
            message = [{"added": {}}]

        return cls.objects.log_action(user, obj, cls.ADDITION, message)

    @classmethod
    def log_change(cls, user, obj, message, serialized_data=None):
        """Create History entry on Change."""
        return cls.objects.log_action(user, obj, cls.CHANGE, message, serialized_data)

    @classmethod
    def log_deletion(cls, user, obj):
        """
        Create History entry on Deletion.
        Include the serialized_data if `as_json()` is available on the model class.
        """
        serialized_data = None
        with suppress(AttributeError):
            serialized_data = obj.as_json()

        return cls.objects.log_action(user, obj, cls.DELETION, serialized_data=serialized_data)


class ExternalSource(DataspacedModel):
    label = models.CharField(
        max_length=50,
        help_text=_("A Label is a concise name of the external source as it " "is commonly known."),
    )

    notes = models.TextField(
        blank=True,
        help_text=_(
            "Notes describe the purpose and special characteristics " "of the external source."
        ),
    )

    homepage_url = models.URLField(
        max_length=1024,
        blank=True,
        help_text=_("Main homepage URL of the external source."),
    )

    class Meta:
        ordering = ["label"]
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))

    def __str__(self):
        return self.label


class ExternalReferenceManager(DataspacedManager):
    def get_queryset(self):
        """
        Force the 'external_source' to be select_related since we always need
        the source data along the reference.
        Only 'external_references' is required on the parent QuerySet prefetch_related()
        instead of 'external_references__external_source'.

        This is equivalent to:
        Prefetch('external_references',
                 queryset=ExternalReference.objects.select_related('external_source'))
        """
        return super().get_queryset().select_related("external_source")

    def get_content_object(self, external_source, external_id):
        """Return the instance attached to a given external reference."""
        return self.get(external_source=external_source, external_id=external_id).content_object

    def get_for_content_object(self, content_object):
        """Return all the instances of ExternalReference for a given DJE object."""
        return self.filter(
            content_type=ContentType.objects.get_for_model(content_object),
            object_id=content_object.pk,
        )

    def create_for_content_object(self, content_object, external_source, external_id):
        """
        Create and Return an ExternalReference for a given DJE object.

        ExternalReference.objects.create_for_content_object(
            content_object=component_instance,
            external_source=ExternalSource.object.get(),
            external_id='4309')
        """
        return self.create(
            content_type=ContentType.objects.get_for_model(content_object),
            object_id=content_object.pk,
            external_source=external_source,
            external_id=external_id,
        )


class ExternalReference(HistoryFieldsMixin, DataspacedModel):
    """
    Maps DJE objects to external resources.
    One DJE object may have several ExternalReference when it's referenced on
    multiple sources.
    Also, there is no unicity collision possible as we use the object_id.

    The copy for GenericForeignKey field is not supported yet.
    """

    # The following models should always inherit from ExternalReferenceMixin
    # for the proper deletion in CASCADE behavior.
    CT_LIMIT = (
        models.Q(app_label="organization", model="owner")
        | models.Q(app_label="license_library", model="license")
        | models.Q(app_label="component_catalog", model="component")
        | models.Q(app_label="component_catalog", model="package")
    )

    content_type = models.ForeignKey(
        to=ContentType,
        limit_choices_to=CT_LIMIT,
        on_delete=models.PROTECT,
    )

    object_id = models.PositiveIntegerField()

    content_object = GenericForeignKey("content_type", "object_id")

    external_source = models.ForeignKey(
        to="dje.ExternalSource",
        on_delete=models.PROTECT,
    )

    external_id = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Value of the identifier used on the source to reference the object."),
    )

    external_url = models.URLField(
        max_length=1024,
        blank=True,
        help_text=_("A URL to the component, or component metadata, in the external source."),
    )

    objects = ExternalReferenceManager()

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ["external_source", "external_id"]

    def __str__(self):
        return f"{self.external_source}: {self.external_id}"

    def save(self, *args, **kwargs):
        self.dataspace = self.content_object.dataspace
        super().save(*args, **kwargs)


external_references_prefetch = models.Prefetch(
    "external_references",
    queryset=(
        ExternalReference.objects.select_related("content_type").prefetch_related("content_object")
    ),
)


class ExternalReferenceMixin(models.Model):
    """
    Abstract Model Mixin to add proper ExternalReference deletion behavior.

    From the documentation: if you delete an object that has a GenericRelation,
    any objects which have a GenericForeignKey pointing at it will be deleted as
    well.
    """

    external_references = GenericRelation(ExternalReference)

    class Meta:
        abstract = True


class ReferenceNotesMixin(models.Model):
    """Add the reference_notes field."""

    reference_notes = models.TextField(
        blank=True,
        help_text=_(
            "Reference Notes provide background details about the sofware and "
            "licenses in DejaCode, alerting you to pertinent ownership history "
            "or licensing complexities"
        ),
    )

    class Meta:
        abstract = True
