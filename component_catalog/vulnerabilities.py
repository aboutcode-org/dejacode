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

# Replace by fetching the endpoint once available.
# https://github.com/aboutcode-org/vulnerablecode/issues/1561#issuecomment-2298764730
VULNERABLECODE_TYPES = [
    "alpine",
    "alpm",
    "apache",
    "cargo",
    "composer",
    "conan",
    "deb",
    "gem",
    "generic",
    "github",
    "golang",
    "hex",
    "mattermost",
    "maven",
    "mozilla",
    "nginx",
    "npm",
    "nuget",
    "openssl",
    "pypi",
    "rpm",
    "ruby",
]


def fetch_for_queryset(queryset, dataspace, batch_size=50, timeout=None, logger=None):
    object_count = queryset.count()
    if object_count < 1:
        return

    vulnerablecode = VulnerableCode(dataspace)
    vulnerability_qs = Vulnerability.objects.scope(dataspace)
    created_vulnerabilities = 0

    for index, batch in enumerate(chunked_queryset(queryset, batch_size), start=1):
        if logger:
            logger.write(f"Progress: {intcomma(index * batch_size)}/{intcomma(object_count)}")

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


def fetch_from_vulnerablecode(dataspace, batch_size, timeout, logger=None):
    start_time = timer()
    vulnerablecode = VulnerableCode(dataspace)
    if not vulnerablecode.is_configured():
        return

    package_qs = (
        Package.objects.scope(dataspace)
        .has_package_url()
        .only("dataspace", *PACKAGE_URL_FIELDS)
        .filter(type__in=VULNERABLECODE_TYPES)
        .order_by("-last_modified_date")
    )
    package_count = package_qs.count()
    if logger:
        logger.write(f"{package_count} Packages in the queue.")

    created = fetch_for_queryset(package_qs, dataspace, batch_size, timeout, logger)
    run_time = timer() - start_time
    if logger:
        logger.write(f"+ Created {intcomma(created)} vulnerabilities")
        logger.write(f"Completed in {humanize_time(run_time)}")

    dataspace.vulnerabilities_updated_at = timezone.now()
    dataspace.save(update_fields=["vulnerabilities_updated_at"])
