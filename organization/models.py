#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from urllib.parse import quote_plus

from django.db import models
from django.utils.translation import gettext_lazy as _

from dje import urn
from dje.models import DataspacedModel
from dje.models import ExternalReferenceMixin
from dje.models import HistoryFieldsMixin
from dje.models import ParentChildModelMixin
from dje.models import ParentChildRelationshipModel


class Owner(
    ExternalReferenceMixin,
    HistoryFieldsMixin,
    ParentChildModelMixin,
    DataspacedModel,
):
    name = models.CharField(
        db_index=True,
        max_length=70,
        help_text=_(
            "The unique user-maintained name of the author, custodian, or provider of "
            "one or more software objects (licenses, components, products)."
        ),
    )

    homepage_url = models.URLField(
        _("Homepage URL"),
        max_length=1024,
        blank=True,
        help_text=_("The homepage URL of the owner."),
    )

    contact_info = models.CharField(
        _("contact information"),
        max_length=500,
        blank=True,
        help_text=_(
            "Information, frequently a dedicated email address, about "
            "contacting an owner for license clarifications and permissions."
        ),
    )

    notes = models.TextField(blank=True, help_text=_("Extended notes about an owner."))

    alias = models.CharField(
        db_index=True,
        max_length=500,
        blank=True,
        help_text=_("Alternative spellings of the name of the owner as a comma-separated list."),
    )

    OWNER_TYPE_CHOICES = (
        (
            "Organization",
            _("Organization: an ongoing entity that provides software or promotes standards."),
        ),
        ("Person", _("Person: an individual that provides software or promotes standards.")),
        ("Project", _("Project: a dynamic collection of contributors to a software project.")),
    )

    type = models.CharField(
        max_length=20,
        default="Organization",
        choices=OWNER_TYPE_CHOICES,
        db_index=True,
        help_text=_(
            "An owner type differentiates individuals, ongoing businesses, and "
            "dynamic organizations (such as software projects). "
            "An owner of any type can be associated with a license, component, or "
            "product. An owner can also be the parent of any other owner."
        ),
    )

    # Use choices database values instead of the `get_FIELD_display`, in reporting.
    type.report_with_db_value = True

    # This reference all the Owners associated with self through a
    # Subowner relation where self is the parents.
    # Only the children are copied on ParentChild relation type.
    children = models.ManyToManyField(
        to="self",
        through="Subowner",
        symmetrical=False,
    )

    class Meta:
        unique_together = (
            ("dataspace", "name"),
            ("dataspace", "uuid"),
        )
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def urn(self):
        return urn.build("owner", name=self.name)

    def get_url(self, name, params=None):
        if not params:
            params = [self.dataspace.name, quote_plus(self.name)]
        return super().get_url(name, params)

    def get_absolute_url(self):
        return self.get_url("details")

    @property
    def details_url(self):
        return self.get_absolute_url()

    def get_change_url(self):
        return self.get_url("change")

    def get_delete_url(self):
        return self.get_url("delete")

    @staticmethod
    def get_extra_relational_fields():
        return ["external_references"]

    @property
    def case_insensitive_unique_on(self):
        return ["name"]

    def get_alias_list(self):
        return self.alias.replace(", ", ",").split(",")

    def as_spdx(self):
        spdx_type = "Person" if self.type == "Person" else "Organization"
        return f"{spdx_type}: {self.name}"


class Subowner(ParentChildRelationshipModel):
    parent = models.ForeignKey(
        to="organization.Owner",
        on_delete=models.CASCADE,
        related_name="related_children",
    )

    child = models.ForeignKey(
        to="organization.Owner",
        on_delete=models.CASCADE,
        related_name="related_parents",
    )

    notes = models.TextField(
        blank=True,
        help_text=_(
            "Comments about the relationship of the Child Owner to the Parent Owner. "
            "For example, an owner was acquired by another owner, or an owner works "
            "for another owner."
        ),
    )

    start_date = models.DateField(
        blank=True,
        null=True,
        help_text=_(
            "Format YYYY-MM-DD. This date is intended to show the beginning of a "
            "parent/child owner relationship."
        ),
    )

    end_date = models.DateField(
        blank=True,
        null=True,
        help_text=_(
            "Format YYYY-MM-DD. This date is intended to show the ending of a "
            "parent/child owner relationship."
        ),
    )

    class Meta:
        # We have a special case for this Model, one Owner can be assigned
        # more than once as child or parent of the same Owner.
        unique_together = (("parent", "child", "start_date", "end_date"), ("dataspace", "uuid"))
