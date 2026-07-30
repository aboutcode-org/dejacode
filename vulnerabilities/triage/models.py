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
    name = models.CharField(
        max_length=100,
        help_text=_("Short name identifying this triage ruleset."),
    )
    description = models.TextField(
        blank=True,
        help_text=_("Optional description of the purpose or scope of this ruleset."),
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
        help_text=_(
            "Active rules for this ruleset, keyed by rule type."
            " Each entry may include is_active, threshold, and parameters."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ("-precedence", "name")

    def __str__(self):
        return self.name
