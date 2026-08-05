#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from vulnerabilities.triage.rules import RULE_REGISTRY


def evaluate_ruleset(ruleset, product):
    """
    Evaluate a TriageRuleset against a product.

    Iterates all active rules in the ruleset. If any rule detects at least one
    violation, returns the ruleset's action. Returns None if no rule fires.
    """
    for rule_type, config in ruleset.rules_config.items():
        if not config.get("is_active"):
            continue

        handler = RULE_REGISTRY.get(rule_type)
        if not handler:
            continue

        if handler.count_violations(product=product) > 0:
            return ruleset.action
