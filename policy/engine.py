#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils import timezone

from policy.rules import RULE_REGISTRY
from product_portfolio.models import ProductPolicyViolation


def get_effective_config(rule_type, dataspace):
    """
    Resolve threshold, parameters, and is_active for a rule type in a given dataspace.

    Reads the dataspace-level override from DataspaceConfiguration.policy_rules_config,
    falling back to the code defaults defined on the rule handler.
    """
    handler = RULE_REGISTRY[rule_type]
    try:
        rule_config = dataspace.configuration.policy_rules_config.get(rule_type, {})
    except AttributeError:
        rule_config = {}

    return {
        "is_active": rule_config.get("is_active", True),
        "threshold": rule_config.get("threshold", handler.default_threshold),
        "parameters": rule_config.get("parameters", {}),
    }


def evaluate_rule(rule_type, product, threshold, parameters):
    """Evaluate a single rule against a product and record the violation if triggered."""
    handler = RULE_REGISTRY[rule_type]
    violation_count = handler.count_violations(product, threshold, parameters)

    lookup = {"rule_type": rule_type, "product": product, "resolved": False}

    if violation_count > 0:
        violation, created = ProductPolicyViolation.objects.get_or_create(
            **lookup,
            defaults={"dataspace": product.dataspace, "violation_count": violation_count},
        )
        if not created:
            violation.violation_count = violation_count
            violation.save()
        return violation

    else:
        ProductPolicyViolation.objects.filter(**lookup).update(
            resolved=True,
            resolved_date=timezone.now(),
        )
        return


def evaluate_rules(product):
    """
    Evaluate all rules in RULE_REGISTRY for the given product.

    Returns the list of active ProductPolicyViolation instances.
    """
    violations = []
    for rule_type in RULE_REGISTRY:
        config = get_effective_config(rule_type, product.dataspace)
        if not config["is_active"]:
            # Explicitly resolve open violations so disabling a rule clears its history
            # rather than leaving stale unresolved records.
            ProductPolicyViolation.objects.filter(
                rule_type=rule_type, product=product, resolved=False,
            ).update(resolved=True, resolved_date=timezone.now())
            continue

        violation = evaluate_rule(rule_type, product, config["threshold"], config["parameters"])
        if violation:
            violations.append(violation)

    return violations
