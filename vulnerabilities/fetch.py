#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from timeit import default_timer as timer

from django.contrib.contenttypes.models import ContentType
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from packageurl import PackageURL

from component_catalog.models import PACKAGE_URL_FIELDS
from component_catalog.models import Package
from component_catalog.models import PackageAffectedByVulnerability
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.models import DejacodeUser
from dje.utils import chunked_queryset
from dje.utils import humanize_time
from notification.models import find_and_fire_hook
from vulnerabilities.models import Vulnerability


def fetch_from_vulnerablecode(dataspace, batch_size, update, timeout, log_func=None, verbosity=1):
    """Fetch vulnerability data from VulnerableCode for all eligible packages in ``dataspace``."""
    start_time = timer()
    vulnerablecode = VulnerableCode(dataspace)
    if not vulnerablecode.is_configured():
        if log_func:
            log_func("VulnerableCode is not configured.")
        return

    available_types = vulnerablecode.get_package_url_available_types()
    package_qs = (
        Package.objects.scope(dataspace)
        .has_package_url()
        .only("dataspace", *PACKAGE_URL_FIELDS)
        .filter(type__in=available_types)
        .order_by("-last_modified_date")
    )
    package_count = package_qs.count()
    if log_func:
        log_func(f"{package_count} Packages in the queue.")

    results = fetch_for_packages(
        queryset=package_qs,
        dataspace=dataspace,
        batch_size=batch_size,
        update=update,
        timeout=timeout,
        log_func=log_func,
        verbosity=verbosity,
    )

    run_time = timer() - start_time
    if log_func:
        log_func(f"+ Created {intcomma(results.get('created', 0))} vulnerabilities")
        log_func(f"+ Updated {intcomma(results.get('updated', 0))} vulnerabilities")
        log_func(f"Completed in {humanize_time(run_time)}")

    if results:
        dataspace.vulnerabilities_updated_at = timezone.now()
        dataspace.save(update_fields=["vulnerabilities_updated_at"])
        log_func("Dataspace.vulnerabilities_updated_at updated")


def fetch_for_packages(
    queryset, dataspace, batch_size=50, update=True, timeout=None, log_func=None, verbosity=1
):
    from product_portfolio.models import ProductPackage

    results = {"created": 0, "updated": 0}

    object_count = queryset.count()
    if object_count < 1:
        return results

    vulnerablecode = VulnerableCode(dataspace)
    # Tracks advisory_uids created during this run to avoid re-updating them in later batches.
    created_advisory_uids = set()

    for index, batch in enumerate(chunked_queryset(queryset, batch_size), start=1):
        batch_start = timer()
        progress_count = min(index * batch_size, object_count)
        if log_func:
            log_func(f"Progress: {intcomma(progress_count)}/{intcomma(object_count)}")

        batch_affected_packages = []
        batch_results = {"created": 0, "updated": 0}

        api_start = timer()
        vc_entries = vulnerablecode.get_vulnerable_purls(batch, details=True, timeout=timeout)
        api_elapsed = timer() - api_start

        if log_func and verbosity >= 2:
            log_func(
                f"  API call: {humanize_time(api_elapsed)} ({len(vc_entries)} vulnerable purls)"
            )

        # One SELECT for all advisory_uids in this batch instead of one per vulnerability.
        all_advisory_uids = [
            vulnerability_data["advisory_uid"]
            for vc_entry in vc_entries
            for vulnerability_data in (vc_entry.get("affected_by_vulnerabilities") or [])
        ]
        vulnerability_cache = {
            vulnerability.advisory_uid: vulnerability
            for vulnerability in Vulnerability.objects.scope(dataspace).filter(
                advisory_uid__in=all_advisory_uids
            )
        }

        for vc_entry in vc_entries:
            affected_packages = process_vc_entry(
                vc_entry,
                queryset,
                dataspace,
                update,
                batch_results,
                vulnerability_cache,
                created_advisory_uids,
                log_func,
                verbosity,
            )
            batch_affected_packages.extend(affected_packages)

        product_package_qs = ProductPackage.objects.filter(package__in=batch_affected_packages)
        product_package_qs.update_weighted_risk_score()

        results["created"] += batch_results["created"]
        results["updated"] += batch_results["updated"]

        if log_func and verbosity >= 2:
            batch_elapsed = timer() - batch_start
            db_elapsed = batch_elapsed - api_elapsed
            log_func(
                f"  Batch done: {batch_results['created']} created, "
                f"{batch_results['updated']} updated "
                f"(API: {humanize_time(api_elapsed)}, processing: {humanize_time(db_elapsed)}, "
                f"total: {humanize_time(batch_elapsed)})"
            )

    return results


def batch_add_affected(affected_packages, vulnerabilities):
    """
    Link all ``vulnerabilities`` to all ``affected_packages`` using two queries:
    one SELECT to find existing relationships, one bulk INSERT for the missing ones.

    Replaces N*M individual ``get_or_create`` calls from ``add_affected_by``.
    """
    existing_pairs = set(
        PackageAffectedByVulnerability.objects.filter(
            package__in=affected_packages,
            vulnerability__in=vulnerabilities,
        ).values_list("package_id", "vulnerability_id")
    )
    to_create = [
        PackageAffectedByVulnerability(
            package=package,
            vulnerability=vulnerability,
            dataspace_id=package.dataspace_id,
        )
        for package in affected_packages
        for vulnerability in vulnerabilities
        if (package.pk, vulnerability.pk) not in existing_pairs
    ]
    if to_create:
        PackageAffectedByVulnerability.objects.bulk_create(to_create, ignore_conflicts=True)


def process_vc_entry(
    vc_entry,
    queryset,
    dataspace,
    update,
    results,
    vulnerability_cache,
    created_advisory_uids,
    log_func=None,
    verbosity=1,
):
    """
    Process a single VulnerableCode purl entry: find the matching packages in ``queryset``,
    create or update each linked vulnerability, and apply the API-provided risk score.

    ``vulnerability_cache`` is a dict mapping advisory_uid to Vulnerability instances,
    pre-fetched by the caller in a single batch query. Newly created vulnerabilities are
    added to the cache so subsequent entries in the same batch reuse them without a DB hit.

    M2M links between packages and vulnerabilities are created in batch via
    ``batch_add_affected`` (1 SELECT + 1 bulk INSERT) instead of one ``get_or_create``
    per pair.

    Risk score is applied in a single UPDATE query, bypassing ``Package.save()`` and the
    ``handle_assigned_licenses`` overhead it carries. The API-provided purl-level
    ``risk_score`` is used directly when present; otherwise the MAX of the linked
    vulnerability risk scores is computed in the same query.

    Returns the affected packages as a list (already evaluated), or an empty list if the
    entry has no vulnerabilities. The ``results`` dict is updated in-place.
    """
    affected_by_vulnerabilities = vc_entry.get("affected_by_vulnerabilities")
    if not affected_by_vulnerabilities:
        return []

    purl = PackageURL.from_string(vc_entry.get("purl"))
    # Evaluate to a list immediately: packages_qs.update() below clears the QS cache,
    # which would cause a re-SELECT when the caller iterates the return value.
    packages_qs = queryset.filter(
        type=purl.type,
        namespace=purl.namespace or "",
        name=purl.name,
        version=purl.version,
    )
    affected_packages = list(packages_qs)
    if not affected_packages:
        raise CommandError("Could not find packages!")

    if log_func and verbosity >= 2:
        advisory_count = len(affected_by_vulnerabilities)
        label = "advisory" if advisory_count == 1 else "advisories"
        log_func(f"  {purl}: {advisory_count} {label}")

    vulnerabilities = []
    for vulnerability_data in affected_by_vulnerabilities:
        advisory_uid = vulnerability_data["advisory_uid"]
        vulnerability = create_or_update_vulnerability(
            vulnerability_data,
            dataspace,
            update,
            results,
            vulnerability=vulnerability_cache.get(advisory_uid),
            created_advisory_uids=created_advisory_uids,
        )
        vulnerability_cache[advisory_uid] = vulnerability
        vulnerabilities.append(vulnerability)

    # Link packages to vulnerabilities: 1 SELECT + 1 bulk INSERT instead of N*M get_or_create.
    batch_add_affected(affected_packages, vulnerabilities)

    # Update risk_score without triggering Package.save() (which carries handle_assigned_licenses).
    if package_risk_score := vc_entry.get("risk_score"):
        packages_qs.update(risk_score=package_risk_score)

    return affected_packages


def create_or_update_vulnerability(
    vulnerability_data, dataspace, update, results, vulnerability=None, created_advisory_uids=None
):
    """
    Create or update a Vulnerability from ``vulnerability_data``.

    ``vulnerability`` is the already-resolved instance (looked up from the caller's
    ``vulnerability_cache``), or ``None`` if not yet created. M2M linking is handled
    by the caller via ``batch_add_affected``.

    ``created_advisory_uids`` is a run-wide set of advisory_uids created during this fetch.
    Vulnerabilities in this set are skipped for updates to avoid spurious re-updates when the
    same advisory appears in multiple packages across different batches.
    """
    advisory_uid = vulnerability_data["advisory_uid"]
    if not vulnerability:
        vulnerability = Vulnerability.create_from_data(
            dataspace=dataspace,
            data=vulnerability_data,
        )
        results["created"] += 1
        if created_advisory_uids is not None:
            created_advisory_uids.add(advisory_uid)
    elif update and advisory_uid not in (created_advisory_uids or ()):
        updated_fields = vulnerability.update_from_data(
            user=None,
            data=vulnerability_data,
            override=True,
        )
        if updated_fields:
            results["updated"] += 1

    return vulnerability


def notify_vulnerability_data_update(dataspace):
    """
    Trigger the notifications related to fetching vulnerability data from
    VulnerableCode.
    """
    vulnerability_qs = Vulnerability.objects.scope(dataspace).added_or_updated_today()
    package_qs = (
        Package.objects.scope(dataspace)
        .filter(affected_by_vulnerabilities__in=vulnerability_qs)
        .distinct()
    )

    vulnerability_count = vulnerability_qs.count()
    if not vulnerability_count:
        return

    package_count = package_qs.count()
    subject = "[DejaCode] New vulnerabilities detected!"

    # 1. Webhooks (simple message)
    message = f"{vulnerability_count} vulnerabilities affecting {package_count} packages"
    find_and_fire_hook(
        "vulnerability.data_update",
        instance=None,
        dataspace=dataspace,
        payload_override={"text": f"{subject}\n{message}"},
    )

    # 2. Internal notifications (message with internal links)
    vulnerability_list_url = reverse("vulnerabilities:vulnerability_list")
    vulnerability_link = (
        f'<a href="{vulnerability_list_url}?last_modified_date=today" target="_blank">'
        f"{vulnerability_count} vulnerabilities</a>"
    )
    package_list_url = reverse("component_catalog:package_list")
    package_link = (
        f'<a href="{package_list_url}?is_vulnerable=yes&affected_by_last_modified_date=today" '
        f'target="_blank"> {package_count} packages</a>'
    )
    message = f"{vulnerability_link} affecting {package_link}"

    users_to_notify = DejacodeUser.objects.get_vulnerability_notifications_users(dataspace)
    for user in users_to_notify:
        user.send_internal_notification(
            verb="New vulnerabilities detected",
            description=f"{message}",
            action_object_content_type=ContentType.objects.get_for_model(Vulnerability),
        )
