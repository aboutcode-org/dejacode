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

    Iterates all active rules in the ruleset. Returns a dict with the recommended
    action and the list of rule types that fired, or None if no rule fires.
    """
    matched_rules = []

    for rule_type, config in ruleset.rules_config.items():
        if not config.get("is_active"):
            continue

        handler = RULE_REGISTRY.get(rule_type)
        if not handler:
            continue

        parameters = {key: value for key, value in config.items() if key != "is_active"}
        if handler.count_matches(product=product, parameters=parameters) > 0:
            matched_rules.append(rule_type)

    if matched_rules:
        return {"action": ruleset.action, "matched_rules": matched_rules}
