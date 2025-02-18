#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from contextlib import suppress

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned
from django.db import models
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import colored_icon_mixin_factory

ColoredIconMixin = colored_icon_mixin_factory(
    verbose_name="usage policy",
    icon_blank=False,
)


class UsagePolicy(ColoredIconMixin, DataspacedModel):
    CONTENT_TYPES = (
        models.Q(app_label="component_catalog", model="component")
        | models.Q(app_label="component_catalog", model="subcomponent")
        | models.Q(app_label="component_catalog", model="package")
        | models.Q(app_label="license_library", model="license")
    )

    label = models.CharField(
        max_length=50,
        help_text=_(
            "Label is the text that you want to present to application "
            "users to describe a specific Usage Policy as it applies "
            "to an application object."
        ),
    )

    guidelines = models.TextField(
        blank=True,
        help_text=_(
            "Guidelines explain the organization definition of a usage "
            "policy (approval level) and can also provide detailed "
            "requirements for compliance."
        ),
    )

    content_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.PROTECT,
        verbose_name=_("object type"),
        limit_choices_to=CONTENT_TYPES,
        help_text=_(
            "Object type identifies the application object (License, "
            "Component, Subcomponent relationship, Package) to which the "
            "Usage Policy will apply."
        ),
    )

    class Compliance(models.TextChoices):
        WARNING = "warning", _("Warning")
        ERROR = "error", _("Error")

    compliance_alert = models.CharField(
        max_length=20,
        blank=True,
        choices=Compliance.choices,
        help_text=_(
            "Indicates how the usage of a DejaCode object (license, component, "
            "package, etc.) complies with organizational policy. "
            'Value choices include "Pass" (or empty, the default value), '
            '"Warning" (should be reviewed), and "Error" '
            "(fails compliance policy guidelines)."
        ),
    )

    associated_product_relation_status = models.ForeignKey(
        to="product_portfolio.ProductRelationStatus",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text=_(
            "An associated product relation status enables you to specify the product "
            "relation status to use automatically when a component or package with an "
            "assigned usage policy is added to a product, overriding the general "
            "default defined in the product relation status table."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "content_type", "label"), ("dataspace", "uuid"))
        ordering = ["content_type", "label"]
        verbose_name_plural = _("usage policies")

    def __str__(self):
        return self.label

    def str_with_content_type(self):
        return f"{self.label} ({self.content_type.model})"

    @classmethod
    def get_identifier_fields(cls, *args, **kwargs):
        """Hack required by the Component import."""
        return ["label"]

    def get_object_set(self):
        """Return the QuerySet of objects using this policy."""
        return self.content_type.model_class().objects.filter(usage_policy=self)

    def get_associated_policy_to_model(self, model):
        with suppress(models.ObjectDoesNotExist, MultipleObjectsReturned):
            return self.to_policies.to_model(model).get().to_policy

    def as_dict(self):
        return {
            "label": self.label,
            "color_code": self.get_color_code(),
            "icon": self.icon,
            "compliance_alert": self.compliance_alert,
        }


class UsagePolicyMixin(models.Model):
    """Abstract Model Mixin to include the field and API for usage policy."""

    usage_policy = models.ForeignKey(
        to="policy.UsagePolicy",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text=_(
            "An administrator can communicate company policy for an "
            "entry by setting the Usage Policy indicator."
        ),
    )

    class Meta:
        abstract = True

    def get_usage_policy_as_icon(self):
        if self.usage_policy:
            return self.usage_policy.get_icon_as_html()

    def get_usage_policy_display_with_icon(self):
        if self.usage_policy:
            return format_html(
                '{}<span class="ms-1">{}</span>',
                self.get_usage_policy_as_icon(),
                self.usage_policy.label,
            )

    def get_usage_policy_color(self):
        return self.usage_policy.get_color_code()

    def get_usage_policy_icon_tooltip(self):
        return format_html(
            '<span class="cursor-help policy-icon" data-bs-toggle="tooltip" title="{}">{}</span>',
            self.usage_policy,
            self.usage_policy.get_icon_as_html(),
        )

    def get_policy_from_primary_license(self):
        """Return the UsagePolicy associated to this Component/Package primary_license."""
        License = apps.get_model("license_library", "license")

        try:
            license_instance = License.objects.get(
                key=self.primary_license,
                dataspace=self.dataspace,
            )
        except models.ObjectDoesNotExist:
            return

        if license_instance.usage_policy:
            return license_instance.usage_policy.get_associated_policy_to_model(self)

    policy_from_primary_license = cached_property(get_policy_from_primary_license)


class SetPolicyFromLicenseMixin:
    def save(self, *args, **kwargs):
        """
        Set a usage policy to Components/Packages based on its license expression,
        when the flag is enabled on the dataspace and no usage_policy is provided.
        Located in save() so this behavior is shared for import, copy, API, and forms.
        """
        set_usage_policy = all(
            [
                not self.usage_policy,
                self.license_expression,
                self.dataspace.set_usage_policy_on_new_component_from_licenses,
            ]
        )

        if set_usage_policy:
            self.usage_policy = self.policy_from_primary_license
            if "update_fields" in kwargs:
                kwargs["update_fields"].append("usage_policy")

        super().save(*args, **kwargs)


class AssociatedPolicyQuerySet(DataspacedQuerySet):
    def to_content_type(self, content_type):
        """Limit the AssociatedPolicy QuerySet for the given `content_type`."""
        return self.filter(to_policy__content_type=content_type)

    def to_model(self, model):
        """Limit the AssociatedPolicy QuerySet for the given `model` type."""
        return self.to_content_type(ContentType.objects.get_for_model(model))


class AssociatedPolicy(DataspacedModel):
    from_policy = models.ForeignKey(
        to="policy.UsagePolicy",
        on_delete=models.PROTECT,
        related_name="to_policies",
    )

    to_policy = models.ForeignKey(
        to="policy.UsagePolicy",
        on_delete=models.PROTECT,
        related_name="from_policies",
    )

    objects = DataspacedManager.from_queryset(AssociatedPolicyQuerySet)()

    def __str__(self):
        return f'"{self.from_policy}" associated with "{self.to_policy}"'

    class Meta:
        unique_together = (("from_policy", "to_policy"), ("dataspace", "uuid"))
        ordering = ["from_policy", "to_policy"]

    def save(self, *args, **kwargs):
        if self.from_policy.content_type == self.to_policy.content_type:
            raise AssertionError
        super().save(*args, **kwargs)
