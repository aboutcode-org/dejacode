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

from component_catalog.models import PACKAGE_URL_FIELDS
from component_catalog.models import Package
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.models import DejacodeUser
from dje.utils import chunked_queryset
from dje.utils import humanize_time
from notification.models import find_and_fire_hook
from vulnerabilities.models import Vulnerability


def fetch_from_vulnerablecode(dataspace, batch_size, update, timeout, log_func=None):
    start_time = timer()
    vulnerablecode = VulnerableCode(dataspace)
    if not vulnerablecode.is_configured():
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
    )
    run_time = timer() - start_time
    if log_func:
        log_func(f"+ Created {intcomma(results.get("created", 0))} vulnerabilities")
        log_func(f"+ Updated {intcomma(results.get("updated", 0))} vulnerabilities")
        log_func(f"Completed in {humanize_time(run_time)}")

    dataspace.vulnerabilities_updated_at = timezone.now()
    dataspace.save(update_fields=["vulnerabilities_updated_at"])


def fetch_for_packages(
    queryset, dataspace, batch_size=50, update=True, timeout=None, log_func=None
):
    from product_portfolio.models import ProductPackage

    object_count = queryset.count()
    if object_count < 1:
        return

    vulnerablecode = VulnerableCode(dataspace)
    results = {"created": 0, "updated": 0}

    for index, batch in enumerate(chunked_queryset(queryset, batch_size), start=1):
        if log_func:
            progress_count = index * batch_size
            if progress_count > object_count:
                progress_count = object_count
            log_func(f"Progress: {intcomma(progress_count)}/{intcomma(object_count)}")

        batch_affected_packages = []
        vc_entries = vulnerablecode.get_vulnerable_purls(batch, purl_only=False, timeout=timeout)
        for vc_entry in vc_entries:
            affected_by_vulnerabilities = vc_entry.get("affected_by_vulnerabilities")
            if not affected_by_vulnerabilities:
                continue

            affected_packages = queryset.filter(
                type=vc_entry.get("type"),
                namespace=vc_entry.get("namespace") or "",
                name=vc_entry.get("name"),
                version=vc_entry.get("version") or "",
            )
            if not affected_packages:
                raise CommandError("Could not find package!")

            # Store all packages of that batch to then trigger the update_weighted_risk_score
            batch_affected_packages.extend(affected_packages)

            for vulnerability_data in affected_by_vulnerabilities:
                create_or_update_vulnerability(
                    vulnerability_data, dataspace, affected_packages, update, results
                )

            if package_risk_score := vc_entry.get("risk_score"):
                affected_packages.update(risk_score=package_risk_score)

        product_package_qs = ProductPackage.objects.filter(package__in=batch_affected_packages)
        product_package_qs.update_weighted_risk_score()

    return results


def create_or_update_vulnerability(
    vulnerability_data, dataspace, affected_packages, update, results
):
    vulnerability_id = vulnerability_data["vulnerability_id"]
    vulnerability_qs = Vulnerability.objects.scope(dataspace)
    vulnerability = vulnerability_qs.get_or_none(vulnerability_id=vulnerability_id)

    if not vulnerability:
        vulnerability = Vulnerability.create_from_data(
            dataspace=dataspace,
            data=vulnerability_data,
        )
        results["created"] += 1
    elif update:
        updated_fields = vulnerability.update_from_data(
            user=None,
            data=vulnerability_data,
            override=True,
        )
        if updated_fields:
            results["updated"] += 1

    vulnerability.add_affected_packages(affected_packages)
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
        user.internal_notify(
            verb="New vulnerabilities detected",
            description=f"{message}",
            actor_content_type=ContentType.objects.get_for_model(Vulnerability),
            action_object_content_type=ContentType.objects.get_for_model(Vulnerability),
        )
