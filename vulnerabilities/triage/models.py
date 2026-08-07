#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import apps
from django.db import models
from django.db.models import OuterRef
from django.db.models import Subquery
from django.utils.translation import gettext_lazy as _

from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import ProductSecuredQuerySet


class TriageAction(models.TextChoices):
    UPGRADE = "upgrade", _("Upgrade Package")
    APPLY_PATCH = "apply_patch", _("Apply Patch")
    FORENSIC_ANALYSIS = "forensic_analysis", _("Forensic Analysis")
    REACHABILITY_ANALYSIS = "reachability_analysis", _("Reachability Analysis")
    CHANGE_CONFIG = "change_config", _("Change Configuration")
    REPLACE_PACKAGE = "replace_package", _("Replace Package")
    NOTIFY = "notify", _("Notify")
    CREATE_REQUEST = "create_request", _("Create DejaCode Request")


class TriageRuleset(DataspacedModel):
    name = models.CharField(
        max_length=100,
        help_text=_("Short name identifying this triage ruleset."),
    )
    description = models.TextField(
        blank=True,
        help_text=_("Optional description of the purpose or scope of this ruleset."),
    )
    action = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Action recommended when this ruleset's conditions are met."),
    )
    precedence = models.PositiveIntegerField(
        default=100,
        help_text=_(
            "When multiple rulesets are assigned to a product and produce different"
            " actions, the one with the highest precedence takes effect."
        ),
    )
    enabled = models.BooleanField(
        default=True,
        help_text=_("Activate or deactivate this ruleset without deleting it."),
    )
    rules_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Active rules for this ruleset, keyed by rule type."),
    )

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ("-precedence", "name")

    def __str__(self):
        return self.name


class TriageRecordQuerySet(ProductSecuredQuerySet):
    def product_secured(self, user=None, perms="view_product"):
        """
        Filter by product object permission through the product_package relation.

        The base implementation filters on a direct `product` FK, which does not exist
        on this model. The product is reached via product_package__product instead.
        """
        if not user:
            return self.none()
        Product = apps.get_model("product_portfolio", "Product")
        product_qs = Product.objects.get_queryset(user, perms)
        return self.filter(product_package__product__in=product_qs)

    def primary_actions(self):
        """
        Return one record per product_package: the highest-precedence active ruleset.

        Uses a correlated subquery to find the winning ruleset per package rather than
        DISTINCT ON, which breaks under Django's COUNT wrapping and select_related JOINs.
        """
        winning_ruleset_id = (
            self.model.objects.filter(
                product_package=OuterRef("product_package"),
                ruleset__enabled=True,
            )
            .order_by("-ruleset__precedence")
            .values("ruleset_id")[:1]
        )
        return self.filter(
            ruleset__enabled=True,
            ruleset_id=Subquery(winning_ruleset_id),
        )


class TriageRecord(DataspacedModel):
    """Stores the triage recommendation for a specific package usage within a product."""

    product_package = models.ForeignKey(
        to="product_portfolio.ProductPackage",
        on_delete=models.CASCADE,
        related_name="triage_records",
        help_text=_("The specific package usage that triggered this recommendation."),
    )
    ruleset = models.ForeignKey(
        to="vulnerabilities_triage.TriageRuleset",
        on_delete=models.CASCADE,
        related_name="triage_records",
        help_text=_("The ruleset that produced this action."),
    )
    action = models.CharField(
        max_length=50,
        help_text=_("Recommended action captured at the time of evaluation."),
    )
    matched_rules = models.JSONField(
        default=list,
        help_text=_("Rules that fired for this package during evaluation."),
    )
    detected_date = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Date and time when this recommendation was first generated."),
    )
    last_checked = models.DateTimeField(
        auto_now=True,
        help_text=_("Date and time of the last evaluation."),
    )

    objects = DataspacedManager.from_queryset(TriageRecordQuerySet)()

    class Meta:
        unique_together = [("product_package", "ruleset"), ("dataspace", "uuid")]
        ordering = ["-detected_date"]

    def __str__(self):
        return f"{self.product_package} / {self.ruleset}: {self.action}"
