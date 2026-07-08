#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils import timezone

from policy.models import PolicyRule
from policy.rules import RULE_REGISTRY
from product_portfolio.models import ProductPolicyViolation


def evaluate_rule(policy_rule, product):
    """
    Evaluate a single PolicyRule against a product, create or update the
    ProductPolicyViolation record.
    Returns the ProductPolicyViolation instance, or None if no violation exists.
    """
    rule_handler = RULE_REGISTRY.get(policy_rule.rule_type)
    if not rule_handler:
        return

    violation_count = rule_handler.count_violations(policy_rule, product)

    lookup = {"policy_rule": policy_rule, "product": product, "resolved": False}

    if violation_count > 0:
        violation, created = ProductPolicyViolation.objects.get_or_create(
            **lookup,
            defaults={"dataspace": policy_rule.dataspace, "violation_count": violation_count},
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
    Evaluate all active PolicyRules for the given product.
    Returns the list of active ProductPolicyViolation instances.
    """
    violations = []
    for policy_rule in PolicyRule.objects.scope(product.dataspace).active():
        violation = evaluate_rule(policy_rule, product)
        if violation:
            violations.append(violation)

    return violations
