#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import re
from collections import OrderedDict

from django.apps import apps
from django.core import validators
from django.core.exceptions import MultipleObjectsReturned
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CharField
from django.db.models import Value
from django.db.models.functions import Concat
from django.template.defaultfilters import truncatechars
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.html import mark_safe
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from dejacode_toolkit import spdx
from dje import urn
from dje.fields import NoStripTextField
from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import ExternalReferenceMixin
from dje.models import HistoryFieldsMixin
from dje.models import ReferenceNotesMixin
from policy.models import UsagePolicyMixin
from workflow.models import RequestMixin

license_library_app = apps.get_app_config("license_library")

# WARNING: Some "exception" entries cannot be access without the `.html` extension.
# It should always be included to ensure the validity of the generated SPDX URLs.
SPDX_LICENSE_URL = "https://spdx.org/licenses/{}.html"
SCANCODE_LICENSEDB_URL = "https://scancode-licensedb.aboutcode.org/{}"
SCANCODE_DATA_BASE_URL = (
    "https://github.com/nexB/scancode-toolkit/tree/develop/src/licensedcode/data"
)
SCANCODE_LICENSE_URL = f"{SCANCODE_DATA_BASE_URL}/licenses/{{}}.LICENSE"

# Add the dot "." to the Slug validation
slug_plus_re = re.compile(r"^[-\w\.]+$")
validate_slug_plus = validators.RegexValidator(
    slug_plus_re,
    _("Enter a valid 'slug' consisting of letters, numbers, underscores, dots or hyphens."),
    "invalid",
)


spdx_license_key_re = re.compile(r"^[a-zA-Z\d\-.]+$")
validate_spdx_license_key = validators.RegexValidator(
    spdx_license_key_re,
    _("Enter a valid value consisting of letters, numbers, dots or hyphens."),
    "invalid",
)


class LicenseCategory(DataspacedModel):
    label = models.CharField(
        max_length=50,
        help_text=_("The descriptive name of a License Category."),
    )

    text = models.TextField(
        help_text=_("Descriptive, explanatory text about a License Category."),
    )

    LICENSE_TYPES = (
        ("Open Source", "Open Source"),
        ("Closed Source", "Closed Source"),
    )

    license_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        choices=LICENSE_TYPES,
        db_index=True,
        help_text=_(
            "A License Type identifies the high level nature of a License "
            "Category: Open Source or Closed Source."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))
        ordering = ["label"]
        verbose_name_plural = _("license categories")

    def __str__(self):
        return self.label


class LicenseTag(DataspacedModel):
    label = models.CharField(
        max_length=50,
        help_text=_(
            "Organization-defined Label to identify a Tag that can be applied to a " "Tag Group."
        ),
    )

    text = models.TextField(
        help_text=_(
            "Text to describe a Tag that can be applied to a Tag Group by an Organization."
        ),
    )

    guidance = models.TextField(
        blank=True,
        help_text=_(
            "Detailed description of the criteria for setting the Tag assigned value, "
            "including examples (snippets) of representative license text that supports "
            "the determination of the License Tag assigned value."
        ),
    )

    default_value = models.BooleanField(
        null=True,
        help_text=_("Yes, No, Unknown"),
    )

    show_in_license_list_view = models.BooleanField(
        default=False,
        help_text=format_lazy(
            "When true (checked), include this Tag (both label and value) in the {license_app} "
            "Viewer. Intended for the most critical Tags only, such as those associated with "
            "source code redistribution and patent impact.",
            license_app=_("License Library"),
        ),
    )

    attribution_required = models.BooleanField(
        default=False,
        help_text=_(
            "When true (checked), a license with this Tag requires attribution in the source "
            "code or the documentation of the product where the licensed software is being used, "
            "or both."
        ),
    )

    redistribution_required = models.BooleanField(
        default=False,
        help_text=_(
            "When true (checked), a license with this Tag requires the product documentation to "
            "include instructions regarding how to obtain source code for the licensed software, "
            "including any modifications to it."
        ),
    )

    change_tracking_required = models.BooleanField(
        default=False,
        help_text=_(
            "When true (checked), a license with this Tag requires any modifications to licensed "
            "software to be documented in the source code, the associated product documentation, "
            "or both."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))
        ordering = ["label"]

    def __str__(self):
        return self.label

    def get_slug_label(self):
        return "tag__" + self.label.lower().replace(" ", "_").replace("-", "_")


class LicenseProfile(DataspacedModel):
    name = models.CharField(
        max_length=50,
        help_text=format_lazy(
            "A descriptive name for the {verbose_name}.",
            verbose_name=_("License profile"),
        ),
    )

    tags = models.ManyToManyField(
        to="license_library.LicenseTag",
        through="LicenseProfileAssignedTag",
    )

    examples = models.TextField(
        blank=True,
        help_text=format_lazy(
            "Free-form text to identify examples of licenses that illustrate this {verbose_name}.",
            verbose_name=_("License profile"),
        ),
    )

    notes = models.TextField(
        blank=True,
        help_text=format_lazy(
            "Extended notes about a {verbose_name} (for example, to explain some kind of "
            "special obligation).",
            verbose_name=_("License profile"),
        ),
    )

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ["name"]
        verbose_name = _("license profile")

    def __str__(self):
        return self.name

    def get_assigned_tags_html(self):
        template = """
        <div class="media">
            <img alt="{}" src="{}">
            <p>{}</p>
        </div>"""

        tags = []
        for obj in self.licenseprofileassignedtag_set.all():
            img = static("img/icon-no-gray.png")
            if bool(obj.value):
                img = static("img/icon-yes.png")
            tags.append(template.format(obj.value, img, obj.license_tag.label))

        return format_html('<div class="assigned_tags">{}</div>', mark_safe("".join(tags)))

    get_assigned_tags_html.short_description = "Assigned tags"


class LicenseProfileAssignedTag(DataspacedModel):
    license_profile = models.ForeignKey(
        to="license_library.LicenseProfile",
        on_delete=models.CASCADE,
        help_text=format_lazy(
            "The ID of the {license_profile} to which this {license_tag}, with its "
            "corresponding value, has been assigned to a dataspace.",
            license_profile=_("License profile"),
            license_tag=_("License tag"),
        ),
    )

    license_tag = models.ForeignKey(
        to="license_library.LicenseTag",
        on_delete=models.PROTECT,
        verbose_name=_("License tag"),
        help_text=format_lazy(
            "The ID of the {license_tag} which, with its corresponding value, has been assigned "
            "in a dataspace to this {license_profile}",
            license_profile=_("License profile"),
            license_tag=_("License Tag"),
        ),
    )

    value = models.BooleanField(
        default=False,
    )

    class Meta:
        ordering = ["license_tag__label"]
        unique_together = (("license_profile", "license_tag"), ("dataspace", "uuid"))
        verbose_name = _("license profile assigned tag")

    def __str__(self):
        return f'"{self.license_tag.label}" in "{self.license_profile}": {self.value}'

    def unique_filters_for(self, target):
        """
        Return the unique filters data dict.
        Custom identifier for LicenseProfileAssignedTag.
        Required as there is no unique_together other than the uuid.
        """
        return {
            "license_profile__uuid": self.license_profile.uuid,
            "license_tag__uuid": self.license_tag.uuid,
            "dataspace": target,
        }


class LicenseStyle(DataspacedModel):
    name = models.CharField(
        max_length=50,
        help_text=_("A descriptive name for the License Style."),
    )

    notes = models.TextField(
        blank=True,
        help_text=_(
            "Additional explanation of the License Style, such as the nature of any "
            "license choices."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ["name"]

    def __str__(self):
        return self.name


class LicenseStatus(DataspacedModel):
    code = models.CharField(
        max_length=50,
        help_text=_(
            "Organization-defined Code to identify a Status that can be applied to a " "License."
        ),
    )

    text = models.TextField(
        help_text=_(
            "Text to describe a Status that can be applied to a License by an " "Organization."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "code"), ("dataspace", "uuid"))
        ordering = ["code"]
        verbose_name_plural = _("license status")

    def __str__(self):
        return self.text


class LicenseTagGroup(DataspacedModel):
    name = models.CharField(
        max_length=50,
        help_text="A descriptive name for the Tag Group.",
    )

    tags = models.ManyToManyField(
        to="license_library.LicenseTag",
        through="LicenseTagGroupAssignedTag",
    )

    seq = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        help_text=_(
            "The order in which a License Tag should be presented in the context of the "
            "other License Tag."
        ),
    )

    notes = models.TextField(
        blank=True,
        help_text=_(
            "Extended notes about a Tag Group (for example, to explain some kind of "
            "special obligation)."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ["seq"]

    def __str__(self):
        return self.name


class LicenseTagGroupAssignedTag(DataspacedModel):
    license_tag_group = models.ForeignKey(
        to="license_library.LicenseTagGroup",
        on_delete=models.CASCADE,
    )

    license_tag = models.ForeignKey(
        to="license_library.LicenseTag",
        on_delete=models.PROTECT,
    )

    seq = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        help_text=_(
            "The order in which a License Tag Group should be presented in the context "
            "of the other License Tag Group."
        ),
    )

    class Meta:
        ordering = ("license_tag_group__seq", "seq")
        unique_together = (("license_tag_group", "license_tag"), ("dataspace", "uuid"))

    def __str__(self):
        # WARNING: This is very un-efficient without the proper select/prefetch_related on the QS.
        # We should consider f'{self.license_tag_group_id}: {self.license_tag_id}' instead
        return f"{self.license_tag_group.name}: {self.license_tag.label}"

    def unique_filters_for(self, target):
        """
        Return the unique filters data dict.
        Custom identifier for LicenseTagGroupAssignedTag.
        Required as there is no unique_together other than the uuid.
        """
        return {
            "license_tag_group__uuid": self.license_tag_group.uuid,
            "license_tag__uuid": self.license_tag.uuid,
            "dataspace": target,
        }


class LicenseSymbolMixin:
    """
    A mixin that makes the object behave and look like a license-expression
    LicenseSymbol.
    """

    @property
    def aliases(self):
        """
        Return a tuple of alias strings used to recognize this license when parsing a
        license expression.

        When a license_expression.Licensing object is created by passing it a list of
        License instance (e.g. a query set), the license key and any aliases string
        of each license are used to resolve expressions licenses to a an actual
        License.

        This would typically be a list of short, long name, alternative names (e.g.
        SPDX), etc that can be used to represent a license in an expression.
        """
        return [self.short_name]

    def render(self, template, as_link=False, show_policy=False, **kwargs):
        """
        Return a formatted string that represent this license using the `template`
        format string.

        If `as_link` is True, the license will be rendered as an HTML link.

        This method is called indirectly when the render(template)
        method is called to render a license expression object as a
        string.

        *args and **kwargs are passed down and the same that were used
        when calling render(template, *args and **kwargs) method
        directly on an expression object
        """
        if as_link:
            # Ignore the template as we use our own HTML link rendering
            rendered = self.get_details_url_for_expression()
        else:
            rendered = template.format(symbol=self)

        if kwargs.get("show_category") and self.category_id:
            rendered = f'<span data-bs-toggle="tooltip" title="{self.category}">{rendered}</span>'

        if show_policy and self.usage_policy_id:
            rendered = (
                f'<span class="text-nowrap">'
                f"{rendered}{self.get_usage_policy_icon_tooltip()}"
                f"</span>"
            )

        return rendered


class LicenseQuerySet(DataspacedQuerySet):
    def for_expression(self, license_keys=None):
        qs = self.only(
            "key",
            "name",
            "short_name",
            "spdx_license_key",
            "is_exception",
            "usage_policy",
            "dataspace",
        ).select_related("dataspace", "usage_policy")

        if license_keys:
            qs = qs.filter(key__in=license_keys)

        return qs

    def data_for_expression_builder(self):
        screen_name_annotation = Concat(
            "short_name",
            Value(" ("),
            "key",
            Value(")"),
            output_field=CharField(),
        )

        return list(
            self.annotate(screen_name=screen_name_annotation).values_list("screen_name", "key")
        )


class License(
    LicenseSymbolMixin,
    ReferenceNotesMixin,
    UsagePolicyMixin,
    ExternalReferenceMixin,
    HistoryFieldsMixin,
    RequestMixin,
    DataspacedModel,
):
    owner = models.ForeignKey(
        to="organization.Owner",
        on_delete=models.PROTECT,
        help_text=_(
            "An owner is an entity that is the original author or custodian  of one or "
            "more software licenses, and which is responsible for the text of that license."
        ),
    )

    key = models.CharField(
        db_index=True,
        max_length=50,
        help_text=_("Unique key name of the license."),
        validators=[validate_slug_plus],
    )

    name = models.CharField(
        db_index=True,
        max_length=100,
        help_text=_("The full name of the license, as provided by the original authors."),
    )

    short_name = models.CharField(
        db_index=True,
        max_length=50,
        verbose_name=_("Short Name"),
        help_text=_("Most commonly used name for the license, often abbreviated."),
    )

    keywords = models.CharField(
        db_index=True,
        max_length=500,
        blank=True,
        help_text=_(
            "Keywords to associate with a license to ensure that the license will be "
            "found when a user searches on one or more of the keywords. Examples include "
            "alternative names for the license, or file/product names that are commonly "
            "associated with the license."
        ),
    )

    homepage_url = models.URLField(
        _("Homepage URL"),
        max_length=1024,
        blank=True,
        help_text=_("Homepage URL for the license."),
    )

    full_text = NoStripTextField(
        blank=True,
        help_text=_(
            "The full text of the license. Note that actual usage of a license with "
            "software may include copyright statements and owner information."
        ),
    )

    standard_notice = NoStripTextField(
        blank=True,
        help_text=_("The standard notice text for this license if it exists."),
    )

    text_urls = models.TextField(
        _("Text URLs"),
        blank=True,
        help_text=_(
            "URLs to the text of the license (plain text or HTML) on the main site of "
            "this license."
        ),
    )

    faq_url = models.URLField(
        _("FAQ URL"),
        max_length=1024,
        blank=True,
        help_text=_("URL of a page with Frequently Asked Questions about this license."),
    )

    osi_url = models.URLField(
        _("OSI URL"),
        max_length=1024,
        blank=True,
        help_text=_("URL on the OSI website http://opensource.org for OSI-approved licenses."),
    )

    other_urls = models.TextField(
        _("Other URLs"),
        blank=True,
        help_text=_(
            "Other URLs that identify this license, such as URLs to this license in "
            "different open-source projects. Obsolete links may be kept here, as they "
            "may be useful for historical analysis purpose."
        ),
    )

    reviewed = models.BooleanField(
        default=False,
        help_text=_(
            "True / False (yes/no) - regarding whether a system license definition has "
            "been reviewed by an administrator. Defaults to False."
        ),
    )

    publication_year = models.CharField(
        max_length=4,
        blank=True,
        help_text=_("Year this license was first published, in four-digits format."),
    )

    spdx_license_key = models.CharField(
        _("SPDX short identifier"),
        db_index=True,
        blank=True,
        max_length=50,
        validators=[validate_spdx_license_key],
        help_text=_(
            "Short identifier of the license as stated on each license detail page at "
            "https://spdx.org/licenses/ or a LicenseRef value that points to another "
            "license list."
        ),
    )

    category = models.ForeignKey(
        to="license_library.LicenseCategory",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text=_(
            "A license category, identified by a code, provides a major grouping for "
            "licenses, generally describing the relationship between the licensor and "
            "licensee."
        ),
    )

    license_style = models.ForeignKey(
        to="license_library.LicenseStyle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_(
            "A license style identifies a group of miscellaneous characteristics about a "
            "license, which may include a combination of restrictions about software "
            "modification and usage"
        ),
    )

    license_profile = models.ForeignKey(
        to="license_library.LicenseProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("License profile"),
        help_text=format_lazy(
            "{verbose_name}: a selection of license tags and their values, identified by a "
            "numeric code, in order to provide a convenient way to assign a set of tag values to "
            "a license. "
            'A "Tag" identifies a frequently encountered obligation, restriction, or other '
            "notable characteristic of license terms. "
            "Note that individual tag value assignments may vary by license.",
            verbose_name=_("License profile"),
        ),
    )

    license_status = models.ForeignKey(
        to="license_library.LicenseStatus",
        verbose_name=_("configuration status"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_(
            "An organization can use the license status to communicate the current stage "
            "of the license configuration review process."
        ),
    )

    is_active = models.BooleanField(
        verbose_name=_("Is active"),
        null=True,
        db_index=True,
        help_text=_(
            "When set to True (Yes), this field indicates that a license definition in the "
            "library is currently in use (active). When set to False (No), this field indicates "
            "that a license is deprecated (inactive) and should not be used, and the license "
            "will not appear in the user views. When the field value is Unknown, the license "
            "will not appear in the user views, usually suggesting that the license has not "
            "yet been evaluated."
        ),
    )

    curation_level = models.PositiveSmallIntegerField(
        db_index=True,
        default=0,
        validators=[validators.MaxValueValidator(100)],
        help_text=_(
            "A numeric value, from 0 to 100, that indicates the level of completeness of all the "
            "pertinent license data, as well as the state of that data being reviewed by a senior "
            'administrator. General Guidelines: "10" indicates basic data present. "20" indicates '
            'Category and License Style assigned. "30" indicates all Obligation Tags are set. '
            '"40" indicates all License Tags are set. "50" indicates all previous conditions '
            "plus URL fields set. Anything above that is at the discretion of a senior "
            "administrative reviewer."
        ),
    )

    admin_notes = models.TextField(
        blank=True,
        help_text=_(
            "Internal notes for administrative use only, primarily intended to "
            "communicate special considerations about the interpretation of a license."
        ),
    )

    guidance = models.TextField(
        blank=True,
        help_text=format_lazy(
            "Guidance notes maintained by an administrator to be communicated to the users who "
            "view the {license_app}, primarily intended to provide cautionary and/or policy "
            "information.",
            license_app=_("License Library"),
        ),
    )

    special_obligations = models.TextField(
        blank=True,
        help_text=format_lazy(
            "A concise description, maintained by an administrator, of the obligations "
            "(or restrictions) mandated by the license which are not communicated by the "
            "standard tag assignments of {license_profile} associated with this License.",
            license_profile=_("License profile"),
        ),
    )

    tags = models.ManyToManyField(
        to="license_library.LicenseTag",
        through="LicenseAssignedTag",
    )

    is_component_license = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_(
            "When set to Yes, indicates that this license is assigned by a "
            "component-creator to one or more versions of a component, and is not "
            "generally used by other components."
        ),
    )

    is_exception = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_(
            "When set to Yes, indicates that this license is actually an "
            "exception applied to another license in order to modify "
            "specific conditions of that other license."
        ),
    )

    guidance_url = models.CharField(
        _("Guidance URL"),
        max_length=1024,
        blank=True,
        help_text=_(
            "A URL to a page that documents your organization's policies and procedures "
            "that relate to the obligations and restrictions associated with this "
            "license or with similar licenses."
        ),
    )

    popularity = models.PositiveSmallIntegerField(
        db_index=True,
        default=0,
        help_text=_(
            "A numeric value assigned to a license and maintained by a DejaCode "
            "administrator, that indicates the relative popularity of a license as used by "
            "public software projects. The value influences the default license ordering "
            "of the User License List, as well as the ordering of the suggested licenses "
            "presented as a dropdown list when you enter text in a DejaCode license "
            "expression field. Popularity values are originally provided in DejaCode "
            "Reference Data, but your administrator has the option to modify them for your "
            "dataspace."
        ),
    )

    language = models.CharField(
        max_length=10,
        choices=license_library_app.languages,
        blank=True,
        help_text=_("The language for this license, stored in standard language ID format."),
    )

    objects = DataspacedManager.from_queryset(LicenseQuerySet)()

    class Meta:
        # This is a special case for the unique_together, ie several entries
        # It's important that's the first entry is 'key' in this case as it is
        # used to Match a License inside a dataspace
        unique_together = (
            ("dataspace", "key"),
            ("dataspace", "name"),
            ("dataspace", "short_name"),
            ("dataspace", "uuid"),
        )
        ordering = ["-popularity", "name"]
        permissions = (
            ("change_usage_policy_on_license", "Can change the usage_policy of license"),
        )

    def __str__(self):
        return f"{self.short_name} ({self.key})"

    def clean(self, from_api=False):
        if self.is_active is False and self.spdx_license_key:
            raise ValidationError("A deprecated license must not have an SPDX license key.")
        super().clean(from_api)

    def _get_unique_checks(self, exclude=None):
        """
        Ensure SPDX license key are unique within a Dataspace.
        This is a soft-constraint, ie not enforced at the database level.
        The check on `spdx_license_key` is not included if the value is blank.
        """
        unique_checks, date_checks = super()._get_unique_checks(exclude)

        if self.spdx_license_key:
            unique_together = ("dataspace", "spdx_license_key")
            unique_checks.append((self.__class__, unique_together))

        return unique_checks, date_checks

    @property
    def urn(self):
        return urn.build("license", key=self.key)

    def get_url(self, name, params=None):
        if not params:
            params = [self.dataspace.name, self.key]
        return super().get_url(name, params)

    def get_absolute_url(self):
        return self.get_url("details")

    @property
    def details_url(self):
        return self.get_absolute_url()

    def get_delete_url(self):
        return self.get_url("delete")

    def get_download_text_url(self):
        return self.get_url("download_text")

    def get_details_url_for_expression(self):
        return self.get_absolute_link(field_name="key", title=self.short_name)

    @property
    def permission_protected_fields(self):
        return {"usage_policy": "change_usage_policy_on_license"}

    @property
    def case_insensitive_unique_on(self):
        return ["name", "short_name", "key"]

    def where_used(self, user):
        """Callable for the reporting system."""
        return (
            f"Product {self.product_set.get_related_secured_queryset(user).count()}\n"
            f"Component {self.component_set.count()}\n"
            f"Subcomponent {self.subcomponent_set.count()}\n"
            f"Package {self.package_set.count()}\n"
            f"ProductComponent {self.productcomponent_set.count()}\n"
            f"ProductPackage {self.productpackage_set.count()}"
        )

    def get_license_tab_displayed_tags(self):
        """
        Return a list of the assigned tags for the given License limiting
        the tags where the value is set to True.
        Tags that are not in a LicenseTagGroup are not included.

        Use `LicenseAssignedTag.prefetch_for_license_tab()` in prefect_related of the QuerySet.
        """
        assigned_tag_qs = self.licenseassignedtag_set.filter(
            license_tag__licensetaggroupassignedtag__isnull=False
        ).order_by("license_tag__licensetaggroupassignedtag")

        return [
            (assigned_tag.license_tag.label, assigned_tag.value, assigned_tag.license_tag.text)
            for assigned_tag in assigned_tag_qs
            # equivalent to "filter(value=True)" without triggering another Query
            if assigned_tag.value
        ]

    def get_tagset(self, include_unknown=False, include_no_group=False):
        """
        Return a tagset for the given License.
        A "tagset" is a the collection of all the LicenseTags assigned to a
        License grouped by LicenseTagGroup and ordered by the Sequence.
        Groups are ordered by their sequence and tags are also ordered by
        their sequence inside a Group.
        LicenseAssignedTag with "Unknown" value can be included using the
        include_unknown parameter.
        Tag not assigned in a LicenseTagGroup can be included using the
        include_no_group parameter, an extra Group "(No Group)" will be added.
        "tagset" format is:
        OrderedDict(
            [('GroupName', [
                ('TagName', 'AssignedTagValue', 'TagText', Annotations),]
            )]
        )
        """
        filters = {"license": self}
        if not include_unknown:
            filters["value__isnull"] = False

        license_assigned_tags = (
            LicenseAssignedTag.objects.scope(self.dataspace)
            .filter(**filters)
            .select_related("license_tag")
            .prefetch_related("licenseannotation_set")
        )

        # Building a dictionary with the assigned tags of the current License
        license_tags_dict = {
            t.license_tag.label: (t.value, t.license_tag.text, t.licenseannotation_set.all())
            for t in license_assigned_tags
        }

        # Creating a 'tabset' dictionary ordered by Group and Tag sequence
        ordered_assigned_tags = (
            LicenseTagGroupAssignedTag.objects.scope(self.dataspace)
            .order_by("license_tag_group__seq", "seq")
            .select_related("license_tag_group", "license_tag")
        )

        # Using an OrderedDict to keep the QS ordering as we build the results
        license_tagset = OrderedDict()
        for assigned_tag in ordered_assigned_tags:
            label = assigned_tag.license_tag.label
            if label in license_tags_dict:
                # Using pop() to remove the entry from the dict, so we keep a
                # list of tags that are not assigned into a LicenseTagGroup
                value, text, annotations = license_tags_dict.pop(label)
                group_name = assigned_tag.license_tag_group.name
                license_tagset.setdefault(group_name, []).append([label, value, text, annotations])

        # If there is still entries in license_tags_dict, that mean those tags
        # are not assigned into a LicenseTagGroup, we are adding those in the
        # result if the include_no_group is True
        if include_no_group and license_tags_dict:
            leftover_tags = [[label] + list(values) for label, values in license_tags_dict.items()]
            license_tagset.update({"(No Group)": leftover_tags})

        return license_tagset

    def get_tag_labels(self):
        """Return the labels of all the tags associated with this license."""
        return self.tags.values_list("label", flat=True)

    def get_tag_value_from_label(self, label):
        try:
            assigned_tag = LicenseAssignedTag.objects.get(license=self, license_tag__label=label)
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            return ""  # Empty string rather than Error when no value available
        return str(assigned_tag.value)

    def set_assigned_tags_from_license_profile(self):
        """Update or create missing LicenseAssignedTag from the license_profile."""
        if not self.license_profile:
            return

        for profile_assigned_tag in self.license_profile.licenseprofileassignedtag_set.all():
            LicenseAssignedTag.objects.update_or_create(
                license=self,
                license_tag=profile_assigned_tag.license_tag,
                dataspace=self.dataspace,
                defaults={"value": profile_assigned_tag.value},
            )

    @staticmethod
    def get_extra_relational_fields():
        return ["annotations", "external_references"]

    @property
    def scancode_url(self):
        return SCANCODE_LICENSE_URL.format(self.key)

    @property
    def licensedb_url(self):
        return SCANCODE_LICENSEDB_URL.format(self.key)

    @property
    def spdx_url(self):
        """
        Return a URL to the https://spdx.org/licenses/ list using the short identifier.
        Return None for SPDX license key starting with "LicenseRef-" as those are not
        available in the SPDX list.
        """
        if self.spdx_license_key and not self.spdx_license_key.startswith("LicenseRef-"):
            return SPDX_LICENSE_URL.format(self.spdx_license_key)

    @property
    def spdx_link(self):
        """
        Return a link base on the `spdx_url` value.
        Return the `spdx_license_key` when the URL is not available.
        """
        spdx_url = self.spdx_url
        if spdx_url:
            return self.get_html_link(self.spdx_url, value=self.spdx_license_key, target="_blank")
        return self.spdx_license_key

    @property
    def spdx_id(self):
        """
        Return the `spdx_license_key` when available or a crafted LicenseRef using
        the license key.
        """
        return self.spdx_license_key or f"LicenseRef-dejacode-{self.key}"

    def as_spdx(self):
        """Return this License as an SPDX ExtractedLicensingInfo entry."""
        return spdx.ExtractedLicensingInfo(
            license_id=self.spdx_id,
            extracted_text=self.full_text,
            name=self.name,
            see_alsos=self.get_all_urls(),
        )

    def get_all_urls(self):
        """Return all URLs set in URL-based fields of this License instance."""
        url_fields = [
            "licensedb_url",
            "scancode_url",
            "homepage_url",
            "osi_url",
            "faq_url",
            "text_urls",
            "other_urls",
        ]

        urls = []
        for url_field in url_fields:
            url_value = getattr(self, url_field)
            if url_value:
                urls.extend([url for url in url_value.split() if url])

        return sorted(set(urls))

    def has_tag_field_enabled(self, tag_field):
        # Make sure to include the following prefetch on the QuerySet:
        # prefetch_related('licenseassignedtag_set__license_tag')
        for assigned_tag in self.licenseassignedtag_set.all():
            if getattr(assigned_tag.license_tag, tag_field) and assigned_tag.value:
                return True
        return False

    @property
    def attribution_required(self):
        return self.has_tag_field_enabled("attribution_required")

    @property
    def redistribution_required(self):
        return self.has_tag_field_enabled("redistribution_required")

    @property
    def change_tracking_required(self):
        return self.has_tag_field_enabled("change_tracking_required")

    @property
    def language_code(self):
        return self.language


class LicenseAssignedTag(DataspacedModel):
    license = models.ForeignKey(
        to="license_library.License",
        on_delete=models.CASCADE,
    )

    license_tag = models.ForeignKey(
        to="license_library.LicenseTag",
        on_delete=models.PROTECT,
    )

    value = models.BooleanField(
        null=True,
        help_text="Yes, No, Unknown",
    )

    class Meta:
        ordering = ["license"]
        unique_together = (("license", "license_tag"), ("dataspace", "uuid"))

    def __str__(self):
        return f"{self.license_tag.label}: {self.value}"

    def unique_filters_for(self, target):
        """
        Return the unique filters data dict.
        Custom identifier for LicenseAssignedTag.
        Required as there is no unique_together other than the uuid.
        """
        return {
            "license__uuid": self.license.uuid,
            "license_tag__uuid": self.license_tag.uuid,
            "dataspace": target,
        }

    @staticmethod
    def prefetch_for_license_tab():
        assigned_tags_qs = LicenseAssignedTag.objects.order_by(
            "license_tag__licensetaggroupassignedtag"
        ).select_related("license_tag")
        return models.Prefetch("licenses__licenseassignedtag_set", queryset=assigned_tags_qs)


class LicenseAnnotation(DataspacedModel):
    license = models.ForeignKey(
        to="license_library.License",
        related_name="annotations",
        on_delete=models.CASCADE,
    )

    assigned_tag = models.ForeignKey(
        to="license_library.LicenseAssignedTag",
        on_delete=models.SET_NULL,
        null=True,
    )

    text = models.TextField(
        blank=True,
    )

    quote = models.TextField(
        blank=True,
    )

    range_start_offset = models.IntegerField()
    range_end_offset = models.IntegerField()

    class Meta:
        unique_together = ("dataspace", "uuid")

    def __str__(self):
        value = f'License: "{self.license.name}"'
        if self.text:
            value += f', Text: "{truncatechars(self.text, 200)}"'
        if self.assigned_tag:
            value += f', Tag: "{self.assigned_tag.license_tag}"'
        return value

    def save(self, *args, **kwargs):
        # This could be move to the  Annotation API 'Addition' logic.
        self.dataspace = self.license.dataspace
        super().save(*args, **kwargs)

    def unique_filters_for(self, target):
        """
        Return the unique filters data dict.
        Custom identifier for Annotation.
        Required as there is no unique_together other than the uuid.
        """
        target_filter = {"dataspace": target}

        try:
            license = License.objects.get(uuid=self.license.uuid, **target_filter)
        except License.DoesNotExist:
            # Filter using the key if uuid doesn't match
            license_filter = {"license__key": self.license.key}
        else:
            license_filter = {"license": license}

        unique_filters = {
            "quote": self.quote,
            "text": self.text,
            "range_start_offset": self.range_start_offset,
            "range_end_offset": self.range_end_offset,
        }

        unique_filters.update(license_filter)
        unique_filters.update(target_filter)
        return unique_filters


class LicenseChoiceManager(DataspacedManager):
    def get_substitutions(self, dataspace):
        """Return a list of substitution suitable for license_expression `subs`."""
        from component_catalog.license_expression_dje import build_licensing

        licensing = build_licensing()

        return [
            {licensing.parse(choice.from_expression): licensing.parse(choice.to_expression)}
            for choice in self.scope(dataspace).all()
        ]

    def get_choices_expression(self, expression, dataspace):
        """Return an expression with choices applied."""
        from component_catalog.license_expression_dje import build_licensing

        licensing = build_licensing()

        expression = licensing.parse(expression)

        if expression is None:
            return ""

        for substitution in self.get_substitutions(dataspace):
            expression = expression.subs(substitution)

        if expression is not None:
            return expression.render()


class LicenseChoice(DataspacedModel):
    """
    Each choice is applied once rather than recursively,
    to prevent risk of infinite loop.

    - Or later type licenses:
        gps-2.0-plus -> gps-2.0 OR gps-2.0-plus OR gps-3.0 OR gps-3.0-plus

    - Dual licenses:
        (seq:0) dual-bsd-gpl -> bsd-new OR gps-2.0
        (seq:1) bsd-new OR gps-2.0 -> bsd-new

    - Unknown gpl version in license text:
        (seq:0) brian-gladman-dual -> bsd-new OR gps-1.0-plus
        (seq:1) bsd-new OR gps-1.0-plus -> bsd-new
    """

    from_expression = models.CharField(
        max_length=1024,
        help_text=_("A license key or license expression snippet."),
    )

    to_expression = models.CharField(
        max_length=1024,
        help_text=_("A license key or license expression snippet."),
    )

    seq = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        help_text=_(
            "Use the sequence value to indicate your license choice preference policies for a "
            "particular license expression, using zero (0) as the first and preferred choice, "
            "followed by other sequences that define acceptable choices."
        ),
    )

    notes = models.TextField(
        blank=True,
        help_text=_("Notes."),
    )

    objects = LicenseChoiceManager()

    class Meta:
        unique_together = ("dataspace", "uuid")
        ordering = ["seq"]

    def __str__(self):
        return f"{self.from_expression} -> {self.to_expression}"
