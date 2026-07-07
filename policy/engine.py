#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils import timezone

from notification.models import fire_webhooks
from policy.models import PolicyRule
from policy.rules import RULE_REGISTRY
from product_portfolio.models import ProductPolicyViolation


def evaluate_rule(policy_rule, product):
    """
    Evaluate a single PolicyRule against a product, create or update the
    ProductPolicyViolation record, and fire the notification event on new violations
    or resolutions.
    Returns the ProductPolicyViolation instance, or None if no violation exists.
    """
    rule_handler = RULE_REGISTRY.get(policy_rule.rule_type)
    if not rule_handler:
        return None

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
        if created and policy_rule.event_name:
            fire_violation_event(policy_rule, product, violation_count)
        return violation
    else:
        resolved_count = ProductPolicyViolation.objects.filter(**lookup).update(
            resolved=True,
            resolved_date=timezone.now(),
        )
        if resolved_count and policy_rule.event_name:
            fire_resolution_event(policy_rule, product)
        return None


def evaluate_rules(dataspace, product):
    """
    Evaluate all active PolicyRules for the given product.
    Returns the list of active ProductPolicyViolation instances.
    """
    violations = []
    for policy_rule in PolicyRule.objects.scope(dataspace).active():
        violation = evaluate_rule(policy_rule, product)
        if violation:
            violations.append(violation)

    return violations


def fire_violation_event(policy_rule, product, violation_count):
    fire_webhooks(
        policy_rule.event_name,
        instance=None,
        dataspace=policy_rule.dataspace,
        payload_override={
            "rule": policy_rule.name,
            "rule_type": policy_rule.rule_type,
            "violation_count": violation_count,
            "product": str(product),
        },
    )


def fire_resolution_event(policy_rule, product):
    fire_webhooks(
        policy_rule.event_name,
        instance=None,
        dataspace=policy_rule.dataspace,
        payload_override={
            "rule": policy_rule.name,
            "status": "resolved",
            "product": str(product),
        },
    )
