#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils import timezone

from notification.models import fire_webhooks
from policy.rules import RULE_REGISTRY
from product_portfolio.models import ProductPolicyViolation


def fire_policy_webhooks(product, new_violations, resolved_count):
    """Fire policy webhooks for newly detected or resolved violations."""
    if new_violations:
        lines = [
            f"- {violation.rule_label}: {violation.violation_count} violation(s)"
            for violation in new_violations
        ]
        payload = {
            "text": (f"[DejaCode] Policy violations detected for {product}\n" + "\n".join(lines))
        }
        fire_webhooks("policy.violation_detected", instance=product, payload_override=payload)

    if resolved_count:
        payload = {
            "text": (f"[DejaCode] {resolved_count} policy violation(s) resolved for {product}")
        }
        fire_webhooks("policy.violation_resolved", instance=product, payload_override=payload)


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
        "is_active": rule_config.get("is_active", False),
        "threshold": rule_config.get("threshold", handler.default_threshold),
        "parameters": rule_config.get("parameters", {}),
    }


def evaluate_rule(rule_type, product, threshold, parameters):
    """
    Evaluate a single rule against a product and record the violation if triggered.

    Returns a 3-tuple: (violation_or_none, created, resolved_count).
    """
    handler = RULE_REGISTRY[rule_type]
    violation_count = handler.count_violations(product, threshold, parameters)

    lookup = {"rule_type": rule_type, "product": product}

    if violation_count > 0:
        # update_or_create on the unique (rule_type, product) pair so that a previously
        # resolved violation can be re-activated without hitting the unique constraint.
        violation, created = ProductPolicyViolation.objects.update_or_create(
            **lookup,
            defaults={
                "dataspace": product.dataspace,
                "violation_count": violation_count,
                "resolved": False,
                "resolved_date": None,
            },
        )
        return violation, created, 0

    now = timezone.now()
    resolved_count = ProductPolicyViolation.objects.filter(**lookup, resolved=False).update(
        resolved=True,
        resolved_date=now,
        last_checked=now,
    )
    return None, False, resolved_count


def evaluate_rules(product):
    """
    Evaluate all rules in RULE_REGISTRY for the given product.

    Returns a 2-tuple: (new_violations, resolved_count).
    new_violations is a list of newly created ProductPolicyViolation instances.
    resolved_count is the total number of violations resolved during this run.
    """
    new_violations = []
    resolved_count = 0

    for rule_type in RULE_REGISTRY:
        config = get_effective_config(rule_type, product.dataspace)
        if not config["is_active"]:
            # Explicitly resolve open violations so disabling a rule clears its history
            # rather than leaving stale unresolved records.
            rows = ProductPolicyViolation.objects.filter(
                rule_type=rule_type,
                product=product,
                resolved=False,
            ).update(resolved=True, resolved_date=timezone.now())
            resolved_count += rows
            continue

        violation, created, resolved = evaluate_rule(
            rule_type, product, config["threshold"], config["parameters"]
        )
        if created:
            new_violations.append(violation)
        resolved_count += resolved

    fire_policy_webhooks(product, new_violations, resolved_count)
    return new_violations, resolved_count
