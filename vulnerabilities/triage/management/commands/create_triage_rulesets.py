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
        "name": "Critical Exploited Vulnerability",
        "description": (
            "Critical-severity vulnerability (risk score >= 8.0) with a known active exploit."
            " Requires immediate package upgrade."
        ),
        "action": TriageRuleset.Action.UPGRADE,
        "precedence": 400,
        "rules_config": {
            "risk_score": {"is_active": True, "min_risk_score": 8.0},
            "exploited_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Active Exploit",
        "description": (
            "Vulnerability with a known active exploit, regardless of severity."
            " Requires immediate package upgrade."
        ),
        "action": TriageRuleset.Action.UPGRADE,
        "precedence": 300,
        "rules_config": {
            "exploited_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Reachable Vulnerability",
        "description": (
            "Vulnerability confirmed as reachable in the product context."
            " Requires applying a patch."
        ),
        "action": TriageRuleset.Action.APPLY_PATCH,
        "precedence": 250,
        "rules_config": {
            "reachable_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Critical Vulnerability",
        "description": (
            "Critical-severity vulnerability (risk score >= 8.0) with no known exploit."
            " Requires applying a patch."
        ),
        "action": TriageRuleset.Action.APPLY_PATCH,
        "precedence": 200,
        "rules_config": {
            "risk_score": {"is_active": True, "min_risk_score": 8.0},
        },
    },
    {
        "name": "Stale Vulnerability",
        "description": (
            "Critical-severity vulnerability (risk score >= 8.0) unaddressed for more than 30 days."
            " Requires applying a patch without further delay."
        ),
        "action": TriageRuleset.Action.APPLY_PATCH,
        "precedence": 150,
        "rules_config": {
            "stale_vulnerability": {"is_active": True, "min_risk_score": 8.0, "max_days": 30},
        },
    },
    {
        "name": "Unresolved Vulnerability",
        "description": (
            "Packages with known vulnerabilities that have no completed triage analysis."
            " Requires forensic analysis to determine impact and next steps."
        ),
        "action": TriageRuleset.Action.FORENSIC_ANALYSIS,
        "precedence": 100,
        "rules_config": {
            "unresolved_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Dev-Only Vulnerable Package",
        "description": (
            "Packages not deployed in production that are affected by vulnerabilities."
            " Lower urgency, notify the team for awareness."
        ),
        "action": TriageRuleset.Action.NOTIFY,
        "precedence": 50,
        "rules_config": {
            "dev_only_vulnerable_package": {"is_active": True},
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
