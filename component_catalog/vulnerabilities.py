#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from timeit import default_timer as timer

from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.management.base import CommandError
from django.utils import timezone

from component_catalog.models import PACKAGE_URL_FIELDS
from component_catalog.models import Package
from component_catalog.models import Vulnerability
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.utils import chunked_queryset
from dje.utils import humanize_time


def fetch_from_vulnerablecode(dataspace, batch_size, timeout, log_func=None):
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

    created = fetch_for_queryset(package_qs, dataspace, batch_size, timeout, log_func)
    run_time = timer() - start_time
    if log_func:
        log_func(f"+ Created {intcomma(created)} vulnerabilities")
        log_func(f"Completed in {humanize_time(run_time)}")

    dataspace.vulnerabilities_updated_at = timezone.now()
    dataspace.save(update_fields=["vulnerabilities_updated_at"])


def fetch_for_queryset(queryset, dataspace, batch_size=50, timeout=None, log_func=None):
    object_count = queryset.count()
    if object_count < 1:
        return

    vulnerablecode = VulnerableCode(dataspace)
    vulnerability_qs = Vulnerability.objects.scope(dataspace)
    created_vulnerabilities = 0

    for index, batch in enumerate(chunked_queryset(queryset, batch_size), start=1):
        if log_func:
            progress_count = index * batch_size
            if progress_count > object_count:
                progress_count = object_count
            log_func(f"Progress: {intcomma(progress_count)}/{intcomma(object_count)}")

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

            for vulnerability_data in affected_by_vulnerabilities:
                vulnerability_id = vulnerability_data["vulnerability_id"]
                vulnerability = vulnerability_qs.get_or_none(vulnerability_id=vulnerability_id)
                if not vulnerability:
                    vulnerability = Vulnerability.create_from_data(
                        dataspace=dataspace,
                        data=vulnerability_data,
                    )
                    created_vulnerabilities += 1
                vulnerability.add_affected_packages(affected_packages)

    return created_vulnerabilities
