#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.db import models
from django.utils.translation import gettext_lazy as _

from dje.models import DataspacedModel


class TriageRuleset(DataspacedModel):
    class Action(models.TextChoices):
        UPGRADE = "upgrade", _("Upgrade Package")
        APPLY_PATCH = "apply_patch", _("Apply Patch")
        FORENSIC_ANALYSIS = "forensic_analysis", _("Forensic Analysis")
        REACHABILITY_ANALYSIS = "reachability_analysis", _("Reachability Analysis")
        CHANGE_CONFIG = "change_config", _("Change Configuration")
        REPLACE_PACKAGE = "replace_package", _("Replace Package")
        NOTIFY = "notify", _("Notify")
        CREATE_REQUEST = "create_request", _("Create DejaCode Request")

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
        choices=Action.choices,
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


class TriageDecision(DataspacedModel):
    """Stores the result of evaluating a TriageRuleset against a product."""

    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
        related_name="triage_decisions",
        help_text=_("The product against which this ruleset was evaluated."),
    )
    ruleset = models.ForeignKey(
        to="vulnerabilities_triage.TriageRuleset",
        on_delete=models.CASCADE,
        related_name="triage_decisions",
        help_text=_("The ruleset that produced this action."),
    )
    action = models.CharField(
        max_length=50,
        choices=TriageRuleset.Action.choices,
        help_text=_("Recommended action at the time of evaluation."),
    )
    matched_rules = models.JSONField(
        default=list,
        help_text=_("List of rule types that detected violations during this evaluation."),
    )
    detected_date = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Date and time when this action was first recommended."),
    )
    last_checked = models.DateTimeField(
        auto_now=True,
        help_text=_("Date and time of the last evaluation."),
    )

    class Meta:
        unique_together = (("dataspace", "uuid"), ("product", "ruleset"))
        ordering = ["-detected_date"]

    def __str__(self):
        return f"{self.ruleset} / {self.product}: {self.action}"
