#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.forms.models import model_to_dict

from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from dje.management.commands import DataspacedCommand
from organization.models import Owner


class Command(DataspacedCommand):
    help = "Create Components from Packages"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("username", help="Your username, for History entries.")
        parser.add_argument(
            "--last_modified_date",
            help=(
                "Limit the packages batch to objects created/modified after that date. "
                'Format: "YYYY-MM-DD"'
            ),
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        try:
            self.user = get_user_model().objects.get(
                username=options["username"],
                dataspace=self.dataspace,
            )
        except ObjectDoesNotExist:
            raise CommandError("The given username does not exist.")

        # Packages without any assigned components
        package_qs = Package.objects.scope(self.dataspace).filter(component__isnull=True)

        if last_modified_date := options["last_modified_date"]:
            try:
                package_qs = package_qs.filter(last_modified_date__gt=last_modified_date)
            except ValidationError as e:
                raise CommandError(e)

        self.component_qs = Component.objects.scope(self.dataspace)
        self.owner_qs = Owner.objects.scope(self.dataspace)
        self.approved_status = ComponentStatus.objects.scope(self.dataspace).get(label="Approved")
        self.file_type = ComponentType.objects.scope(self.dataspace).get(label="File")

        created = []
        errors = []

        for package in package_qs:
            component = None
            try:
                component = self.create_component_from_package(package)
            except Exception as e:
                errors.append(e)

            if component:
                created.append(component)
                _ = ComponentAssignedPackage.objects.create(
                    component=component,
                    package=package,
                    dataspace=self.dataspace,
                )

        self.stdout.write(self.style.SUCCESS(f"{len(created)} Component(s) created."))
        if errors:
            self.stdout.write(self.style.ERROR(f"{len(errors)} errors:"))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"- {error}"))

    def create_component_from_package(self, package):
        # When a component with this name/version already exist, skip
        if self.component_qs.filter(name__iexact=package.name, version=package.version):
            return

        component_data = model_to_dict(package)
        component_data.pop("id", None)
        # ``licenses`` are assigned from the ``license_expression`` field
        component_data.pop("licenses", None)
        component_data["curation_level"] = 45
        # ForeignKeys
        component_data["configuration_status"] = self.approved_status
        component_data["type"] = self.file_type
        # Package usage policies are not shared with components
        # The proper policy will be set from the ``license_expression`` value
        component_data.pop("usage_policy", None)

        if inferred_url := package.inferred_url:
            component_data["code_view_url"] = inferred_url
            component_data["homepage_url"] = inferred_url

        if package.notice_text:
            component_data["is_license_notice"] = True
            component_data["is_notice_in_codebase"] = True

        # Check for components that already exists in a different version,
        # we can use the owner the keywords from that component
        if existing := self.component_qs.filter(name__iexact=package.name, owner__isnull=False):
            component_data["owner"] = existing[0].owner
            if keywords := existing[0].keywords:
                component_data["keywords"] = keywords

        # Set owner
        if not component_data.get("owner"):
            component_data["owner"] = self.get_owner(component_data)

        component = Component.create_from_data(self.user, component_data, validate=False)
        component.update_completion_level()
        return component

    def get_owner(self, component_data):
        owner_name = ""
        contact_info = ""
        owner_type = ""

        # Start with the ``parties`` field
        parties = component_data.get("parties")
        if parties and parties[0].get("name"):
            owner_name = parties[0].get("name")
            owner_type = "Person"
            contact_info = parties[0].get("email") or ""
        # If there is a ``holder`` value on the package, search reference data Owners
        # for that and use it if found, or create a new owner otherwise.
        elif holder := component_data.get("holder"):
            owner_name = holder
        # If the component name, derived from the package name, is already in reference
        # data components in a different version, use the owner of that component.
        else:
            owner_name = component_data.get("name")
            if related_components := self.component_qs.filter(name__icontains=owner_name):
                return related_components[0].owner

        if match := self.owner_qs.filter(name__icontains=owner_name):
            return match[0]
        elif match := self.owner_qs.filter(name__icontains=f"{owner_name} Project"):
            return match[0]

        if owner_name:
            owner, _ = self.owner_qs.get_or_create(
                name=f"{owner_name}",
                dataspace=self.dataspace,
                defaults={
                    "contact_info": contact_info,
                    "type": owner_type,
                    "created_by": self.user,
                },
            )
            return owner

        self.stdout.write(f"Cannot found owner for {component_data.get('name')}")
