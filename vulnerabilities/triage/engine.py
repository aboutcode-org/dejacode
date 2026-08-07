#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.rules import RULE_REGISTRY


def collect_matches(ruleset, product):
    """
    Return a dict mapping each matching ProductPackage PK to the list of rule
    types that fired for it, for all active rules in the ruleset.
    """
    matched_rules_per_package_id = {}

    for rule_type, config in ruleset.rules_config.items():
        if not config.get("is_active"):
            continue

        handler = RULE_REGISTRY.get(rule_type)
        if not handler:
            continue

        parameters = {key: value for key, value in config.items() if key != "is_active"}
        matching_package_ids = handler.get_matching_packages(
            product=product,
            parameters=parameters,
        ).values_list("pk", flat=True)

        for package_id in matching_package_ids:
            matched_rules_per_package_id.setdefault(package_id, []).append(rule_type)

    return matched_rules_per_package_id


def sync_triage_records(ruleset, product, matched_rules_per_package_id):
    """
    Create or update one TriageRecord record per matching package, then
    delete records for packages that no longer match any rule in the ruleset.
    """
    for product_package_id, matched_rules in matched_rules_per_package_id.items():
        TriageRecord.objects.update_or_create(
            product_package_id=product_package_id,
            ruleset=ruleset,
            defaults={
                "action": ruleset.action,
                "matched_rules": matched_rules,
                "dataspace": ruleset.dataspace,
            },
        )

    TriageRecord.objects.filter(
        ruleset=ruleset,
        product_package__product=product,
    ).exclude(product_package_id__in=matched_rules_per_package_id.keys()).delete()


def evaluate_ruleset(ruleset, product):
    """Evaluate a TriageRuleset against a product and persist the results."""
    matched_rules_per_package_id = collect_matches(ruleset=ruleset, product=product)
    sync_triage_records(
        ruleset=ruleset,
        product=product,
        matched_rules_per_package_id=matched_rules_per_package_id,
    )
