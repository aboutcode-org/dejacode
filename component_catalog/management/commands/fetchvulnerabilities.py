#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.management.base import CommandError
from django.utils import timezone

from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.models import Vulnerability
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.management.commands import DataspacedCommand
from dje.utils import chunked

# TODO: Retry failures
# ERROR VulnerableCode [Exception] HTTPSConnectionPool(host='public.vulnerablecode.io',
# port=443): Read timed out. (read timeout=10)


def fetch_from_vulnerablecode(vulnerablecode, batch_size, timeout, logger):
    dataspace = vulnerablecode.dataspace
    package_qs = Package.objects.scope(dataspace).has_package_url()
    logger.write(f"{package_qs.count()} Packages in the queue.")

    # TODO: Add support for Component
    component_qs = Component.objects.scope(dataspace).exclude(cpe="")
    logger.write(f"{component_qs.count()} Components in the queue.")

    # TODO: Replace this by a create_or_update
    Vulnerability.objects.all().delete()
    vulnerability_qs = Vulnerability.objects.scope(dataspace)

    for packages_batch in chunked(package_qs, chunk_size=batch_size):
        entries = vulnerablecode.get_vulnerable_purls(
            packages_batch, purl_only=False, timeout=timeout
        )
        for entry in entries:
            affected_by_vulnerabilities = entry.get("affected_by_vulnerabilities")
            if not affected_by_vulnerabilities:
                continue

            affected_packages = package_qs.filter(
                type=entry.get("type"),
                namespace=entry.get("namespace") or "",
                name=entry.get("name"),
                version=entry.get("version") or "",
                # qualifiers=entry.get("qualifiers") or {},
                subpath=entry.get("subpath") or "",
            )
            if not affected_packages:
                raise CommandError("Could not find package!")

            for vulnerability in affected_by_vulnerabilities:
                vulnerability_id = vulnerability["vulnerability_id"]
                if vulnerability_qs.filter(vulnerability_id=vulnerability_id).exists():
                    continue  # -> TODO: Update from data in that case?
                Vulnerability.create_from_data(
                    dataspace=dataspace,
                    data=vulnerability,
                    affected_packages=affected_packages,
                )

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
            default=10,
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
