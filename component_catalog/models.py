#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging
import re
from contextlib import suppress
from urllib.parse import quote_plus

from django.contrib.postgres.fields import ArrayField
from django.core import validators
from django.core.exceptions import MultipleObjectsReturned
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.core.validators import EMPTY_VALUES
from django.db import models
from django.db.models import CharField
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models.functions import Concat
from django.dispatch import receiver
from django.template.defaultfilters import filesizeformat
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.text import format_lazy
from django.utils.text import get_valid_filename
from django.utils.text import normalize_newlines
from django.utils.translation import gettext_lazy as _

from attributecode.model import About
from cyclonedx import model as cyclonedx_model
from cyclonedx.model import component as cyclonedx_component
from cyclonedx.model import contact as cyclonedx_contact
from cyclonedx.model import license as cyclonedx_license
from license_expression import ExpressionError
from packageurl import PackageURL
from packageurl.contrib import purl2url
from packageurl.contrib import url2purl
from packageurl.contrib.django.models import PackageURLMixin
from packageurl.contrib.django.models import PackageURLQuerySetMixin
from packageurl.contrib.django.utils import without_empty_values

from component_catalog.license_expression_dje import build_licensing
from component_catalog.license_expression_dje import get_expression_as_spdx
from component_catalog.license_expression_dje import get_license_objects
from component_catalog.license_expression_dje import parse_expression
from component_catalog.license_expression_dje import render_expression_as_html
from dejacode_toolkit import spdx
from dejacode_toolkit.download import DataCollectionException
from dejacode_toolkit.download import collect_package_data
from dejacode_toolkit.purldb import PurlDB
from dejacode_toolkit.purldb import pick_purldb_entry
from dje import urn
from dje.copier import post_copy
from dje.copier import post_update
from dje.fields import JSONListField
from dje.fields import NoStripTextField
from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import ExternalReferenceMixin
from dje.models import History
from dje.models import HistoryFieldsMixin
from dje.models import ParentChildModelMixin
from dje.models import ParentChildRelationshipModel
from dje.models import ReferenceNotesMixin
from dje.tasks import logger as tasks_logger
from dje.utils import is_purl_str
from dje.utils import set_fields_from_object
from dje.validators import generic_uri_validator
from dje.validators import validate_url_segment
from dje.validators import validate_version
from license_library.models import License
from license_library.models import LicenseChoice
from policy.models import SetPolicyFromLicenseMixin
from policy.models import UsagePolicyMixin
from workflow.models import RequestMixin

logger = logging.getLogger("dje")


COMPONENT_PACKAGE_COMMON_FIELDS = [
    "copyright",
    "dependencies",
    "description",
    "holder",
    "homepage_url",
    "license_expression",
    "name",
    "notice_text",
    "primary_language",
    "release_date",
    "version",
]

LICENSE_EXPRESSION_HELP_TEXT = _(
    "The License Expression assigned to a DejaCode Package or Component is an editable "
    'value equivalent to a "concluded license" as determined by a curator who has '
    "performed analysis to clarify or correct the declared license expression, which "
    "may have been assigned automatically (from a scan or an associated package "
    "definition) when the Package or Component was originally created. "
    "A license expression defines the relationship of one or more licenses to a "
    "software object. More than one applicable license can be expressed as "
    '"license-key-a AND license-key-b". A choice of applicable licenses can be '
    'expressed as "license-key-a OR license-key-b", and you can indicate the primary '
    "(preferred) license by placing it first, on the left-hand side of the OR "
    "relationship. The relationship words (OR, AND) can be combined as needed, "
    "and the use of parentheses can be applied to clarify the meaning; "
    'for example "((license-key-a AND license-key-b) OR (license-key-c))". '
    "An exception to a license can be expressed as "
    '"license-key WITH license-exception-key".'
)


class PackageAlreadyExistsWarning(Exception):
    def __init__(self, message):
        self.message = message


def validate_filename(value):
    invalid_chars = ["/", "\\", ":"]
    if any(char in value for char in invalid_chars):
        raise ValidationError(
            _("Enter a valid filename: slash, backslash, or colon are not allowed.")
        )


class LicenseExpressionMixin:
    """Model mixin for models that store license expressions."""

    def _get_licensing(self):
        """Return a Licensing object built from the assigned licenses."""
        # WARNING: Do not apply select/prefect_related here but on the main QuerySet instead
        # For example: prefetch_related('component_set__licenses__dataspace')
        return build_licensing(self.licenses.all())

    licensing = cached_property(_get_licensing)

    def _get_normalized_expression(self):
        """
        Return this object ``license_expression`` field value as a normalized parsed
        expression object.
        """
        if self.license_expression:
            return parse_expression(
                self.license_expression,
                licenses=self.licensing,
                validate_known=False,
                validate_strict=False,
            )

    normalized_expression = cached_property(_get_normalized_expression)

    def get_license_expression(self, template="{symbol.key}", as_link=False, show_policy=False):
        """
        Validate and Return the license_expression value set on this instance.
        The license expression is NOT validated for known symbols.
        Use the `template` format string to render each license in the expression.
        if `as_link` is True, render the expression as a link.
        """
        if self.license_expression:
            rendered = self.normalized_expression.render_as_readable(
                template,
                as_link=as_link,
                show_policy=show_policy,
            )
            return format_html(rendered)

    def get_license_expression_attribution(self):
        # note: the fields use in the template must be available as attributes or
        # properties on a License.
        template = '<a href="#license_{symbol.key}">{symbol.short_name}</a>'
        return self.get_license_expression(template)

    license_expression_attribution = cached_property(get_license_expression_attribution)

    def get_license_expression_linked(self):
        return self.get_license_expression(as_link=True)

    license_expression_linked = cached_property(get_license_expression_linked)

    def get_license_expression_linked_with_policy(self):
        license_expression = self.get_license_expression(as_link=True, show_policy=True)
        if license_expression:
            return format_html('<span class="license-expression">{}</span>', license_expression)

    def _get_primary_license(self):
        """
        Return the primary license key of this instance or None. The primary license is
        the left most license of the expression. It can be the combination of a
        license WITH an exception and therefore may contain more than one key.

        WARNING: This does not support exception as primary_license.
        """
        if self.license_expression:
            licensing = build_licensing()
            return licensing.primary_license_key(self.license_expression)

    primary_license = cached_property(_get_primary_license)

    def get_expression_as_spdx(self, expression):
        """
        Return the license_expression formatted for SPDX compatibility.

        This includes a workaround for a SPDX spec limitation, where license exceptions
        that do not exist in the SPDX list cannot be provided as "LicenseRef-" in the
        "hasExtractedLicensingInfos".
        The current fix is to use AND rather than WITH for any exception that is a
        "LicenseRef-".

        See discussion at https://github.com/spdx/tools-java/issues/73
        """
        if not expression:
            return

        try:
            expression_as_spdx = get_expression_as_spdx(expression, self.dataspace)
        except ExpressionError as e:
            return str(e)

        if expression_as_spdx:
            return expression_as_spdx.replace("WITH LicenseRef-", "AND LicenseRef-")

    @property
    def concluded_license_expression_spdx(self):
        return self.get_expression_as_spdx(self.license_expression)

    @property
    def license_expression_html(self):
        if self.license_expression:
            return render_expression_as_html(self.license_expression, self.dataspace)

    def save(self, *args, **kwargs):
        """
        Call the handle_assigned_licenses method on save, except during copy.
        During copy, as some Licenses referenced by the license_expression may not exists in the
        target Dataspace yet, the handle_assigned_licenses() would not be able to create the
        proper assignments and the UUID of those assignments would not be shared with
        reference Dataspace.
        Thus, the handle_assigned_licenses() is skipped during the copy process and the
        License assignments are handled by the m2m copy.
        """
        super().save(*args, **kwargs)
        self.handle_assigned_licenses(copy=kwargs.get("copy"))

    def handle_assigned_licenses(self, copy=False):
        """
        Create missing AssignedLicense instances and deletes the ones non-referenced
        in the license_expression.

        In `copy` mode, all the license assignments are deleted to avoid any conflicts
        during the copy/update process where all the assignments are properly created.
        """
        licenses_field = self._meta.get_field("licenses")
        AssignedLicense = licenses_field.remote_field.through

        # Looking for the FK field name, on the AssignedLicense, that points to this Model
        fk_field_name = [
            field
            for field in AssignedLicense._meta.get_fields()
            if field.many_to_one and field.concrete and field.related_model == self.__class__
        ]

        if len(fk_field_name) != 1:
            return
        fk_field_name = fk_field_name[0].name

        assigned_license_qs = AssignedLicense.objects.filter(
            **{"dataspace": self.dataspace, fk_field_name: self}
        )

        if copy:
            # Deletes all existing license assignments to ensure UUID integrity
            # as the licenses will be properly assigned during the copy/update process
            assigned_license_qs.delete()
            return

        # Get the full list of licenses is required here for proper
        # validation. We cannot rely on the assigned licenses since we
        # are modifying those assignments.
        all_licenses = License.objects.scope(self.dataspace).for_expression()
        licenses = get_license_objects(self.license_expression, all_licenses)

        for license_instance in licenses:
            AssignedLicense.objects.get_or_create(
                **{
                    "dataspace": self.dataspace,
                    fk_field_name: self,
                    "license": license_instance,
                }
            )

        assigned_license_qs.exclude(license__in=licenses).delete()

    @cached_property
    def license_choices_expression(self):
        """Return the license choices as an expression."""
        return LicenseChoice.objects.get_choices_expression(self.license_expression, self.dataspace)

    @cached_property
    def has_license_choices(self):
        """Return `True` if applying the LicenseChoice results in a new expression."""
        return self.license_expression != self.license_choices_expression

    @property
    def attribution_required(self):
        return any(license.attribution_required for license in self.licenses.all())

    @property
    def redistribution_required(self):
        return any(license.redistribution_required for license in self.licenses.all())

    @property
    def change_tracking_required(self):
        return any(license.change_tracking_required for license in self.licenses.all())

    @cached_property
    def compliance_alerts(self):
        """
        Return the list of all existing `compliance_alert` through this license
        `usage_policy`.
        """
        return [
            license.usage_policy.compliance_alert
            for license in self.licenses.all()
            if license.usage_policy_id and license.usage_policy.compliance_alert
        ]

    def compliance_table_class(self):
        """Return a CSS class for a table row based on the licenses `compliance_alerts`."""
        if "error" in self.compliance_alerts:
            return "table-danger"
        elif "warning" in self.compliance_alerts:
            return "table-warning"


class LicenseFieldsMixin(models.Model):
    declared_license_expression = models.TextField(
        blank=True,
        help_text=_(
            "A license expression derived from statements in the manifests or key "
            "files of a software project, such as the NOTICE, COPYING, README, and "
            "LICENSE files."
        ),
    )

    other_license_expression = models.TextField(
        blank=True,
        help_text=_(
            "A license expression derived from detected licenses in the non-key files "
            "of a software project, which are often third-party software used by the "
            "project, or test, sample and documentation files."
        ),
    )

    class Meta:
        abstract = True

    @property
    def declared_license_expression_spdx(self):
        return self.get_expression_as_spdx(self.declared_license_expression)

    @property
    def other_license_expression_spdx(self):
        return self.get_expression_as_spdx(self.other_license_expression)


def get_cyclonedx_properties(instance):
    """
    Return fields not supported natively by CycloneDX as properties.
    Those fields are required to load the BOM without major data loss.
    See https://github.com/nexB/aboutcode-cyclonedx-taxonomy
    """
    property_prefix = "aboutcode"
    property_fields = [
        "filename",  # package-only
        "download_url",  # package-only
        "primary_language",
        "homepage_url",
        "notice_text",
    ]
    properties = [
        cyclonedx_model.Property(name=f"{property_prefix}:{field_name}", value=value)
        for field_name in property_fields
        if (value := getattr(instance, field_name, None)) not in EMPTY_VALUES
    ]
    return properties


class HolderMixin(models.Model):
    """Add the `holder` field."""

    holder = models.TextField(
        blank=True,
        help_text=_(
            "The name(s) of the copyright holder(s) of a software package as documented in the "
            "code. This field is intended to record the copyright holder independently of "
            "copyright statement dates and formats, and generally corresponds to the owner of "
            "the associated software project."
        ),
    )

    class Meta:
        abstract = True


class KeywordsMixin(models.Model):
    """Add the `keywords` field."""

    keywords = JSONListField(
        blank=True,
        help_text=_(
            "A keyword is a category or label that helps you to find items "
            "for particular requirements."
        ),
    )

    class Meta:
        abstract = True


class CPEMixin(models.Model):
    """Add the `cpe` field."""

    cpe = models.CharField(
        _("CPE"),
        blank=True,
        max_length=1024,
        help_text=_(
            "Common Platform Enumeration (CPE) is a standardized method of describing and "
            "identifying a computing asset. CPE does not necessarily identify a unique instance "
            "or version of a computing asset. For example, a CPE could identify a component name "
            "with a version range."
        ),
    )

    class Meta:
        abstract = True

    def get_spdx_cpe_external_ref(self):
        if self.cpe:
            return spdx.ExternalRef(
                category="SECURITY",
                type="cpe23Type",
                locator=self.cpe,
            )


class URLFieldsMixin(models.Model):
    homepage_url = models.URLField(
        _("Homepage URL"),
        max_length=1024,
        blank=True,
        help_text=_("Homepage URL."),
    )

    # The URLField validation is too strict to support values like git://
    vcs_url = models.CharField(
        _("VCS URL"),
        max_length=1024,
        validators=[generic_uri_validator],
        blank=True,
        help_text=_("URL to the Version Control System (VCS)."),
    )

    code_view_url = models.URLField(
        _("Code view URL"),
        max_length=1024,
        blank=True,
        help_text=_("A URL that allows you to browse and view the source code online."),
    )

    bug_tracking_url = models.URLField(
        _("Bug tracking URL"),
        max_length=1024,
        blank=True,
        help_text=_("A URL to the bug reporting system."),
    )

    class Meta:
        abstract = True


class HashFieldsMixin(models.Model):
    """
    The hash fields are not indexed by default, use the `indexes` in Meta as needed:

    class Meta:
        indexes = [
            models.Index(fields=['md5']),
            models.Index(fields=['sha1']),
            models.Index(fields=['sha256']),
            models.Index(fields=['sha512']),
        ]
    """

    md5 = models.CharField(
        _("MD5"),
        max_length=32,
        blank=True,
        help_text=_("MD5 checksum hex-encoded, as in md5sum."),
    )
    sha1 = models.CharField(
        _("SHA1"),
        max_length=40,
        blank=True,
        help_text=_("SHA1 checksum hex-encoded, as in sha1sum."),
    )
    sha256 = models.CharField(
        _("SHA256"),
        max_length=64,
        blank=True,
        help_text=_("SHA256 checksum hex-encoded, as in sha256sum."),
    )
    sha512 = models.CharField(
        _("SHA512"),
        max_length=128,
        blank=True,
        help_text=_("SHA512 checksum hex-encoded, as in sha512sum."),
    )

    class Meta:
        abstract = True


class ComponentType(DataspacedModel):
    label = models.CharField(
        max_length=50,
        help_text=_(
            "Label that indicates the scope, function, and complexity of a component. "
            "Every dataspace has its own list of component types. Examples include: "
            "product, package, project, assembly, module, platform, directory, file, snippet."
        ),
    )

    notes = models.TextField(
        blank=True,
        help_text=_("Optional descriptive text."),
    )

    class Meta:
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))
        ordering = ["label"]

    def __str__(self):
        return self.label


CONFIGURATION_STATUS_HELP = _(
    "The configuration status can be used to communicate the current stage of the review process "
    "and whether additional review is required."
)


class DefaultOnAdditionManager(DataspacedManager):
    def get_default_on_addition_qs(self, dataspace):
        """
        Return the QuerySet with default_on_addition=True scoped to the given `dataspace`.
        The QS count should be 0 or 1 max.
        """
        return self.scope(dataspace).filter(default_on_addition=True)


class DefaultOnAdditionFieldMixin(models.Model):
    default_on_addition = models.BooleanField(
        _("Default on addition"),
        default=False,
        help_text=_(
            "Indicates this instance is automatically assigned by the "
            "application to an object when it is initially created."
        ),
    )

    objects = DefaultOnAdditionManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Make sure only one default_on_addition is set to True per Dataspace by forcing False
        for default_on_addition on any other instance.
        Note that this cannot be done in clean() as the dataspace will not have
        been set on the instance yet.
        """
        if self.default_on_addition:
            qs = self.__class__.objects.get_default_on_addition_qs(self.dataspace)
            qs.update(default_on_addition=False)
        super().save(*args, **kwargs)


class BaseStatusMixin(DefaultOnAdditionFieldMixin, models.Model):
    label = models.CharField(
        max_length=50,
        help_text=_("Concise name to identify the status."),
    )

    text = models.TextField(
        help_text=_("Descriptive text to define the status purpose precisely."),
    )

    class Meta:
        abstract = True
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))
        ordering = ["label"]

    def __str__(self):
        return self.label


class DefaultOnAdditionMixin:
    def save(self, *args, **kwargs):
        """
        Set the default Status on ADDITION, if a Status instance was set as default.
        Note that this cannot be done in clean() as the dataspace will not be
        set on the instance yet.
        """
        is_addition = not self.pk

        if is_addition:
            default_on_addition_fields = [
                field
                for field in self._meta.get_fields()
                if field.is_relation
                and issubclass(field.related_model, DefaultOnAdditionFieldMixin)
            ]

            for on_addition_field in default_on_addition_fields:
                if not getattr(self, on_addition_field.name):
                    related_model = on_addition_field.related_model
                    default = related_model.objects.get_default_on_addition_qs(
                        self.dataspace
                    ).first()
                    setattr(self, on_addition_field.name, default)

        super().save(*args, **kwargs)


class ComponentStatus(BaseStatusMixin, DataspacedModel):
    class Meta(BaseStatusMixin.Meta):
        verbose_name_plural = _("component status")


def component_mixin_factory(verbose_name):
    """
    Return a BaseComponentMixin class suitable for Component and Product.
    This factory logic is required to inject a variable verbose name in the help_text.
    """

    class BaseComponentMixin(
        DefaultOnAdditionMixin,
        LicenseExpressionMixin,
        URLFieldsMixin,
        RequestMixin,
        HistoryFieldsMixin,
        models.Model,
    ):
        """Component and Product common Model fields."""

        name = models.CharField(
            db_index=True,
            max_length=100,
            help_text=format_lazy(
                "Name by which the {verbose_name} is commonly referenced.",
                verbose_name=_(verbose_name),
            ),
            validators=[validate_url_segment],
        )

        version = models.CharField(
            db_index=True,
            max_length=100,
            blank=True,
            help_text=format_lazy(
                "Identifies a specific version of a {verbose_name}. The combination of "
                "name + version uniquely identifies a {verbose_name}. If the version is "
                "(nv) or blank, it signifies an unstated/unknown version (or it indicates "
                "that version does not apply to the {verbose_name}), and it does not imply "
                "that the information in this {verbose_name} definition applies to any "
                "or all possible versions of the {verbose_name}.",
                verbose_name=_(verbose_name),
            ),
            validators=[validate_version],
        )

        owner = models.ForeignKey(
            to="organization.Owner",
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            help_text=format_lazy(
                "Owner is an optional field selected by the user to identify the original "
                "creator (copyright holder) of the  {verbose_name}. "
                "If this {verbose_name} is in its original, unmodified state, the {verbose_name}"
                " owner is associated with the original author/publisher. "
                "If this {verbose_name} has been copied and modified, "
                "the {verbose_name}  owner should be the owner that has copied and "
                "modified it.",
                verbose_name=_(verbose_name),
            ),
        )

        release_date = models.DateField(
            null=True,
            blank=True,
            help_text=format_lazy(
                "The date that the {verbose_name} was released by its owner.",
                verbose_name=_(verbose_name),
            ),
        )

        description = models.TextField(
            blank=True,
            help_text=_("Free form description, preferably as provided by the author(s)."),
        )

        copyright = models.TextField(
            blank=True,
            help_text=format_lazy(
                "The copyright statement(s) that pertain to this {verbose_name}, as "
                "contained in the source or as specified in an associated file.",
                verbose_name=_(verbose_name),
            ),
        )

        homepage_url = models.URLField(
            _("Homepage URL"),
            max_length=1024,
            blank=True,
            help_text=format_lazy(
                "Homepage URL for the {verbose_name}.",
                verbose_name=_(verbose_name),
            ),
        )

        primary_language = models.CharField(
            db_index=True,
            max_length=50,
            blank=True,
            help_text=format_lazy(
                "The primary programming language associated with the {verbose_name}.",
                verbose_name=_(verbose_name),
            ),
        )

        admin_notes = models.TextField(
            blank=True,
            help_text=format_lazy(
                "Comments about the {verbose_name}, provided by administrators, "
                "intended for viewing and maintenance by administrators only.",
                verbose_name=_(verbose_name),
            ),
        )

        notice_text = NoStripTextField(
            blank=True,
            help_text=format_lazy(
                "The notice text provided by the authors of a {verbose_name} to identify "
                "the copyright statement(s), contributors, and/or license obligations that apply"
                " to a {verbose_name}.",
                verbose_name=_(verbose_name),
            ),
        )

        class Meta:
            abstract = True
            unique_together = (("dataspace", "name", "version"), ("dataspace", "uuid"))
            ordering = ("name", "version")

        def __str__(self):
            if self.version:
                return f"{self.name} {self.version}"
            return self.name

        def get_url(self, name, params=None):
            if not params:
                params = [self.dataspace.name, quote_plus(self.name)]
                if self.version:
                    params.append(quote_plus(self.version))
            return super().get_url(name, params)

        def get_absolute_url(self):
            return self.get_url("details")

        def get_change_url(self):
            return self.get_url("change")

        def get_delete_url(self):
            return self.get_url("delete")

        def get_about_files_url(self):
            return self.get_url("about_files")

        def get_export_spdx_url(self):
            return self.get_url("export_spdx")

        def get_export_cyclonedx_url(self):
            return self.get_url("export_cyclonedx")

        def get_about_files(self):
            """
            Return the list of all AboutCode files from all the Packages
            related to this instance.
            """
            return [
                about_file
                for package in self.all_packages
                for about_file in package.get_about_files()
            ]

        def as_cyclonedx(self, license_expression_spdx=None):
            """Return this Component/Product as an CycloneDX Component entry."""
            supplier = None
            if self.owner:
                supplier = cyclonedx_contact.OrganizationalEntity(
                    name=self.owner.name,
                    urls=[self.owner.homepage_url],
                )

            expression_spdx = license_expression_spdx or self.concluded_license_expression_spdx
            licenses = []
            if expression_spdx:
                # Using the LicenseExpression directly as the make_with_expression method
                # does not support the "LicenseRef-" keys.
                licenses = [cyclonedx_license.LicenseExpression(value=expression_spdx)]

            if self.__class__.__name__ == "Product":
                component_type = cyclonedx_component.ComponentType.APPLICATION
            else:
                component_type = cyclonedx_component.ComponentType.LIBRARY

            return cyclonedx_component.Component(
                name=self.name,
                type=component_type,
                version=self.version,
                bom_ref=str(self.uuid),
                supplier=supplier,
                licenses=licenses,
                copyright=self.copyright,
                description=self.description,
                cpe=getattr(self, "cpe", None),
                properties=get_cyclonedx_properties(self),
            )

    return BaseComponentMixin


BaseComponentMixin = component_mixin_factory("component")


class ComponentQuerySet(DataspacedQuerySet):
    def with_has_hierarchy(self):
        subcomponents = Subcomponent.objects.filter(
            models.Q(child_id=OuterRef("pk")) | models.Q(parent_id=OuterRef("pk"))
        )
        return self.annotate(has_hierarchy=Exists(subcomponents))


PROJECT_FIELD_HELP = _(
    "Project is a free-form label that you can use to group and find packages and components "
    "that interest you; for example, you may be starting a new development project, "
    "evaluating them for use in a product or you may want to get approval to use them."
)


class Component(
    ReferenceNotesMixin,
    UsagePolicyMixin,
    SetPolicyFromLicenseMixin,
    ExternalReferenceMixin,
    HolderMixin,
    KeywordsMixin,
    CPEMixin,
    LicenseFieldsMixin,
    ParentChildModelMixin,
    BaseComponentMixin,
    DataspacedModel,
):
    license_expression = models.CharField(
        _("Concluded license expression"),
        max_length=1024,
        blank=True,
        db_index=True,
        help_text=LICENSE_EXPRESSION_HELP_TEXT,
    )

    configuration_status = models.ForeignKey(
        to="component_catalog.ComponentStatus",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=CONFIGURATION_STATUS_HELP,
    )

    type = models.ForeignKey(
        to="component_catalog.ComponentType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("A component type provides a label to filter and sort components."),
    )

    approval_reference = models.CharField(
        max_length=200,
        blank=True,
        help_text=_(
            "The name or number of a document (e.g. approval document, contract, etc.) "
            "that indicates that the component is approved for use in your organization."
        ),
    )

    guidance = models.TextField(
        verbose_name=_("Component usage guidance"),
        blank=True,
        help_text=_(
            "Component usage guidance is provided by your organization to specify "
            "recommendations, requirements and restrictions regarding your usage of this "
            "component.",
        ),
    )

    is_active = models.BooleanField(
        verbose_name=_("Is active"),
        null=True,
        db_index=True,
        default=True,
        help_text=_(
            "When set to True (Yes), this field indicates that a component definition in the "
            "catalog is currently in use (active). When set to False (No), this field indicates "
            "that a component is deprecated (inactive) and should not be used, and the component "
            "will not appear in the user views. When the field value is Unknown, the component "
            "will not appear in the user views, usually suggesting that the component has not "
            "yet been evaluated."
        ),
    )

    curation_level = models.PositiveSmallIntegerField(
        db_index=True,
        default=0,
        validators=[validators.MaxValueValidator(100)],
        help_text=_(
            "A numeric value, from 0 to 100, that indicates the level of completeness of "
            "all the pertinent component data, as well as the state of that data being "
            'reviewed by a senior administrator. General guidelines: "10" indicates basic '
            'data present. "20" indicates copyright and notice data are provided. '
            'assigned. "30" indicates all license data are provided. "40" indicates all '
            "available technical details (including URLs and primary language) are provided. "
            '"50" indicates that relevant parent and child are provided. '
            "Any other values are at the discretion of a senior administrative reviewer."
        ),
    )

    COMPONENT_FIELDS_WEIGHT = (
        ("notice_text", 10),
        ("copyright", 5),
        ("description", 5),
        ("packages", 5),
        ("homepage_url", 5),
        ("keywords", 5),
        ("licenses", 5),
        ("notice_filename", 5),
        ("notice_url", 5),
        ("bug_tracking_url", 3),
        ("code_view_url", 3),
        ("primary_language", 3),
        ("release_date", 3),
        ("vcs_url", 3),
        ("owner", 2),
        ("type", 2),
        ("version", 2),
    )

    completion_level = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        help_text=_(
            "Completion level is a number automatically calculated by the application to "
            "indicate the completeness of the data for a specific component. Fields that "
            "influence the calculation include: Notice Text, Copyright, Description, Package, "
            "Homepage URL, Keyword, License, Notice Filename, Notice URL, Bug Tracking URL, "
            "Code View URL, Primary Language, Release Date, VCS URL, Owner, Type, and Version."
        ),
    )

    is_license_notice = models.BooleanField(
        null=True,
        help_text=_(
            "Indicator (Yes, No, Unknown) regarding whether the notice text contains a "
            "statement about the licenses that apply to the component as a whole."
        ),
    )

    is_copyright_notice = models.BooleanField(
        null=True,
        help_text=_(
            "Indicator (Yes, No, Unknown) regarding whether the notice text contains one or "
            "more copyright statements that apply to the component as a whole."
        ),
    )

    is_notice_in_codebase = models.BooleanField(
        null=True,
        help_text=_(
            "Indicator (Yes, No, Unknown) regarding whether a notice is internal to a "
            "component (for example, if the notice text is in the source file header of "
            "the component)."
        ),
    )

    notice_filename = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "Optional filename to identify a notice file associated with a component. If a "
            "filename is not provided, the application will assume that this notice is "
            "internal to this component (for example, in a source file header)."
        ),
    )

    notice_url = models.URLField(
        _("Notice URL"),
        max_length=1024,
        blank=True,
        help_text=_("A URL that contains notice text for a component."),
    )

    dependencies = models.JSONField(
        blank=True,
        default=list,
        help_text=_(
            "Identifies one or more potential dependencies required to deploy a component in "
            "a particular context, with an emphasis on dependencies that may have an impact "
            "on licensing and/or attribution obligations."
        ),
    )

    project = models.CharField(
        max_length=50,
        db_index=True,
        blank=True,
        help_text=PROJECT_FIELD_HELP,
    )

    codescan_identifier = models.URLField(
        max_length=1024,
        blank=True,
        help_text=_("A component identifier from a code scanning application."),
    )

    website_terms_of_use = models.TextField(
        blank=True,
        help_text=_(
            "The Terms of Use or Terms of Service specified on a software project website. "
            "These are terms that apply in addition to or in absence of an asserted license "
            "for a component package."
        ),
    )

    ip_sensitivity_approved = models.BooleanField(
        verbose_name=_("IP sensitivity approved"),
        default=False,
        help_text=_(
            "The component software can be combined with sensitive or critical IP, as determined "
            "by legal review. This information will be used for product architecture review."
        ),
    )

    affiliate_obligations = models.BooleanField(
        default=False,
        help_text=_(
            "The component license contains terms that would impose obligations on a legal entity "
            "affiliate."
        ),
    )

    affiliate_obligation_triggers = models.TextField(
        blank=True,
        help_text=_(
            "Explanation of how affiliate obligations are triggered, and what is the mitigation "
            "strategy."
        ),
    )

    legal_comments = models.TextField(
        blank=True,
        help_text=_(
            "Notes to be entered and shared among legal team members during the legal review "
            "process."
        ),
    )

    sublicense_allowed = models.BooleanField(
        null=True,
        help_text=_(
            "The component license grants some or all of the rights acquired under the original "
            "license, and allows usage of the licensed code to be licensed under an overriding "
            "license, although obligations such as attribution generally still apply. "
            "This allowance is typical of permissive licenses, but is often not allowed in "
            "copyleft and proprietary licenses. The right to sublicense is explicit in some "
            "license texts (such as the MIT License) but is not always stated; implicit "
            "permission to sublicense is a legal interpretation."
        ),
    )

    express_patent_grant = models.BooleanField(
        null=True,
        help_text=_(
            "The license that applies to this component expressly grants a patent license."
        ),
    )

    covenant_not_to_assert = models.BooleanField(
        null=True,
        help_text=_(
            "The license that applies to this component has language that we agree not to assert "
            "our patents against users of a project under this license."
        ),
    )

    indemnification = models.BooleanField(
        null=True,
        help_text=_(
            "The license that applies to this component has one or more scenarios that "
            "require indemnification."
        ),
    )

    legal_reviewed = models.BooleanField(
        default=False,
        help_text=_("This component definition has been reviewed by the organization legal team."),
    )

    DISTRIBUTION_FORMATS_CHOICES = (
        ("Binary", "Binary"),
        ("Source", "Source"),
        ("All - Binary or Source", "All - Binary or Source"),
    )

    distribution_formats_allowed = models.CharField(
        blank=True,
        max_length=30,
        default="",
        choices=DISTRIBUTION_FORMATS_CHOICES,
        help_text=_("The software distribution formats allowed by the component license."),
    )

    acceptable_linkages = ArrayField(
        models.CharField(
            max_length=40,
        ),
        blank=True,
        null=True,
        help_text=_(
            "Your organization's legal review team can identify one or more "
            "specific linkages (software interactions) that are acceptable "
            "between this component and your organization's products in order "
            "to comply with your organization's license compliance standards."
        ),
    )

    export_restrictions = models.TextField(
        blank=True,
        help_text=_(
            "The export restrictions and/or requirements associated with a component as "
            "determined by legal review."
        ),
    )

    approved_download_location = models.URLField(
        max_length=1024,
        blank=True,
        help_text=_(
            "The link to a pristine (unmodified) component package download as specified by "
            "legal review."
        ),
    )

    approved_community_interaction = models.TextField(
        blank=True,
        help_text=_("The community interaction allowed with this software project."),
    )

    licenses = models.ManyToManyField(
        to="license_library.License",
        through="ComponentAssignedLicense",
        help_text=_(
            "The license that applies to a component. There could be more than one license, "
            'in which case a choice is usually required. The expression "(default)" next to '
            "the license name indicates that this license applies to the component even if "
            "you do not assert a particular license."
        ),
    )

    # This reference all the Components associated with self through a
    # Subcomponent relation where self is the parents.
    # Only the children are copied on ParentChild relation type.
    children = models.ManyToManyField(
        to="self",
        through="Subcomponent",
        through_fields=("parent", "child"),
        symmetrical=False,
    )

    # Explicitly declared to be handled by the m2m copy
    packages = models.ManyToManyField(
        to="component_catalog.Package",
        through="ComponentAssignedPackage",
    )

    objects = DataspacedManager.from_queryset(ComponentQuerySet)()

    class Meta(BaseComponentMixin.Meta):
        permissions = (
            ("change_usage_policy_on_component", "Can change the usage_policy of component"),
        )

    @property
    def urn(self):
        return urn.build("component", name=self.name, version=self.version)

    @property
    def details_url(self):
        return self.get_absolute_url()

    @staticmethod
    def get_extra_relational_fields():
        return ["external_references"]

    @property
    def permission_protected_fields(self):
        return {"usage_policy": "change_usage_policy_on_component"}

    @property
    def case_insensitive_unique_on(self):
        return ["name"]

    @property
    def css_icon(self):
        return "fa-puzzle-piece"

    @cached_property
    def package(self):
        """Return the Package instance if 1 and only 1 Package is assigned to this Component."""
        with suppress(ObjectDoesNotExist, MultipleObjectsReturned):
            return self.packages.get()

    def compute_completion_level(self):
        """
        Return the computed value for the completion_level.
        Convert the result based on the fields weight into a percentage.
        For ManyToMany fields, we add the weight if there's at least 1 relation.
        """
        max_weight = 0
        current_weight = 0

        for field_name, weight in self.COMPONENT_FIELDS_WEIGHT:
            max_weight += weight
            field = self._meta.get_field(field_name)
            is_m2m = isinstance(field, models.ManyToManyField)
            field_value = getattr(self, field_name)

            if (is_m2m and field_value.count()) or (not is_m2m and field_value):
                current_weight += weight

        return int(current_weight * 100 / max_weight)

    def update_completion_level(self):
        """
        Update the completion_level of the current instance.
        Using update() rather than save() to avoid noise in the history.
        Hits the DB only if the recomputed value is different from the current
        one.
        Return True if the update was done.
        """
        computed_level = self.compute_completion_level()

        if self.completion_level != computed_level:
            Component.objects.filter(pk=self.pk).update(completion_level=computed_level)
            msg = f"Updated completion_level for Component {self.pk}, new value: {computed_level}"
            logger.debug(msg)
            return True

    @cached_property
    def all_packages(self):
        return self.packages.all()

    def where_used(self, user):
        """Callable made available in the reporting system."""
        return f"Product {self.product_set.get_related_secured_queryset(user).count()}\n"

    @property
    def aboutcode_data(self):
        """
        Return a dict of AboutCode supported fields.
        Fields without a value are not included.
        """
        component_data = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "homepage_url": self.homepage_url,
            "license_expression": self.license_expression,
            "copyright": self.copyright,
            "notice_url": self.notice_url,
            "vcs_repository": self.vcs_url,
        }

        owner = getattr(self, "owner", None)
        if owner:
            component_data.update(
                {
                    "owner": owner.name,
                    "owner_url": owner.homepage_url,
                    "contact": owner.contact_info,
                }
            )

        if self.license_expression:
            component_data.update(
                {
                    "attribute": self.attribution_required,
                    "redistribute": self.redistribution_required,
                    "track_changes": self.change_tracking_required,
                }
            )

        return without_empty_values(component_data)

    def as_spdx(self, license_concluded=None):
        """
        Return this Component as an SPDX Package entry.
        An optional ``license_concluded`` can be provided to override the
        ``license_expression`` value defined on this instance.
        This can be a license choice applied to a Product relationship.
        """
        external_refs = []

        if cpe_external_ref := self.get_spdx_cpe_external_ref():
            external_refs.append(cpe_external_ref)

        attribution_texts = []
        if self.notice_text:
            attribution_texts.append(self.notice_text)

        return spdx.Package(
            name=self.name,
            spdx_id=f"dejacode-{self._meta.model_name}-{self.uuid}",
            supplier=self.owner.as_spdx() if self.owner else "",
            license_concluded=license_concluded or self.concluded_license_expression_spdx,
            license_declared=self.declared_license_expression_spdx,
            copyright_text=self.copyright,
            version=self.version,
            homepage=self.homepage_url,
            description=self.description,
            release_date=str(self.release_date) if self.release_date else "",
            attribution_texts=attribution_texts,
            external_refs=external_refs,
        )

    def get_spdx_packages(self):
        return [self]


@receiver([post_copy, post_update], sender=Component)
def update_completion_level(sender, **kwargs):
    """Update the Component.completion_level after copy or update."""
    kwargs["target"].update_completion_level()


class ComponentRelationshipMixin(models.Model):
    notes = models.TextField(
        blank=True,
        help_text=_(
            "Free form text about how the component is being used in this context, "
            "especially useful if the information is needed for the review process."
        ),
    )

    is_deployed = models.BooleanField(
        default=True,
        help_text=_("Indicates if the component is deployed in this context. Default = True."),
    )

    is_modified = models.BooleanField(
        default=False,
        help_text=_(
            "Indicates if the original third-party component has been modified. Default = False."
        ),
    )

    extra_attribution_text = models.TextField(
        blank=True,
        help_text=_(
            "Additional text to be supplied with the component when attribution is generated. "
            "For example, you may want to explain a license choice when the component is "
            "available under a choice of licenses."
        ),
    )

    package_paths = models.TextField(
        blank=True,
        help_text=_(
            "This field is deprecated in DejaCode. To define one or more specific location(s) "
            "of a Component in a Product, create a Product Codebase Resource for each location, "
            "specifying the codebase path and referencing the Product Component."
        ),
    )

    class Meta:
        abstract = True

    @cached_property
    def related_component_or_package(self):
        """
        Return the related object instance:
            - ProductComponent.component
            - Subcomponent.child
            - ProductPackage.package
        """
        return (
            getattr(self, "component", None)
            or getattr(self, "child", None)
            or getattr(self, "package", None)
        )

    @cached_property
    def standard_notice(self):
        """
        Return a line separated combination of all License.standard_notice associated to
        this relationship.
        """
        return "\n\n".join(
            [license.standard_notice for license in self.licenses.all() if license.standard_notice]
        )


class Subcomponent(
    ReferenceNotesMixin,
    UsagePolicyMixin,
    LicenseExpressionMixin,
    HistoryFieldsMixin,
    ComponentRelationshipMixin,
    ParentChildRelationshipModel,
):
    parent = models.ForeignKey(
        to="component_catalog.Component",
        on_delete=models.CASCADE,
        related_name="related_children",
    )

    child = models.ForeignKey(
        to="component_catalog.Component",
        on_delete=models.CASCADE,
        related_name="related_parents",
    )

    # This license_expression is never generated but always stored.
    license_expression = models.CharField(
        _("License expression"),
        max_length=1024,
        blank=True,
        db_index=True,
        help_text=_(
            "On a subcomponent relationship (which defines a child component of another "
            "component), a license expression is limited by the license(s) assigned to the "
            "child component, and expresses the license(s) that apply to the context of the "
            "child component as it is used by the parent component. More than one applicable "
            'license can be expressed as "license-key-a AND license-key-b". A choice of licenses '
            'can be expressed as "license-key-a OR license-key-b", and you can indicate the '
            "primary license as defined by your business by placing it first, on the left-hand "
            "side of the OR relationship. The relationship words (OR, AND) can be combined as "
            "needed, and the use of parentheses can be applied to clarify the meaning; for "
            'example "((license-key-a AND license-key-b) OR (license-key-c))". An exception '
            'to a license can be expressed as “license-key WITH license-exception-key".'
        ),
    )

    licenses = models.ManyToManyField(
        to="license_library.License",
        through="SubcomponentAssignedLicense",
    )

    purpose = models.CharField(
        max_length=50,
        db_index=True,
        blank=True,
        help_text=_(
            "Indicates how this component/package is used in this context. "
            "Suggested values are: Core, Test, Tool, Build, Reference, Requirement."
        ),
    )

    class Meta:
        verbose_name = _("subcomponent relationship")
        unique_together = (("parent", "child"), ("dataspace", "uuid"))
        ordering = ["parent", "child"]
        permissions = (
            (
                "change_usage_policy_on_subcomponent",
                "Can change the usage_policy of subcomponent relationship",
            ),
        )

    def __str__(self):
        if self.purpose:
            return f"{self.purpose}: {self.child}"
        return f"{self.child}"

    def clean(self, from_api=False):
        # If one of the main Object (child or parent) is not saved in the DB
        # yet then no further validation possible.
        if not self.child_id or not self.parent_id:
            return
        super().clean(from_api)

    @property
    def permission_protected_fields(self):
        return {"usage_policy": "change_usage_policy_on_subcomponent"}

    def get_policy_from_child_component(self):
        """Return the UsagePolicy associated to this Subcomponent child Component."""
        child_policy = self.child.usage_policy
        if child_policy:
            return child_policy.get_associated_policy_to_model(self)

    policy_from_child_component = cached_property(get_policy_from_child_component)


class ComponentAssignedLicense(DataspacedModel):
    component = models.ForeignKey(
        to="component_catalog.Component",
        on_delete=models.CASCADE,
    )

    license = models.ForeignKey(
        to="license_library.License",
        on_delete=models.PROTECT,
        help_text=_("Select from list of licenses."),
    )

    class Meta:
        # 'dataspace' should never be part of the unique_together on
        # Models that are used as a "through" relation. See #7404.
        unique_together = (("component", "license"), ("dataspace", "uuid"))
        ordering = ("component__name", "license__name")
        verbose_name = _("Assigned license")

    def __str__(self):
        return f"{self.component} is under {self.license}."


class SubcomponentAssignedLicense(DataspacedModel):
    subcomponent = models.ForeignKey(
        to="component_catalog.Subcomponent",
        on_delete=models.CASCADE,
    )

    license = models.ForeignKey(
        to="license_library.License",
        on_delete=models.PROTECT,
    )

    class Meta:
        unique_together = (("subcomponent", "license"), ("dataspace", "uuid"))
        verbose_name = _("subcomponent assigned license")

    def __str__(self):
        return f"{self.subcomponent} is under {self.license}."


class AcceptableLinkage(DataspacedModel):
    label = models.CharField(
        max_length=40,
    )

    description = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["label"]
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))

    def __str__(self):
        return self.label

    def has_references(self):
        return (
            Component.objects.scope(self.dataspace)
            .filter(acceptable_linkages__contains=[self.label])
            .exists()
        )


class ComponentKeyword(DataspacedModel):
    label = models.CharField(
        max_length=50,
        blank=True,
        help_text=_(
            "A short, descriptive label to categorize components and support searches, "
            "reports, filters, and facets."
        ),
    )

    description = models.TextField(
        blank=True,
        help_text=_("Additional remarks about the intention and purpose of a Keyword value."),
    )

    class Meta:
        ordering = ["label"]
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))

    def __str__(self):
        return self.label


PACKAGE_URL_FIELDS = ["type", "namespace", "name", "version", "qualifiers", "subpath"]


class PackageQuerySet(PackageURLQuerySetMixin, DataspacedQuerySet):
    def annotate_sortable_identifier(self):
        """
        Annotate the QuerySet with a `sortable_identifier` value that combines
        all the Package URL fields and the filename.
        This value in used in the Package list for sorting by Identifier.
        """
        return self.annotate(
            sortable_identifier=Concat(*PACKAGE_URL_FIELDS, "filename", output_field=CharField())
        )

    def only_rendering_fields(self):
        """Minimum requirements to render a Package element in the UI."""
        return self.only(
            "uuid",
            *PACKAGE_URL_FIELDS,
            "filename",
            "license_expression",
            "dataspace__name",
            "dataspace__show_usage_policy_in_user_views",
        )


class Package(
    ExternalReferenceMixin,
    UsagePolicyMixin,
    SetPolicyFromLicenseMixin,
    LicenseExpressionMixin,
    LicenseFieldsMixin,
    RequestMixin,
    HistoryFieldsMixin,
    ReferenceNotesMixin,
    HolderMixin,
    KeywordsMixin,
    CPEMixin,
    URLFieldsMixin,
    HashFieldsMixin,
    PackageURLMixin,
    DataspacedModel,
):
    filename = models.CharField(
        _("Filename"),
        blank=True,
        db_index=True,
        max_length=255,  # 255 is the maximum on most filesystems
        validators=[validate_filename],
        help_text=_(
            "The exact file name (typically an archive of some type) of the package. "
            "This is usually the name of the file as downloaded from a website."
        ),
    )

    download_url = models.CharField(
        _("Download URL"),
        max_length=1024,
        validators=[generic_uri_validator],
        blank=True,
        help_text=_("The download URL for obtaining the package."),
    )

    sha1 = models.CharField(
        _("SHA1"),
        max_length=40,
        blank=True,
        db_index=True,
        help_text=_("The SHA1 signature of the package file."),
    )

    md5 = models.CharField(
        _("MD5"),
        max_length=32,
        blank=True,
        db_index=True,
        help_text=_("The MD5 signature of the package file."),
    )

    size = models.BigIntegerField(
        blank=True,
        null=True,
        db_index=True,
        help_text=_("The size of the package file in bytes."),
    )

    release_date = models.DateField(
        blank=True,
        null=True,
        help_text=_(
            "The date that the package file was created, or when it was posted to its "
            "original download source."
        ),
    )

    primary_language = models.CharField(
        db_index=True,
        max_length=50,
        blank=True,
        help_text=_("The primary programming language associated with the package."),
    )

    description = models.TextField(
        blank=True,
        help_text=_("Free form description, preferably as provided by the author(s)."),
    )

    project = models.CharField(
        max_length=50,
        db_index=True,
        blank=True,
        help_text=PROJECT_FIELD_HELP,
    )

    notes = models.TextField(
        blank=True,
        help_text=_("Descriptive information about the package."),
    )

    license_expression = models.CharField(
        _("Concluded license expression"),
        max_length=1024,
        blank=True,
        db_index=True,
        help_text=LICENSE_EXPRESSION_HELP_TEXT,
    )

    copyright = models.TextField(
        blank=True,
        help_text=_(
            "The copyright statement(s) that pertain to this package, as contained in the "
            "source or as specified in an associated file."
        ),
    )

    notice_text = NoStripTextField(
        blank=True,
        help_text=_(
            "The notice text provided by the authors of a package to identify the copyright "
            "statement(s), contributors, and/or license obligations that apply to a package."
        ),
    )

    author = models.TextField(
        blank=True,
        help_text=_(
            "The name(s) of the author(s) of a software package as documented in the code."
        ),
    )

    dependencies = models.JSONField(
        blank=True,
        default=list,
        help_text=_(
            "Identifies one or more potential dependencies required to deploy a package in "
            "a particular context, with an emphasis on dependencies that may have an impact "
            "on licensing and/or attribution obligations."
        ),
    )

    repository_homepage_url = models.URLField(
        _("Repository homepage URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "URL to the page for this package in its package repository. "
            "This is typically different from the package homepage URL proper."
        ),
    )

    repository_download_url = models.URLField(
        _("Repository download URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "Download URL to download the actual archive of code of this "
            "package in its package repository. "
            "This may be different from the actual download URL."
        ),
    )

    api_data_url = models.URLField(
        _("API data URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "API URL to obtain structured data for this package such as the "
            "URL to a JSON or XML api its package repository."
        ),
    )

    datasource_id = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("The identifier for the datafile handler used to obtain this package."),
    )

    file_references = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            "List of file paths and details for files referenced in a package "
            "manifest. These may not actually exist on the filesystem. "
            "The exact semantics and base of these paths is specific to a "
            "package type or datafile format."
        ),
    )

    parties = models.JSONField(
        default=list,
        blank=True,
        help_text=_("A list of parties such as a person, project or organization."),
    )

    licenses = models.ManyToManyField(
        to="license_library.License",
        through="PackageAssignedLicense",
    )

    objects = DataspacedManager.from_queryset(PackageQuerySet)()

    class Meta:
        ordering = ["filename"]
        unique_together = (
            ("dataspace", "uuid"),
            # This constraint prevent to insert twice the exact same Package data.
            # If one value of the filename, download_url, or any purl fields, changed,
            # the Package is not a duplicate and can be created.
            # Note that an empty string '' counts as a unique value.
            #
            # A `package_url` can be identical for multiple files.
            # For example, ".zip" and ".whl" release of a Package may share the same `package_url`.
            # Therefore, we only apply this unique constraint on `package_url` in the context of a
            # `download_url` and `filename`.
            # Also, a duplicated `download_url`+`filename` combination is allowed if any of the
            # `package_url` fields is different.
            (
                "dataspace",
                *PACKAGE_URL_FIELDS,
                "download_url",
                "filename",
            ),
        )
        indexes = [
            models.Index(fields=["md5"]),
            models.Index(fields=["sha1"]),
            models.Index(fields=["sha256"]),
            models.Index(fields=["sha512"]),
        ]
        permissions = (
            ("change_usage_policy_on_package", "Can change the usage_policy of package"),
        )

    def __str__(self):
        return self.identifier

    def save(self, *args, **kwargs):
        """Do not allow to save without an identifier."""
        self.enforce_identifier()
        super().save(*args, **kwargs)

    def enforce_identifier(self):
        """Raise a error if an identifier, package_url or filename, is not set."""
        if not self.identifier:
            raise ValidationError("package_url or filename required")

    @property
    def identifier(self):
        """
        Provide a unique value to identify each Package.
        It is the Package URL if one exists; otherwise it is the Package Filename.
        """
        return self.package_url or self.filename

    @classmethod
    def identifier_help(cls):
        return _(
            "Package Identifier is a system-derived field that provides a "
            "unique value to identify each Package. "
            "It is the Package URL if one exists; "
            "otherwise it is the Package Filename."
        )

    @property
    def plain_package_url(self):
        """Package URL without the qualifiers and subpath fields."""
        try:
            package_url = PackageURL(self.type, self.namespace, self.name, self.version)
        except ValueError:
            return ""
        return str(package_url)

    @property
    def short_package_url(self):
        """Plain Package URL (no qualifiers no subpath) without the 'pkg:' prefix."""
        return self.plain_package_url.replace("pkg:", "", 1)

    @property
    def package_url_filename(self):
        """
        Return the Package URL string as a valid filename.
        Useful when `Package.filename` is not available.
        """
        cleaned_package_url = self.plain_package_url
        for char in "/@?=#:":
            cleaned_package_url = cleaned_package_url.replace(char, "_")
        return get_valid_filename(cleaned_package_url)

    @property
    def inferred_url(self):
        """Return the URL deduced from the information available in a Package URL (purl)."""
        return purl2url.get_repo_url(self.package_url)

    def get_url(self, name, params=None, include_identifier=False):
        if not params:
            params = [self.dataspace.name, quote_plus(str(self.uuid))]
            if include_identifier:
                # For the URL, using plain_package_url for simplification
                params.insert(1, self.plain_package_url or self.filename)
        return super().get_url(name, params)

    def get_absolute_url(self):
        return self.get_url("details", include_identifier=True)

    @property
    def details_url(self):
        return self.get_absolute_url()

    def get_change_url(self):
        return self.get_url("change", include_identifier=True)

    def get_delete_url(self):
        return self.get_url("delete")

    def get_about_files_url(self):
        return self.get_url("about_files")

    def get_export_spdx_url(self):
        return self.get_url("export_spdx")

    def get_export_cyclonedx_url(self):
        return self.get_url("export_cyclonedx")

    @classmethod
    def get_identifier_fields(cls, *args, purl_fields_only=False, **kwargs):
        """
        Explicit list of identifier fields as we do not enforce a unique together
        on this model.
        This is used in the Importer, to catch duplicate entries.
        The purl_fields_only option can be use to limit the results.
        """
        if purl_fields_only:
            return PACKAGE_URL_FIELDS

        return ["filename", "download_url", *PACKAGE_URL_FIELDS]

    @property
    def permission_protected_fields(self):
        return {"usage_policy": "change_usage_policy_on_package"}

    @staticmethod
    def autocomplete_term_adjust(term):
        """Cleanup the `term` string replacing some special chars into spaces."""
        chars_to_replace_ = "-_@/"
        for char in chars_to_replace_:
            term = term.replace(char, " ")
        return term

    def collect_data(self, force_update=False, save=True):
        """
        Download the Package content using the `download_url` to collect the
        md5, sha1, sha256, sha512, size, and filename.
        If all values for those fields are set, the process
        will be skipped unless the `force_update` option is given.
        Return `True` if the package instance was updated.
        """
        if not self.download_url:
            tasks_logger.info("No Download URL available.")
            return

        collect_fields = [
            "size",
            "md5",
            "sha1",
            "sha256",
            "sha512",
            "filename",
        ]

        all_has_values = all(getattr(self, field_name, None) for field_name in collect_fields)
        if all_has_values and not force_update:
            tasks_logger.info("Size, MD5, SHA1, SH256, SHA512, and filename values already set.")
            return

        try:
            package_data = collect_package_data(self.download_url)
        except DataCollectionException as e:
            tasks_logger.info(e)
            return
        tasks_logger.info("Package data collected.")

        update_fields = []
        for field_name in collect_fields:
            if not getattr(self, field_name, None):
                setattr(self, field_name, package_data.get(field_name))
                update_fields.append(field_name)

        if save:
            self.save(update_fields=update_fields)
            tasks_logger.info(f'Package field(s) updated: {", ".join(update_fields)}')

        return update_fields

    def update_package_url(self, user, save=False, overwrite=False, history=False):
        """
        Generate and set a Package URL from the Download URL on this Package instance.
        By default, update() is used on the Package to avoid updating field such as
        `last_modified_date`. save() can be used instead providing the `save` argument.
        Existing Package URL value can be overwritten using the `overwrite` argument.
        When `history` is True, History entry will be created along updating the
        Package URL.
        """
        skip_conditions = [self.package_url and not overwrite, not self.download_url]
        if any(skip_conditions):
            return

        package_url = url2purl.get_purl(self.download_url)
        if not package_url or str(package_url) == str(self.package_url):
            return

        if save:
            self.set_package_url(package_url)
            self.last_modified_by = user
            self.save()
        else:
            package_url_dict = package_url.to_dict(encode=True, empty="")
            Package.objects.filter(pk=self.pk).update(**package_url_dict)

        if history:
            History.log_change(user, self, message="Set Package URL from Download URL")

        return package_url

    @property
    def size_formatted(self):
        if self.size:
            return f"{self.size} ({filesizeformat(self.size)})"

    @cached_property
    def component(self):
        """
        Return the Component instance if 1 and only 1 Component is assigned to this
        Package.
        Using ``component_set.all()`` to benefit from prefetch_related when it was
        applied to the Package QuerySet.
        """
        component_set = self.component_set.all()
        if len(component_set) == 1:
            return component_set[0]

    def set_values_from_component(self, component, user):
        changed_fields = set_fields_from_object(
            source=component,
            target=self,
            fields=COMPONENT_PACKAGE_COMMON_FIELDS,
        )
        if changed_fields:
            self.last_modified_by = user
            self.save()
            change_message = [{"changed": {"fields": changed_fields}}]
            History.log_change(user, self, message=change_message)
            return changed_fields

    @property
    def css_icon(self):
        return "fa-archive"

    @classmethod
    def package_url_help(cls):
        return _(
            'A Package URL "purl" is a URL string used to identify and locate '
            "a software package in a mostly universal and uniform way across "
            "programing languages, package managers, packaging conventions, "
            "tools, APIs and databases."
        )

    @property
    def aboutcode_data(self):
        """
        Return a dict of AboutCode supported fields.
        Fields without a value are not included.
        """
        package_data = {
            "about_resource": self.filename or ".",
            "package_url": self.package_url,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "checksum_sha1": self.sha1,
            "checksum_md5": self.md5,
            "copyright": self.copyright,
            "download_url": self.download_url,
            "homepage_url": self.homepage_url,
            "license_expression": self.license_expression,
            "notes": self.notes,
        }

        if self.license_expression:
            package_data.update(
                {
                    "attribute": self.attribution_required,
                    "redistribute": self.redistribution_required,
                    "track_changes": self.change_tracking_required,
                }
            )

        return without_empty_values(package_data)

    def as_about(self, extra=None):
        """
        Return ABOUT file data as a dict.
        https://github.com/nexB/aboutcode-toolkit/blob/develop/SPECIFICATION.rst

        Optionally provided `extra` dict will be added to the returned data.

        If one and only one Component is assigned to the Package, the Component values
        will be included if the corresponding Package field is empty.
        """
        package_data = self.aboutcode_data

        component = self.component
        if component:
            # Overrides Component data with available Package data
            aboutcode_data = {**component.aboutcode_data, **package_data}
        else:
            aboutcode_data = package_data

        if extra:
            aboutcode_data.update(extra)

        return aboutcode_data

    def as_about_yaml(self, extra=None):
        """Return ABOUT file data YAML formatted."""
        about_data = self.as_about(extra)
        if about_data:
            about = About()
            about.load_dict(about_data, base_dir="")
            return about.dumps()

    @property
    def about_file_name(self):
        """
        Return the ABOUT file filename.
        Using the `Package.filename` when available, or the Package URL slug.
        """
        return f"{self.filename or self.package_url_filename}.ABOUT"

    @property
    def notice_file_name(self):
        """
        Return the NOTICE file filename.
        Using the `Package.filename` when available, or the Package URL slug.
        """
        return f"{self.filename or self.package_url_filename}.NOTICE"

    def get_about_files(self):
        """
        Return a list of all AboutCode files related to that Package:
          - .ABOUT
          - .NOTICE
          - .LICENSE
        """
        about_files = []
        extra = {}

        notice_text = self.notice_text
        component = self.component
        if component and component.notice_text:
            notice_text = component.notice_text

        if notice_text:
            about_files.append((self.notice_file_name, normalize_newlines(notice_text)))
            extra["notice_file"] = self.notice_file_name

        licenses = []
        # Using `license_expression` fields to avoid extra DB queries.
        if component and component.license_expression:
            licenses = component.licenses.all()
        elif self.license_expression:
            licenses = self.licenses.all()

        for license_instance in licenses:
            license_file_name = f"{license_instance.key}.LICENSE"
            normalized_text = normalize_newlines(license_instance.full_text)
            about_files.append((license_file_name, normalized_text))
            extra.setdefault("licenses", []).append(
                {
                    "key": license_instance.key,
                    "name": license_instance.name,
                    "file": license_file_name,
                }
            )

        about_files.append((self.about_file_name, self.as_about_yaml(extra)))

        return about_files

    def as_spdx(self, license_concluded=None):
        """
        Return this Package as an SPDX Package entry.
        An optional ``license_concluded`` can be provided to override the
        ``license_expression`` value defined on this instance.
        This can be a license choice applied to a Product relationship.
        """
        checksums = [
            spdx.Checksum(algorithm=algorithm, value=checksum_value)
            for algorithm in ["sha1", "md5"]
            if (checksum_value := getattr(self, algorithm))
        ]

        attribution_texts = []
        if self.notice_text:
            attribution_texts.append(self.notice_text)

        external_refs = []

        if package_url := self.package_url:
            external_refs.append(
                spdx.ExternalRef(
                    category="PACKAGE-MANAGER",
                    type="purl",
                    locator=package_url,
                )
            )

        if cpe_external_ref := self.get_spdx_cpe_external_ref():
            external_refs.append(cpe_external_ref)

        return spdx.Package(
            name=self.name or self.filename,
            spdx_id=f"dejacode-{self._meta.model_name}-{self.uuid}",
            download_location=self.download_url,
            license_concluded=license_concluded or self.concluded_license_expression_spdx,
            license_declared=self.declared_license_expression_spdx,
            copyright_text=self.copyright,
            version=self.version,
            homepage=self.homepage_url,
            filename=self.filename,
            description=self.description,
            release_date=str(self.release_date) if self.release_date else "",
            comment=self.notes,
            attribution_texts=attribution_texts,
            checksums=checksums,
            external_refs=external_refs,
        )

    def get_spdx_packages(self):
        return [self]

    def as_cyclonedx(self, license_expression_spdx=None):
        """Return this Package as an CycloneDX Component entry."""
        expression_spdx = license_expression_spdx or self.concluded_license_expression_spdx

        licenses = []
        if expression_spdx:
            # Using the LicenseExpression directly as the make_with_expression method
            # does not support the "LicenseRef-" keys.
            licenses = [cyclonedx_license.LicenseExpression(value=expression_spdx)]

        hash_fields = {
            "md5": cyclonedx_model.HashAlgorithm.MD5,
            "sha1": cyclonedx_model.HashAlgorithm.SHA_1,
            "sha256": cyclonedx_model.HashAlgorithm.SHA_256,
            "sha512": cyclonedx_model.HashAlgorithm.SHA_512,
        }
        hashes = [
            cyclonedx_model.HashType(alg=algorithm, content=hash_value)
            for field_name, algorithm in hash_fields.items()
            if (hash_value := getattr(self, field_name))
        ]

        package_url = self.get_package_url()
        return cyclonedx_component.Component(
            name=self.name,
            version=self.version,
            bom_ref=str(package_url) or str(self.uuid),
            purl=package_url,
            licenses=licenses,
            copyright=self.copyright,
            description=self.description,
            cpe=self.cpe,
            author=self.author,
            hashes=hashes,
            properties=get_cyclonedx_properties(self),
        )

    @cached_property
    def github_repo_url(self):
        """Generate a GitHub code view URL from a Download URL if the format is known."""
        if not self.download_url:
            return

        patterns = [
            r"^https?://github.com/(?P<owner>.+)/(?P<repo>.+)/archive/(?P<branch>.+)"
            r"(.zip|.tar.gz)$",
            r"^https?://github.com/(?P<owner>.+)/(?P<repo>.+)/releases/download/(?P<branch>.+)/.*$",
        ]

        for pattern in patterns:
            compiled_pattern = re.compile(pattern, re.VERBOSE)
            match = compiled_pattern.match(self.download_url)
            if match:
                url_template = "https://github.com/{owner}/{repo}/tree/{branch}"
                return url_template.format(**match.groupdict())

    def where_used(self, user):
        """Callable for the reporting system."""
        return (
            f"Product {self.product_set.get_related_secured_queryset(user).count()}\n"
            f"Component {self.component_set.count()}\n"
        )

    @classmethod
    def create_from_url(cls, url, user):
        """
        Create a package from the given URL for the specified user.

        This function processes the URL to create a package entry. It handles
        both direct download URLs and Package URLs (purls), checking for
        existing packages to avoid duplicates. If the package is not already
        present, it collects necessary package data and creates a new package
        entry.
        """
        url = url.strip()
        if not url:
            return

        package_data = {}
        scoped_packages_qs = cls.objects.scope(user.dataspace)

        if is_purl_str(url):
            download_url = purl2url.get_download_url(url)
            package_url = PackageURL.from_string(url)
            existing_packages = scoped_packages_qs.for_package_url(url, exact_match=True)
        else:
            download_url = url
            package_url = url2purl.get_purl(url)
            existing_packages = scoped_packages_qs.filter(download_url=url)

        if existing_packages:
            package_links = [package.get_absolute_link() for package in existing_packages]
            raise PackageAlreadyExistsWarning(
                f"{url} already exists in your Dataspace as {', '.join(package_links)}"
            )

        # Matching in PurlDB early to avoid more processing in case of a match.
        purldb_data = None
        if user.dataspace.enable_purldb_access:
            package_for_match = cls(download_url=download_url)
            package_for_match.set_package_url(package_url)
            purldb_entries = package_for_match.get_purldb_entries(user)
            # Look for one ith the same exact purl in that case
            if purldb_data := pick_purldb_entry(purldb_entries, purl=url):
                # The format from PurlDB is "2019-11-18T00:00:00Z" from DateTimeField
                if release_date := purldb_data.get("release_date"):
                    purldb_data["release_date"] = release_date.split("T")[0]
                package_data.update(purldb_data)

        if download_url and not purldb_data:
            package_data = collect_package_data(download_url)

        if sha1 := package_data.get("sha1"):
            if sha1_match := scoped_packages_qs.filter(sha1=sha1):
                package_link = sha1_match[0].get_absolute_link()
                raise PackageAlreadyExistsWarning(
                    f"{url} already exists in your Dataspace as {package_link}"
                )

        # Duplicate the declared_license_expression into the license_expression field.
        if declared_license_expression := package_data.get("declared_license_expression"):
            package_data["license_expression"] = declared_license_expression

        if package_url:
            package_data.update(package_url.to_dict(encode=True, empty=""))

        package = cls.create_from_data(user, package_data)
        return package

    def get_purldb_entries(self, user, max_request_call=0, timeout=None):
        """
        Return the PurlDB entries that correspond to this Package instance.

        Matching on the following fields order:
        - Package URL
        - SHA1
        - Download URL

        A `max_request_call` integer can be provided to limit the number of
        HTTP requests made to the PackageURL server.
        By default, one request will be made per field until a match is found.
        Providing max_request_call=1 will stop after the first request, even
        is nothing was found.
        """
        payloads = []

        package_url = self.package_url
        if package_url:
            payloads.append({"purl": package_url})
        if self.sha1:
            payloads.append({"sha1": self.sha1})
        if self.download_url:
            payloads.append({"download_url": self.download_url})

        for index, payload in enumerate(payloads):
            if max_request_call and index >= max_request_call:
                return

            packages_data = PurlDB(user.dataspace).find_packages(payload, timeout)
            if packages_data:
                return packages_data


class PackageAssignedLicense(DataspacedModel):
    package = models.ForeignKey(
        to="component_catalog.Package",
        on_delete=models.CASCADE,
    )

    license = models.ForeignKey(
        to="license_library.License",
        on_delete=models.PROTECT,
    )

    class Meta:
        unique_together = (("package", "license"), ("dataspace", "uuid"))
        verbose_name = _("package assigned license")

    def __str__(self):
        return f"{self.package} is under {self.license}."


class ComponentAssignedPackage(DataspacedModel):
    component = models.ForeignKey(
        to="component_catalog.Component",
        on_delete=models.CASCADE,
    )

    package = models.ForeignKey(
        to="component_catalog.Package",
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = (("component", "package"), ("dataspace", "uuid"))
        ordering = ("component", "package")
        verbose_name = _("component assigned package")

    def __str__(self):
        return f"<{self.component}>: {self.package}"
