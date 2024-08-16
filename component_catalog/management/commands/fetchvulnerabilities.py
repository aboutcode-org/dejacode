#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.management.base import CommandError
from django.utils import timezone

from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.models import Vulnerability
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.management.commands import DataspacedCommand
from dje.utils import chunked_queryset

# TODO: Retry failures -> log those
# ERROR VulnerableCode [Exception] HTTPSConnectionPool(host='public.vulnerablecode.io',
# port=443): Read timed out. (read timeout=10)


# TODO: Add support for Component
def fetch_from_vulnerablecode(vulnerablecode, batch_size, timeout, logger):
    created_vulnerabilities = 0
    dataspace = vulnerablecode.dataspace
    vulnerability_qs = Vulnerability.objects.scope(dataspace)
    package_qs = (
        Package.objects.scope(dataspace)
        .has_package_url()
        .exclude(type="sourceforge")
        .order_by("-last_modified_date")
    )
    component_qs = (
        Component.objects.scope(dataspace).exclude(cpe="").order_by("-last_modified_date")
    )

    package_count = package_qs.count()
    logger.write(f"{package_count} Packages in the queue.")
    component_count = component_qs.count()
    logger.write(f"{component_count} Components in the queue.")

    for index, batch in enumerate(chunked_queryset(package_qs, chunk_size=batch_size), start=1):
        logger.write(f"Progress: {intcomma(index*batch_size)}/{intcomma(package_count)}")
        entries = vulnerablecode.get_vulnerable_purls(batch, purl_only=False, timeout=timeout)
        for entry in entries:
            affected_by_vulnerabilities = entry.get("affected_by_vulnerabilities")
            if not affected_by_vulnerabilities:
                continue

            affected_packages = package_qs.filter(
                type=entry.get("type"),
                namespace=entry.get("namespace") or "",
                name=entry.get("name"),
                version=entry.get("version") or "",
                # TODO: get_vulnerable_purls converts to plain purl, review this
                # qualifiers=entry.get("qualifiers") or {},
                # subpath=entry.get("subpath") or "",
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

    dataspace.vulnerabilities_updated_at = timezone.now()
    dataspace.save(update_fields=["vulnerabilities_updated_at"])


class Command(DataspacedCommand):
    help = "Fetch vulnerabilities for the provided Dataspace"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Specifies the number of objects per requests to the VulnerableCode service",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="Request timeout in seconds",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        vulnerablecode = VulnerableCode(self.dataspace)

        if not self.dataspace.enable_vulnerablecodedb_access:
            raise CommandError("VulnerableCode is not enabled on this Dataspace.")

        if not vulnerablecode.is_configured():
            raise CommandError("VulnerableCode is not configured.")

        batch_size = options["batch_size"]
        timeout = options["timeout"]
        fetch_from_vulnerablecode(vulnerablecode, batch_size, timeout, logger=self.stdout)
