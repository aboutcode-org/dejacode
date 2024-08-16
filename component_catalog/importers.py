#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import os
from urllib.parse import urlparse

from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError
from django.core.validators import EMPTY_VALUES
from django.db import models
from django.utils.dateparse import parse_date

import saneyaml

from component_catalog.forms import AcceptableLinkagesFormMixin
from component_catalog.forms import SetKeywordsChoicesFormMixin
from component_catalog.forms import SubcomponentLicenseExpressionFormMixin
from component_catalog.license_expression_dje import LicenseExpressionFormMixin
from component_catalog.models import Component
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from component_catalog.programming_languages import PROGRAMMING_LANGUAGES
from dje.fields import SmartFileField
from dje.forms import JSONListField
from dje.importers import BaseImporter
from dje.importers import BaseImportModelForm
from dje.importers import ComponentRelatedFieldImportMixin
from dje.importers import ModelChoiceFieldForImport
from dje.utils import get_help_text
from organization.models import Owner
from policy.models import UsagePolicy
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage

keywords_help = (
    get_help_text(Component, "keywords")
    + " You can add multiple keywords by separating them with commas, like this: "
    "keyword1, keyword2."
)


class OwnerChoiceField(ModelChoiceFieldForImport):
    def get_suggestions(self, value, limit=5):
        """
        Return a QuerySet of similar match, using the name__icontains filter,
        for a given value.
        """
        if self.queryset:
            dataspace = self.queryset.first().dataspace
        else:
            return

        owners = Owner.objects.scope(dataspace).filter(
            models.Q(name__icontains=value) | models.Q(alias__icontains=value)
        )

        return owners[:limit]

    def get_suggestion_message(self, value):
        """Return a message including the suggestions if any."""
        suggestions = self.get_suggestions(value)
        if not suggestions:
            return "No suggestion."

        names = [owner.name for owner in suggestions]
        return "Suggestion(s): {}.".format(", ".join(names))

    def to_python(self, value):
        """
        Wrap the original code to catch the ValidationError and add the
        suggestion in the error message.
        """
        try:
            value = super().to_python(value)
        except ValidationError:
            msg = "{} {}".format(
                self.error_messages["invalid_choice"], self.get_suggestion_message(value)
            )
            raise ValidationError(msg)
        return value


class CleanPrimaryLanguageFormMixin:
    def clean_primary_language(self):
        primary_language = self.cleaned_data["primary_language"]
        if primary_language and primary_language not in PROGRAMMING_LANGUAGES:
            language_mapping = {language.lower(): language for language in PROGRAMMING_LANGUAGES}
            proper_case = language_mapping.get(primary_language.lower(), None)
            if proper_case:
                msg = f'Language will be imported with proper case: "{proper_case}"'
                self.add_warning("primary_language", msg)
                return proper_case

            msg = f'"{primary_language}" is not in standard languages list.'
            suggestions = [
                language
                for language in PROGRAMMING_LANGUAGES
                if language.lower().startswith(str(primary_language[0]).lower())
            ]
            if suggestions:
                msg += "\nSuggestion(s): {}.".format(", ".join(suggestions))
            self.add_warning("primary_language", msg)

        return primary_language


class ImportMultipleChoiceField(forms.fields.MultipleChoiceField):
    def to_python(self, value):
        if not value:
            return []
        elif isinstance(value, str):
            return [label.strip() for label in value.split(",")]
        return [str(val) for val in value]


class ComponentImportForm(
    LicenseExpressionFormMixin,
    CleanPrimaryLanguageFormMixin,
    AcceptableLinkagesFormMixin,
    SetKeywordsChoicesFormMixin,
    BaseImportModelForm,
):
    """
    For now, each FK field of the Model needs to be redefined on this Form as a
    ModelChoiceFieldForImport field.
    """

    owner = OwnerChoiceField(
        queryset=Owner.objects.none(),
        required=False,
        # Using a TextInput as widget so the value is in the input
        widget=forms.TextInput,
        help_text=get_help_text(Component, "owner"),
        error_messages={"invalid_choice": "This Owner does not exists."},
    )

    type = ModelChoiceFieldForImport(
        queryset=ComponentType.objects.none(),
        required=False,
        help_text=get_help_text(Component, "type"),
        identifier_field="label",
    )

    configuration_status = ModelChoiceFieldForImport(
        queryset=ComponentStatus.objects.none(),
        required=False,
        help_text=get_help_text(Component, "configuration_status"),
        identifier_field="label",
    )

    usage_policy = ModelChoiceFieldForImport(
        queryset=UsagePolicy.objects.none(),
        required=False,
        help_text=get_help_text(Component, "usage_policy"),
        identifier_field="label",
    )

    keywords = JSONListField(
        required=False,
        help_text=keywords_help,
    )

    acceptable_linkages = ImportMultipleChoiceField(
        required=False,
    )

    class Meta:
        model = Component
        exclude = (
            "licenses",
            "children",
            "packages",
            "completion_level",
            "request_count",
            # JSONField not supported
            "dependencies",
        )

    def pre_process_form(self, data, **kwargs):
        instance = kwargs.pop("instance", None)
        self.prefix = kwargs.get("prefix")
        version = self.normalize_version(data.get(self.add_prefix("version"), "").strip())

        if not instance:  # No instance given, let's match our component
            try:
                instance = Component.objects.get(
                    name=data.get(self.add_prefix("name")).strip(),
                    version=version,
                    dataspace=self.dataspace,
                )
            except Component.DoesNotExist:
                pass

        return data, instance

    def normalize_version(self, version):
        if version.startswith("v"):
            version = version[1:].strip()
        return version

    def clean_version(self):
        original_version = self.cleaned_data["version"]
        normalized_version = self.normalize_version(original_version)
        if original_version != normalized_version:
            self.add_warning("version", f"Version will been cleaned to {normalized_version}")
        return normalized_version

    def save(self, commit=True):
        """Update the completion_level once everything including m2m were saved."""
        instance = super().save(commit)
        instance.update_completion_level()
        return instance


class ComponentImporter(BaseImporter):
    model_form = ComponentImportForm
    add_to_product_perm = "product_portfolio.add_productcomponent"
    relation_model = ProductComponent


class PackageImportForm(
    ComponentRelatedFieldImportMixin,
    LicenseExpressionFormMixin,
    CleanPrimaryLanguageFormMixin,
    SetKeywordsChoicesFormMixin,
    BaseImportModelForm,
):
    component = forms.CharField(
        required=False,  # We are allowing import without a Component attached
        help_text='"<name>:<version>" of the Component to be associated with this Package.',
    )

    usage_policy = ModelChoiceFieldForImport(
        queryset=UsagePolicy.objects.none(),
        required=False,
        help_text=get_help_text(Package, "usage_policy"),
        identifier_field="label",
    )

    keywords = JSONListField(
        required=False,
        help_text=keywords_help,
    )

    class Meta:
        model = Package
        exclude = [
            "licenses",
            # JSONField not supported
            "dependencies",
            "file_references",
            "request_count",
            "parties",
        ]

    def __init__(self, *args, **kwargs):
        self.is_from_scancode = kwargs.pop("is_from_scancode", False)
        super().__init__(*args, **kwargs)

    def clean_component(self):
        return self._clean_name_version_related_field("component", Component)

    def errors_to_warnings(self):
        """
        Convert the errors (blocking) list into warnings (not blocking).
        This is useful when the input is not meant to be edited by the user.
        Note that if the cleaning process raised an error for a given field,
        the value will not be included in the `cleaned_data`, thus not imported.
        """
        remaining_errors = {}
        for field_name, value in self._errors.items():
            if field_name == "filename":
                remaining_errors[field_name] = value
            else:
                self.add_warning(field_name, "Value is not valid, it will not be imported.")
        self._errors = remaining_errors

    def clean(self):
        cleaned_data = super().clean()
        if self.is_from_scancode:
            self.errors_to_warnings()
        return cleaned_data

    def save(self, commit=True):
        """Create the ComponentAssignedPackage after the Package instance is saved."""
        package = super().save(commit)
        component = self.cleaned_data.get("component")

        if component:
            ComponentAssignedPackage.objects.create(
                package=package, component=component, dataspace=package.dataspace
            )
            # Update the completion_level once the ComponentAssignedPackage was created
            component.update_completion_level()

        return package


class PackageImportableUploadFileForm(forms.Form):
    file = SmartFileField(extensions=["csv", "json"])

    @property
    def header(self):
        return "Select a <strong>CSV (.csv) or JSON (.json)</strong> file"


class PackageImporter(BaseImporter):
    model_form = PackageImportForm
    upload_form_class = PackageImportableUploadFileForm
    add_to_product_perm = "product_portfolio.add_productpackage"
    relation_model = ProductPackage
    update_existing = True

    def prepare_data_json(self, data):
        """
        Look for summary data (`--summary` ScanCode option) first as a
        shortcut to get all the detected packages.
        Iterate the whole scan results when the summary is not available.
        """
        if "summary" in data:
            packages = data.get("summary", {}).get("packages", [])
        else:
            packages = [
                package for file in data.get("files", []) for package in file.get("packages", [])
            ]

        if not packages:
            self.fatal_errors.append("No package data to import in input file.")
            return

        self.is_from_scancode = True
        packages = [self.prepare_package(package) for package in packages]
        input_as_list_of_dict = packages

        # Using a dict comprehension to keep the original key order and
        # ensure we have all possibile headers.
        header_row = {key: None for package in packages for key in package.keys()}
        header_row = list(header_row.keys())

        self.build_headers(header_row)

        return input_as_list_of_dict

    @staticmethod
    def prepare_package(package, path=None):
        """
        Prepare the package data during the ScanCode data import.
        WARNING: Do not return None, always return a package data.
        """
        # Warning: Files may have more than 1 entry in the future
        if not path:
            files = package.get("files")
            if files:
                path = files[0].get("path")

        map_if_none = {
            "homepage_url": "repository_homepage_url",
            "download_url": "repository_download_url",
        }
        for field, mapped_field in map_if_none.items():
            if not package.get(field):
                package[field] = package.get(mapped_field, "")

        filename = None
        download_url = package.get("download_url")
        if download_url:
            filename = os.path.basename(urlparse(download_url).path)

        if not filename and path:
            filename = path.strip("/").split("/")[-1]

        package["filename"] = filename

        field_to_notes = [
            "bug_tracking_url",
            "code_view_url",
            "vcs_url",
            "parties",
        ]
        notes = {}
        for field in field_to_notes:
            value = package.pop(field, None)
            if value:
                notes[field] = value
        if notes:
            package["notes"] = saneyaml.dump(notes)

        prepared_data = {}
        for field, value in package.items():
            if value in EMPTY_VALUES:
                continue

            try:
                model_field = Package._meta.get_field(field)
            except FieldDoesNotExist:
                continue

            if isinstance(model_field, models.DateField):
                value = parse_date(value)
            elif field == "dependencies":
                value = json.dumps(value, indent=2)
            elif field == "keywords":
                pass
            else:
                value = str(value)

            prepared_data[field] = value

        return prepared_data

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["is_from_scancode"] = getattr(self, "is_from_scancode", False)
        return kwargs


class SubcomponentImportForm(
    ComponentRelatedFieldImportMixin,
    SubcomponentLicenseExpressionFormMixin,
    BaseImportModelForm,
):
    parent = forms.CharField(help_text='"<name>:<version>" of the parent Component.')

    child = forms.CharField(help_text='"<name>:<version>" of the child Component.')

    usage_policy = ModelChoiceFieldForImport(
        queryset=UsagePolicy.objects.none(),
        required=False,
        help_text=get_help_text(Subcomponent, "usage_policy"),
        identifier_field="label",
    )

    class Meta:
        model = Subcomponent
        exclude = [
            "licenses",
        ]

    def pre_process_form(self, data, **kwargs):
        instance = kwargs.pop("instance", None)
        self.prefix = kwargs.get("prefix")
        parent = data.get(self.add_prefix("parent"))
        child = data.get(self.add_prefix("child"))

        try:
            parent_name, parent_version = self.get_name_version(parent)
            child_name, child_version = self.get_name_version(child)
            parent = Component.objects.scope(self.dataspace).get(
                name=parent_name, version=parent_version
            )
            child = Component.objects.scope(self.dataspace).get(
                name=child_name, version=child_version
            )
        except (models.ObjectDoesNotExist, forms.ValidationError):
            parent = None
            child = None

        # No instance given, let's find a possible matching Subcomponent
        if not instance and (parent and child):
            try:
                instance = Subcomponent.objects.get(
                    parent=parent,
                    child=child,
                    dataspace=self.dataspace,
                )
            except Subcomponent.DoesNotExist:
                pass

        return data, instance

    def clean_parent(self):
        return self._clean_name_version_related_field("parent", Component)

    def clean_child(self):
        return self._clean_name_version_related_field("child", Component)


class SubcomponentImporter(BaseImporter):
    model_form = SubcomponentImportForm
