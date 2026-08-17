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
from vulnerabilities.triage.models import AnalysisPreset
from vulnerabilities.triage.models import TriageAction
from vulnerabilities.triage.models import TriageRuleset

REFERENCE_PRESETS = [
    {
        "name": "Auto-Close - Dev Only",
        "description": (
            "Automatically close vulnerabilities that affect only non-deployed packages."
        ),
        "state": "not_affected",
        "justification": "code_not_present",
        "responses": ["will_not_fix"],
        "detail": "Package not deployed in production. Automatically closed by triage.",
        "ruleset_name": "Dev-Only Vulnerable Package",
    },
    {
        "name": "Flag - Active Exploit",
        "description": (
            "Flag vulnerabilities with a known active exploit for immediate human review."
        ),
        "state": "in_triage",
        "detail": "Known exploit detected. Flagged for immediate review by triage.",
        "ruleset_name": "Active Exploit",
    },
    {
        "name": "Flag - Stale Vulnerability",
        "description": (
            "Flag high-risk vulnerabilities unaddressed beyond the configured threshold."
        ),
        "state": "in_triage",
        "detail": "Vulnerability unaddressed beyond configured threshold. Escalated by triage.",
        "ruleset_name": "Stale Vulnerability",
    },
]

REFERENCE_RULESETS = [
    {
        "name": "Critical Exploited Vulnerability",
        "description": (
            "Vulnerabilities with a critical risk score and a known active exploit"
            " affecting the product."
        ),
        "recommended_action": TriageAction.UPGRADE,
        "precedence": 700,
        "rules_config": {
            "risk_score": {"is_active": True, "min_risk_score": 8.0},
            "exploited_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Active Exploit",
        "description": (
            "Vulnerabilities with a known active exploit affecting the product,"
            " regardless of severity."
        ),
        "recommended_action": TriageAction.UPGRADE,
        "precedence": 600,
        "rules_config": {
            "exploited_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Reachable Vulnerability",
        "description": "Vulnerabilities confirmed as reachable within the product context.",
        "recommended_action": TriageAction.APPLY_PATCH,
        "precedence": 500,
        "rules_config": {
            "reachable_vulnerability": {"is_active": True},
        },
    },
    {
        "name": "Critical Vulnerability",
        "description": (
            "Vulnerabilities with a critical risk score and no known active exploit"
            " affecting the product."
        ),
        "recommended_action": TriageAction.APPLY_PATCH,
        "precedence": 400,
        "rules_config": {
            "risk_score": {"is_active": True, "min_risk_score": 8.0},
        },
    },
    {
        "name": "Stale Vulnerability",
        "description": (
            "Vulnerabilities with a critical risk score left unaddressed"
            " for more than 30 days in the product."
        ),
        "recommended_action": TriageAction.APPLY_PATCH,
        "precedence": 300,
        "rules_config": {
            "stale_vulnerability": {"is_active": True, "min_risk_score": 8.0, "max_days": 30},
        },
    },
    {
        "name": "Dev-Only Vulnerable Package",
        "description": "Vulnerabilities affecting only non-deployed packages in the product.",
        "recommended_action": TriageAction.NOTIFY,
        "precedence": 200,
        "rules_config": {
            "dev_only_vulnerable_package": {"is_active": True},
        },
    },
    {
        "name": "Unresolved Vulnerability",
        "description": (
            "Vulnerabilities affecting the product where at least one package"
            " has no completed triage analysis."
        ),
        "recommended_action": TriageAction.FORENSIC_ANALYSIS,
        "precedence": 100,
        "rules_config": {
            "unresolved_vulnerability": {"is_active": True},
        },
    },
]


class Command(BaseCommand):
    help = "Create reference triage rulesets in the given dataspace."

    def add_arguments(self, parser):
        parser.add_argument("dataspace", help="Name of the target Dataspace.")
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Delete all existing triage rulesets in the dataspace before recreating them."
                " This also removes all associated product assignments and triage records."
            ),
        )

    def handle(self, *args, **options):
        dataspace_name = options["dataspace"]

        try:
            dataspace = Dataspace.objects.get(name=dataspace_name)
        except Dataspace.DoesNotExist:
            raise CommandError(f'Dataspace "{dataspace_name}" does not exist.')

        if options["reset"]:
            deleted_rulesets, _ = TriageRuleset.objects.filter(dataspace=dataspace).delete()
            deleted_presets, _ = AnalysisPreset.objects.filter(dataspace=dataspace).delete()
            self.stdout.write(
                f"  Deleted {deleted_rulesets} existing ruleset(s) and {deleted_presets} preset(s)."
            )

        ruleset_created_count = 0
        for ruleset_data in REFERENCE_RULESETS:
            _, created = TriageRuleset.objects.get_or_create(
                dataspace=dataspace,
                name=ruleset_data["name"],
                defaults={
                    "description": ruleset_data["description"],
                    "recommended_action": ruleset_data["recommended_action"],
                    "precedence": ruleset_data["precedence"],
                    "rules_config": ruleset_data["rules_config"],
                    "enabled": True,
                },
            )
            if created:
                ruleset_created_count += 1
                self.stdout.write(f"  Created: {ruleset_data['name']}")
            else:
                self.stdout.write(f"  Already exists: {ruleset_data['name']}")

        preset_created_count = 0
        for preset_data in REFERENCE_PRESETS:
            ruleset_name = preset_data["ruleset_name"]
            preset, preset_created = AnalysisPreset.objects.get_or_create(
                dataspace=dataspace,
                name=preset_data["name"],
                defaults={
                    "description": preset_data.get("description", ""),
                    "state": preset_data.get("state", ""),
                    "justification": preset_data.get("justification", ""),
                    "responses": preset_data.get("responses"),
                    "detail": preset_data.get("detail", ""),
                },
            )
            if preset_created:
                preset_created_count += 1
                self.stdout.write(f"  Created preset: {preset_data['name']}")
            else:
                self.stdout.write(f"  Already exists: {preset_data['name']}")
            try:
                ruleset = TriageRuleset.objects.get(dataspace=dataspace, name=ruleset_name)
                if ruleset.analysis_preset_id != preset.pk:
                    ruleset.analysis_preset = preset
                    ruleset.save(update_fields=["analysis_preset"])
                    self.stdout.write(f"    Linked preset to ruleset: {ruleset_name}")
            except TriageRuleset.DoesNotExist:
                self.stdout.write(f"    Ruleset not found: {ruleset_name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"{ruleset_created_count} ruleset(s) and {preset_created_count} preset(s)"
                f" created in dataspace '{dataspace_name}'."
            )
        )
