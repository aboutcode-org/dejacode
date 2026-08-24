#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import logging

from django.apps import apps
from django.utils import timezone

from vulnerabilities.triage.models import ProductTriageRuleset
from vulnerabilities.triage.models import TriageRecord
from vulnerabilities.triage.rules import RULE_REGISTRY
from vulnerabilities.triage.rules import rule_parameters_from_config

logger = logging.getLogger(__name__)


def collect_matches(ruleset, product):
    """
    Return a dict mapping each matching Vulnerability PK to the list of rule
    types that fired for it, for all active rules in the ruleset.
    """
    matched_rules_per_vulnerability_id = {}

    for rule_type, config in ruleset.rules_config.items():
        if not config.get("is_active"):
            continue

        handler = RULE_REGISTRY.get(rule_type)
        if not handler:
            continue

        parameters = rule_parameters_from_config(config)
        matching_vulnerability_ids = handler.get_matching_vulnerabilities(
            product=product,
            parameters=parameters,
        ).values_list("pk", flat=True)

        for vulnerability_id in matching_vulnerability_ids:
            matched_rules_per_vulnerability_id.setdefault(vulnerability_id, []).append(rule_type)

    return matched_rules_per_vulnerability_id


def apply_preset_for_vulnerabilities(preset, product, vulnerability_ids):
    """
    For each (product_package, vulnerability) pair in the product, create or update
    a VulnerabilityAnalysis using preset values.

    Skips any analysis already modified by a human (applied_by_preset is null on an
    existing record). Only analyses that were auto-created (applied_by_preset is set)
    or brand-new are touched. Skips creating a new analysis when the preset has no
    content fields set (state/justification/responses/detail), since saving an
    analysis with only is_reachable would fail model validation.
    """
    VulnerabilityAnalysis = apps.get_model("vulnerabilities", "VulnerabilityAnalysis")
    ProductPackage = apps.get_model("product_portfolio", "ProductPackage")

    # One query: exact (product_package_id, vulnerability_id) pairs to process.
    # Filtering by __id__in on the M2M restricts the JOIN rows to the matching
    # vulnerabilities, so values_list returns only the pairs we want.
    product_package_vulnerability_pairs = set(
        ProductPackage.objects.filter(
            product=product,
            package__affected_by_vulnerabilities__id__in=vulnerability_ids,
        )
        .values_list("id", "package__affected_by_vulnerabilities__id")
        .distinct()
    )

    if not product_package_vulnerability_pairs:
        return

    product_package_ids = {pair_pp_id for pair_pp_id, _ in product_package_vulnerability_pairs}

    # One query: all existing analyses for this product_package / vulnerability set
    existing_analyses = {
        (analysis.product_package_id, analysis.vulnerability_id): analysis
        for analysis in VulnerabilityAnalysis.objects.filter(
            product_package_id__in=product_package_ids,
            vulnerability_id__in=vulnerability_ids,
        )
    }

    # One query: product_package instances needed to construct new analyses
    product_packages_by_id = {
        product_package.pk: product_package
        for product_package in ProductPackage.objects.filter(pk__in=product_package_ids)
    }

    for product_package_id, vulnerability_id in product_package_vulnerability_pairs:
        existing = existing_analyses.get((product_package_id, vulnerability_id))

        if existing is not None and existing.applied_by_preset_id is None:
            continue  # User-owned analysis, never overwrite

        if existing is None:
            product_package = product_packages_by_id[product_package_id]
            analysis = VulnerabilityAnalysis(
                product_package=product_package,
                vulnerability_id=vulnerability_id,
                dataspace_id=product.dataspace_id,
            )
            preset.apply_to_analysis(analysis)
        else:
            analysis = existing
            preset.apply_to_analysis(analysis)

        analysis.applied_by_preset = preset
        analysis.save()


def delete_preset_analyses_for_product(preset_id, product, vulnerability_ids):
    """
    Delete VulnerabilityAnalysis records applied by the given preset for the given
    product and vulnerability set.
    """
    VulnerabilityAnalysis = apps.get_model("vulnerabilities", "VulnerabilityAnalysis")
    ProductPackage = apps.get_model("product_portfolio", "ProductPackage")

    product_package_ids = list(
        ProductPackage.objects.filter(product=product).values_list("id", flat=True)
    )
    VulnerabilityAnalysis.objects.filter(
        product_package_id__in=product_package_ids,
        vulnerability_id__in=vulnerability_ids,
        applied_by_preset_id=preset_id,
    ).delete()


def delete_triage_records_for_assignment(ruleset, product):
    """
    Delete triage records for a ruleset being unassigned from a product.

    VulnerabilityAnalysis records already applied by the ruleset's preset are left
    untouched: the facts that justified them have not changed, only the decision to keep
    monitoring with this ruleset. This matches disabling a ruleset, which also leaves
    previously-applied analyses in place.
    """
    matching_records = TriageRecord.objects.filter(ruleset=ruleset, product=product)
    # Records with an open Request are kept so reassigning the ruleset reconnects to it
    # instead of opening a duplicate Request.
    matching_records.filter(request__isnull=True).delete()


def sync_triage_records(ruleset, product, matched_rules_per_vulnerability_id, apply_preset=True):
    """
    Create or update one TriageRecord per matching vulnerability, then
    delete records for vulnerabilities that no longer match any rule in the ruleset.
    Applies the ruleset's analysis_preset when configured and apply_preset is True.
    """
    now = timezone.now()
    records = [
        TriageRecord(
            vulnerability_id=vulnerability_id,
            product=product,
            ruleset=ruleset,
            recommended_action=ruleset.recommended_action,
            matched_rules=matched_rules,
            dataspace=ruleset.dataspace,
            detected_date=now,
            last_checked=now,
        )
        for vulnerability_id, matched_rules in matched_rules_per_vulnerability_id.items()
    ]
    TriageRecord.objects.bulk_create(
        records,
        update_conflicts=True,
        unique_fields=["vulnerability", "product", "ruleset"],
        update_fields=["recommended_action", "matched_rules", "last_checked", "dataspace"],
    )

    stale_records_qs = TriageRecord.objects.filter(
        ruleset=ruleset,
        product=product,
    ).exclude(vulnerability_id__in=matched_rules_per_vulnerability_id.keys())

    if ruleset.analysis_preset_id:
        stale_vulnerability_ids = list(stale_records_qs.values_list("vulnerability_id", flat=True))
        if stale_vulnerability_ids:
            delete_preset_analyses_for_product(
                preset_id=ruleset.analysis_preset_id,
                product=product,
                vulnerability_ids=stale_vulnerability_ids,
            )

    # Records with an open Request are kept so a later rematch reconnects to it (via the
    # update_conflicts upsert above) instead of opening a duplicate Request.
    stale_records_qs.filter(request__isnull=True).delete()

    if apply_preset and ruleset.analysis_preset_id and matched_rules_per_vulnerability_id:
        apply_preset_for_vulnerabilities(
            preset=ruleset.analysis_preset,
            product=product,
            vulnerability_ids=list(matched_rules_per_vulnerability_id.keys()),
        )

    # Open a workflow Request for each TriageRecord when the Ruleset request_template is set.
    if ruleset.request_template_id:
        records_without_request = TriageRecord.objects.filter(
            ruleset=ruleset,
            product=product,
            request=None,
        ).select_related("vulnerability")

        if records_without_request:
            create_triage_requests(
                request_template=ruleset.request_template,
                product=product,
                records=records_without_request,
            )


def create_triage_requests(request_template, product, records):
    """
    Open one Request per TriageRecord using the given request_template.

    Uses the request_template creator as requester.
    """
    requester = request_template.created_by

    for record in records:
        advisory_id = record.vulnerability.advisory_id
        triage_request = request_template.create_request(
            requester=requester,
            title=f"Vulnerability: {advisory_id}",
            product_context=product,
            object_id=product.pk,
        )
        TriageRecord.objects.filter(pk=record.pk).update(request=triage_request)


def evaluate_ruleset(ruleset, product, apply_preset=True):
    """Evaluate a TriageRuleset against a product and persist the results."""
    matched_rules_per_vulnerability_id = collect_matches(ruleset=ruleset, product=product)
    sync_triage_records(
        ruleset=ruleset,
        product=product,
        matched_rules_per_vulnerability_id=matched_rules_per_vulnerability_id,
        apply_preset=apply_preset,
    )


def evaluate_assignments(assignments):
    """
    Evaluate each ProductTriageRuleset assignment in the given queryset, skipping and
    logging any that raise instead of aborting the whole batch.

    Returns the number of assignments successfully evaluated.
    """
    evaluated_count = 0
    for assignment in assignments:
        try:
            evaluate_ruleset(ruleset=assignment.ruleset, product=assignment.product)
        except Exception:
            logger.exception(
                f"Triage evaluation failed for ruleset id={assignment.ruleset_id} /"
                f" product id={assignment.product_id}, skipping."
            )
            continue
        evaluated_count += 1
    return evaluated_count


def reevaluate_product_rulesets(product, apply_preset=True):
    """Re-evaluate all enabled triage rulesets currently assigned to the product."""
    assignments = ProductTriageRuleset.objects.filter(
        product=product, ruleset__enabled=True
    ).select_related("ruleset", "ruleset__analysis_preset")

    for assignment in assignments:
        evaluate_ruleset(ruleset=assignment.ruleset, product=product, apply_preset=apply_preset)
