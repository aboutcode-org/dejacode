#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from django.core.management.base import CommandError

from component_catalog.models import Package
from component_catalog.models import Vulnerability
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje.management.commands import DataspacedCommand
from dje.models import DejacodeUser
from dje.utils import chunked


class Command(DataspacedCommand):
    help = "Fetch vulnerabilities for the provided Dataspace"

    def handle(self, *args, **options):
        super().handle(*args, **options)

        # TODO: Consider making the user optional on the Vulnerability model as its
        # automatically collected
        user = DejacodeUser.objects.scope(self.dataspace).all()[0]
        vulnerablecode = VulnerableCode(self.dataspace)

        if not self.dataspace.enable_vulnerablecodedb_access:
            raise CommandError("VulnerableCode is not enabled on this Dataspace.")

        if not vulnerablecode.is_configured():
            raise CommandError("VulnerableCode is not configured.")

        package_qs = Package.objects.scope(self.dataspace).has_package_url()
        self.stdout.write(f"{package_qs.count()} Packages in the queue.")

        # Vulnerability.objects.all().delete()
        for packages_batch in chunked(package_qs, chunk_size=10):
            entries = vulnerablecode.get_vulnerable_purls(packages_batch, purl_only=False)
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
                )
                if not affected_packages:
                    raise CommandError("Could not find package!")

                for vulnerability in affected_by_vulnerabilities:
                    Vulnerability.create_from_data(
                        user=user,
                        data=vulnerability,
                        affected_packages=affected_packages,
                    )
