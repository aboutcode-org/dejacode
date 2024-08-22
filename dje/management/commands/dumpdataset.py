#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.core.serializers.json import Serializer

from component_catalog.models import AcceptableLinkage
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedLicense
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from component_catalog.models import PackageAssignedLicense
from component_catalog.models import Subcomponent
from component_catalog.models import SubcomponentAssignedLicense
from dje.management import LICENSE_LIBRARY_MODELS
from dje.management import POLICY_MODELS
from dje.management import PRODUCT_PORTFOLIO_MODELS
from dje.management import REPORTING_MODELS
from dje.management import get_component_limited_qs
from dje.management import get_owner_limited_qs
from dje.models import Dataspace
from dje.models import ExternalSource
from dje.models import get_unsecured_manager
from organization.models import Owner
from organization.models import Subowner
from workflow.models import Priority
from workflow.models import Question
from workflow.models import RequestTemplate


class ExcludeFieldsSerializer(Serializer):
    exclude_fields = [
        "request_count",
    ]

    def handle_field(self, obj, field):
        """
        Add the ability to exclude fields from the serialization output
        using the `self.exclude_fields` attribute.
        """
        if field.name in self.exclude_fields:
            return
        super().handle_field(obj, field)


class Command(BaseCommand):
    help = "Output the contents of the all DejaCode data for the " "given Dataspace as a fixture."

    def add_arguments(self, parser):
        parser.add_argument("dataspace_name", help="Name of the Dataspace.")
        parser.add_argument(
            "--dataspace",
            action="store_true",
            dest="dataspace",
            default=False,
            help="Only the given Dataspace will be dumped.",
        )
        parser.add_argument(
            "--user",
            action="store_true",
            dest="user",
            default=False,
            help="Only Dataspace and User Models will be dumped.",
        )
        parser.add_argument(
            "--external",
            action="store_true",
            dest="external",
            default=False,
            help="Only ExternalSource instances will be dumped.",
        )
        parser.add_argument(
            "--policy",
            action="store_true",
            dest="policy",
            default=False,
            help="Only UsagePolicy instances will be dumped.",
        )
        parser.add_argument(
            "--organization",
            action="store_true",
            dest="organization",
            default=False,
            help="Only Organization Models will be dumped.",
        )
        parser.add_argument(
            "--license_library",
            action="store_true",
            dest="license_library",
            default=False,
            help="Only License Library Models will be dumped.",
        )
        parser.add_argument(
            "--component_catalog",
            action="store_true",
            dest="component_catalog",
            default=False,
            help="Only Component Catalog Models with some extra filtering will be dumped.",
        )
        parser.add_argument(
            "--workflow",
            action="store_true",
            dest="workflow",
            default=False,
            help="Only Workflow Models will be dumped.",
        )
        parser.add_argument(
            "--reporting",
            action="store_true",
            dest="reporting",
            default=False,
            help="Only Reporting Models will be dumped.",
        )
        parser.add_argument(
            "--product_portfolio",
            action="store_true",
            dest="product_portfolio",
            default=False,
            help="Only Product Models will be dumped.",
        )

    def handle(self, *args, **options):
        dataspace_name = options.get("dataspace_name")
        try:
            dataspace = Dataspace.objects.get(name=dataspace_name)
        except Dataspace.DoesNotExist:
            raise CommandError(f"The Dataspace {dataspace_name} does not exit.")

        models = []
        data = []

        if options.get("dataspace"):
            data = [dataspace]

        if options.get("user"):
            data = [dataspace]  # includes the dataspace
            data += list(get_user_model().objects.scope(dataspace))

        if options.get("external"):
            models = [ExternalSource]

        if options.get("policy"):
            models = POLICY_MODELS[:]

        if options.get("organization"):
            owner_limited_qs = get_owner_limited_qs(dataspace)
            data += list(owner_limited_qs)
            subowner_limited_qs = (
                Subowner.objects.filter(
                    parent__in=owner_limited_qs,
                    child__in=owner_limited_qs,
                )
                .select_related(
                    "parent__dataspace",
                    "child__dataspace",
                )
                .distinct()
            )
            data += list(subowner_limited_qs)

        if options.get("license_library"):
            models = LICENSE_LIBRARY_MODELS[:]

        if options.get("product_portfolio"):
            component_qs = (
                Component.objects.scope(dataspace)
                .filter(productcomponents__isnull=False)
                .exclude(id__in=get_component_limited_qs(dataspace))
            )
            owner_qs = (
                Owner.objects.scope(dataspace)
                .filter(component__in=component_qs)
                .exclude(id__in=get_owner_limited_qs(dataspace))
            )
            package_qs = Package.objects.scope(dataspace).filter(productpackages__isnull=False)

            data += list(owner_qs)
            data += list(component_qs)
            data += list(package_qs)

            models = PRODUCT_PORTFOLIO_MODELS[:]

        if options.get("component_catalog"):
            data += list(ComponentType.objects.scope(dataspace))
            data += list(ComponentStatus.objects.scope(dataspace))
            data += list(AcceptableLinkage.objects.scope(dataspace))

            components = get_component_limited_qs(dataspace)
            component_ids = list(components.values_list("id", flat=True))
            data += list(components)

            subcomponents = (
                Subcomponent.objects.filter(parent_id__in=component_ids, child_id__in=component_ids)
                .select_related(
                    "parent__dataspace",
                    "child__dataspace",
                )
                .distinct()
            )
            data += list(subcomponents)

            # From Django docs:
            # "When fixture files are processed, the data is saved to the
            # database as is. Model defined save() methods are not called, ..."
            # The handle_assigned_licenses() method is not called so we need to dump
            # ComponentAssignedLicense and SubcomponentAssignedLicense models data
            data += list(
                ComponentAssignedLicense.objects.filter(
                    component__id__in=component_ids
                ).select_related()
            )
            data += list(
                SubcomponentAssignedLicense.objects.filter(
                    subcomponent__in=subcomponents
                ).select_related()
            )

            data += list(ComponentKeyword.objects.scope(dataspace))

            packages = (
                Package.objects.filter(componentassignedpackage__component__id__in=component_ids)
                .select_related()
                .distinct()
            )
            data += list(packages)
            data += list(
                ComponentAssignedPackage.objects.filter(component__id__in=component_ids)
                .select_related()
                .distinct()
            )
            data += list(
                PackageAssignedLicense.objects.filter(package__in=packages)
                .select_related()
                .distinct()
            )

        if options.get("workflow"):
            models = [RequestTemplate, Question, Priority]

        if options.get("reporting"):
            models = REPORTING_MODELS[:]

        for model_class in models:
            qs = get_unsecured_manager(model_class).scope(dataspace).select_related()
            data += list(qs)

        return ExcludeFieldsSerializer().serialize(
            queryset=data,
            indent=2,
            use_natural_foreign_keys=True,
            use_natural_primary_keys=True,
        )
