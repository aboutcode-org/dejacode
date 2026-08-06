#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from dje.models import Dataspace
from vulnerabilities.triage.models import TriageRuleset

"""
docker compose -f compose.dev.yml exec web ./manage.py create_triage_rulesets nexB
"""

REFERENCE_RULESETS = [
    {
        "name": "Active Exploit",
        "description": "Packages with known active exploits require immediate upgrade.",
        "action": TriageRuleset.Action.UPGRADE,
        "precedence": 300,
        "rules_config": {
            "exploited_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Critical Vulnerability",
        "description": (
            "Critical vulnerabilities with no known exploit require forensic analysis."
        ),
        "action": TriageRuleset.Action.FORENSIC_ANALYSIS,
        "precedence": 200,
        "rules_config": {
            "critical_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Critical + Exploited",
        "description": ("Both critical severity and active exploit detected, upgrade immediately."),
        "action": TriageRuleset.Action.UPGRADE,
        "precedence": 400,
        "rules_config": {
            "critical_vulnerability": {"is_active": True},
            "exploited_vulnerability": {"is_active": True},
        },
    },
]


class Command(BaseCommand):
    help = "Create reference triage rulesets in the given dataspace."

    def add_arguments(self, parser):
        parser.add_argument("dataspace", help="Name of the target Dataspace.")

    def handle(self, *args, **options):
        dataspace_name = options["dataspace"]

        try:
            dataspace = Dataspace.objects.get(name=dataspace_name)
        except Dataspace.DoesNotExist:
            raise CommandError(f'Dataspace "{dataspace_name}" does not exist.')

        created_count = 0
        for ruleset_data in REFERENCE_RULESETS:
            _, created = TriageRuleset.objects.get_or_create(
                dataspace=dataspace,
                name=ruleset_data["name"],
                defaults={
                    "description": ruleset_data["description"],
                    "action": ruleset_data["action"],
                    "precedence": ruleset_data["precedence"],
                    "rules_config": ruleset_data["rules_config"],
                    "enabled": True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created: {ruleset_data['name']}")
            else:
                self.stdout.write(f"  Already exists: {ruleset_data['name']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"{created_count} ruleset(s) created in dataspace '{dataspace_name}'."
            )
        )
