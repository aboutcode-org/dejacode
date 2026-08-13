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
from vulnerabilities.models import VulnerabilityAnalysisContentMixin


class TriageAction(models.TextChoices):
    UPGRADE = "upgrade", _("Upgrade Package")
    APPLY_PATCH = "apply_patch", _("Apply Patch")
    FORENSIC_ANALYSIS = "forensic_analysis", _("Forensic Analysis")
    REACHABILITY_ANALYSIS = "reachability_analysis", _("Reachability Analysis")
    CHANGE_CONFIG = "change_config", _("Change Configuration")
    REPLACE_PACKAGE = "replace_package", _("Replace Package")
    NOTIFY = "notify", _("Notify")
    CREATE_REQUEST = "create_request", _("Create DejaCode Request")


class AnalysisPreset(DataspacedModel, VulnerabilityAnalysisContentMixin):
    """Default VulnerabilityAnalysis values applied automatically when a TriageRuleset fires."""

    name = models.CharField(
        max_length=100,
        help_text=_("Short name identifying this analysis preset."),
    )
    description = models.TextField(
        blank=True,
        help_text=_("Optional description of when and why this preset is applied."),
    )
    is_reachable = models.BooleanField(
        null=True,
        blank=True,
        help_text=_(
            "Reachability value to set on the analysis. Leave blank to leave the field unchanged."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ("name",)

    def __str__(self):
        return self.name

    def apply_to_analysis(self, analysis):
        """Copy non-blank preset fields onto the analysis instance (does not save)."""
        if self.state:
            analysis.state = self.state
        if self.justification:
            analysis.justification = self.justification
        if self.responses:
            analysis.responses = self.responses
        if self.detail:
            analysis.detail = self.detail
        if self.is_reachable is not None:
            analysis.is_reachable = self.is_reachable


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
    analysis_preset = models.ForeignKey(
        to="AnalysisPreset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triage_rulesets",
        help_text=_(
            "Optional preset automatically applied to matching vulnerability analyses."
            " Only applied when no human-owned analysis exists."
        ),
    )
    request_template = models.ForeignKey(
        to="workflow.RequestTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triage_rulesets",
        limit_choices_to={
            "content_type__app_label": "product_portfolio",
            "content_type__model": "product",
        },
        help_text=_(
            "Optional product-type request template. When set, the triage engine"
            " automatically opens a request for each newly detected vulnerability match."
        ),
    )

    class Meta:
        unique_together = (
            ("dataspace", "name"),
            ("dataspace", "precedence"),
            ("dataspace", "uuid"),
        )
        ordering = ("-precedence", "name")

    def __str__(self):
        return self.name


class TriageRecordQuerySet(ProductSecuredQuerySet):
    def product_secured(self, user=None, perms="view_product"):
        """Filter by product object permission through the direct product FK."""
        if not user:
            return self.none()
        Product = apps.get_model("product_portfolio", "Product")
        product_qs = Product.objects.get_queryset(user, perms)
        return self.filter(product__in=product_qs)

    def primary_actions(self):
        """
        Return one record per (vulnerability, product): the highest-precedence active ruleset
        that is explicitly assigned to the product via ProductTriageRuleset.

        Uses a correlated subquery rather than DISTINCT ON, which breaks under Django's
        COUNT wrapping and select_related JOINs.
        """
        winning_ruleset_id = (
            self.model.objects.filter(
                vulnerability=OuterRef("vulnerability"),
                product=OuterRef("product"),
                ruleset__enabled=True,
                ruleset__product_triage_rulesets__product=OuterRef("product"),
            )
            .order_by("-ruleset__precedence")
            .values("ruleset_id")[:1]
        )
        return self.filter(
            ruleset__enabled=True,
            ruleset_id=Subquery(winning_ruleset_id),
        )


class ProductTriageRuleset(DataspacedModel):
    """Activates a TriageRuleset for evaluation against a specific Product."""

    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
        related_name="product_triage_rulesets",
        help_text=_("The product this ruleset is activated for."),
    )
    ruleset = models.ForeignKey(
        to="TriageRuleset",
        on_delete=models.CASCADE,
        related_name="product_triage_rulesets",
        help_text=_("The ruleset to evaluate against this product."),
    )

    class Meta:
        unique_together = [("product", "ruleset"), ("dataspace", "uuid")]
        ordering = ["-ruleset__precedence"]

    def __str__(self):
        return f"{self.product} / {self.ruleset}"


class TriageRecord(DataspacedModel):
    """Stores the triage recommendation for a specific vulnerability within a product."""

    vulnerability = models.ForeignKey(
        to="vulnerabilities.Vulnerability",
        on_delete=models.CASCADE,
        related_name="triage_records",
        help_text=_("The vulnerability that triggered this recommendation."),
    )
    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
        related_name="triage_records",
        help_text=_("The product this recommendation applies to."),
    )
    ruleset = models.ForeignKey(
        to="vulnerabilities_triage.TriageRuleset",
        on_delete=models.CASCADE,
        related_name="triage_records",
        help_text=_("The ruleset that produced this action."),
    )
    action = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Recommended action captured at the time of evaluation."),
    )
    matched_rules = models.JSONField(
        default=list,
        help_text=_("Rules that fired for this vulnerability during evaluation."),
    )
    request = models.ForeignKey(
        to="workflow.Request",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triage_records",
        help_text=_(
            "Request automatically opened by the triage engine for this vulnerability match."
        ),
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
        unique_together = [("vulnerability", "product", "ruleset"), ("dataspace", "uuid")]
        ordering = ["-detected_date"]

    def __str__(self):
        return f"{self.vulnerability} / {self.product} / {self.ruleset}: {self.action}"
