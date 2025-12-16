#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
from collections import defaultdict
from contextlib import suppress

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import EMPTY_VALUES
from django.db import IntegrityError
from django.db import transaction
from django.db.models import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from license_expression import Licensing
from packageurl import PackageURL

from component_catalog.importers import PackageImporter
from component_catalog.models import PACKAGE_URL_FIELDS
from component_catalog.models import Component
from component_catalog.models import Package
from dejacode_toolkit import download
from dejacode_toolkit.scancodeio import ScanCodeIO
from dje.copier import copy_object
from dje.importers import BaseImporter
from dje.importers import BaseImportModelForm
from dje.importers import BaseImportModelFormSet
from dje.importers import ComponentRelatedFieldImportMixin
from dje.importers import ModelChoiceFieldForImport
from dje.models import Dataspace
from dje.utils import get_help_text
from dje.utils import is_uuid4
from product_portfolio.forms import ProductComponentLicenseExpressionFormMixin
from product_portfolio.models import CodebaseResource
from product_portfolio.models import CodebaseResourceUsage
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductDependency
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ScanCodeProject


class CleanProductMixin(ComponentRelatedFieldImportMixin):
    def clean_product(self):
        queryset = Product.objects.get_queryset(self.user)
        return self._clean_name_version_related_field("product", Product, queryset)


class ProductRelationshipMixin(
    CleanProductMixin,
    ProductComponentLicenseExpressionFormMixin,
    BaseImportModelForm,
):
    product = forms.CharField(
        help_text=_(
            '"<name>:<version>" of the Product as defined in DejaCode. This is required '
            "for the import process to know where you are using this Component."
        ),
    )


class ProductComponentImportForm(ProductRelationshipMixin):
    component = forms.CharField(
        required=False,
        help_text=_(
            '"<name>:<version>" of the Component as defined in the DejaCode Component '
            'Catalog. Alternatively, provide your Component Name in the "name" field, '
            'and the Component Version (if known) in the "version" field.'
        ),
    )

    review_status = ModelChoiceFieldForImport(
        queryset=ProductRelationStatus.objects.none(),
        required=False,
        help_text=get_help_text(ProductComponent, "review_status"),
        identifier_field="label",
    )

    purpose = ModelChoiceFieldForImport(
        queryset=ProductItemPurpose.objects.none(),
        required=False,
        help_text=get_help_text(ProductComponent, "purpose"),
        identifier_field="label",
    )

    class Meta:
        model = ProductComponent
        exclude = [
            "licenses",
        ]

    def pre_process_form(self, data, **kwargs):
        instance = kwargs.pop("instance", None)
        self.prefix = kwargs.get("prefix")
        product = data.get(self.add_prefix("product"))
        component = data.get(self.add_prefix("component"))

        try:
            product_name, product_version = self.get_name_version(product)
            component_name, component_version = self.get_name_version(component)
            product = Product.objects.get_queryset(self.user).get(
                name=product_name, version=product_version
            )
            component = Component.objects.scope(self.dataspace).get(
                name=component_name, version=component_version
            )
        except (ObjectDoesNotExist, forms.ValidationError):
            product = None
            component = None

        # No instance given, let's find a possible matching ProductComponent
        if not instance and product and component:
            try:
                instance = ProductComponent.objects.get(
                    product=product,
                    component=component,
                    dataspace=self.dataspace,
                )
            except ProductComponent.DoesNotExist:
                pass

        return data, instance

    def clean_component(self):
        return self._clean_name_version_related_field("component", Component)


class ProductComponentImporter(BaseImporter):
    model_form = ProductComponentImportForm


class ProductPackageImportForm(ProductRelationshipMixin):
    relation_fk_field = "package"

    package = forms.CharField(
        required=True,
        help_text=get_help_text(Package, "filename"),
    )

    review_status = ModelChoiceFieldForImport(
        queryset=ProductRelationStatus.objects.none(),
        required=False,
        help_text=get_help_text(ProductPackage, "review_status"),
        identifier_field="label",
    )

    purpose = ModelChoiceFieldForImport(
        queryset=ProductItemPurpose.objects.none(),
        required=False,
        help_text=get_help_text(ProductPackage, "purpose"),
        identifier_field="label",
    )

    class Meta:
        model = ProductPackage
        exclude = [
            "licenses",
        ]

    def get_package(self, filename_or_uuid):
        field = "uuid" if is_uuid4(filename_or_uuid) else "filename"

        return Package.objects.scope(self.dataspace).get(**{field: filename_or_uuid})

    def pre_process_form(self, data, **kwargs):
        instance = kwargs.pop("instance", None)
        self.prefix = kwargs.get("prefix")
        product = data.get(self.add_prefix("product"))
        package = data.get(self.add_prefix("package"))

        try:
            product_name, product_version = self.get_name_version(product)
            product = Product.objects.get_queryset(self.user).get(
                name=product_name, version=product_version
            )
            package = self.get_package(package)
        except (ObjectDoesNotExist, Package.MultipleObjectsReturned, forms.ValidationError):
            product = None
            package = None

        # No instance given, let's find a possible matching ProductPackage
        if not instance and product and package:
            try:
                instance = ProductPackage.objects.get(
                    product=product,
                    package=package,
                    dataspace=self.dataspace,
                )
            except ProductPackage.DoesNotExist:
                pass

        return data, instance

    def clean_package(self):
        filename_or_uuid = self.cleaned_data["package"]
        try:
            return self.get_package(filename_or_uuid)
        except Package.DoesNotExist:
            raise forms.ValidationError(
                f"The following package does not exists: {filename_or_uuid}"
            )
        except Package.MultipleObjectsReturned:
            raise forms.ValidationError(
                f'Multiple packages with the same "{filename_or_uuid}" filename.'
            )


class ProductPackageImporter(BaseImporter):
    model_form = ProductPackageImportForm


class CodebaseResourceImportForm(CleanProductMixin, BaseImportModelForm):
    product = forms.CharField(
        help_text=_(
            '"<name>:<version>" of the Product as defined in DejaCode. This is required '
            "for the import process to know where you are using this Component."
        ),
    )
    product_component = forms.CharField(
        required=False,
        help_text=_(
            '"<name>:<version>" of a Component currently defined as a Product Component on the '
            "Product."
        ),
    )
    product_package = forms.CharField(
        required=False,
        help_text=_(
            "The exact file name of a Package currently defined as a Product Package on the "
            "Product."
        ),
    )
    deployed_to = forms.CharField(
        required=False,
        help_text=_(
            "If path is a development codebase resource (not a deployment codebase resource), "
            "this is a  comma-separated list of path values that are currently associated with "
            "this product where is_deployment_path = True."
        ),
    )

    class Meta:
        model = CodebaseResource
        exclude = [
            "deployed_to",
        ]

    def pre_process_form(self, data, **kwargs):
        instance = kwargs.pop("instance", None)
        self.prefix = kwargs.get("prefix")
        product = data.get(self.add_prefix("product"))
        path = data.get(self.add_prefix("path"))

        # Workaround default `dict` value on the model
        additional_details = data.get(self.add_prefix("additional_details"))
        if not additional_details:
            data[self.add_prefix("additional_details")] = "{}"

        try:
            product_name, product_version = self.get_name_version(product)
            product = Product.objects.get_queryset(self.user).get(
                name=product_name, version=product_version
            )
        except (ObjectDoesNotExist, forms.ValidationError):
            product = None

        if not instance and product:  # No instance given, let's match our CodebaseResource
            try:
                instance = CodebaseResource.objects.get(
                    product=product,
                    path=path,
                    dataspace=self.dataspace,
                )
            except CodebaseResource.DoesNotExist:
                pass

        return data, instance

    def clean_product_component(self):
        product_component = self.cleaned_data["product_component"]
        if not product_component:
            return

        product = self.cleaned_data["product"]
        component_name, component_version = self.get_name_version(product_component)
        component_lookup = Q(
            component__name=component_name,
            component__version=component_version,
        )
        custom_component_lookup = Q(
            name=component_name,
            version=component_version,
        )

        try:
            return ProductComponent.objects.scope(self.dataspace).get(
                component_lookup | custom_component_lookup,
                product=product,
            )
        except ProductComponent.DoesNotExist:
            raise forms.ValidationError(
                f'The component "{product_component}" is not available on {product}'
            )
        except ProductComponent.MultipleObjectsReturned:
            raise forms.ValidationError(
                f'Multiple entries available for "{product_component}" on {product}'
            )

    def clean_product_package(self):
        filename = self.cleaned_data["product_package"]
        if not filename:
            return

        product = self.cleaned_data["product"]
        try:
            return ProductPackage.objects.scope(self.dataspace).get(
                package__filename=filename,
                product=product,
            )
        except ProductPackage.DoesNotExist:
            raise forms.ValidationError(f'The package "{filename}" is not available on {product}')

    def clean_deployed_to(self):
        deployed_to = self.cleaned_data["deployed_to"]
        self.deployed_to_paths = [path.strip() for path in deployed_to.split(",") if path.strip()]
        return deployed_to


class CodebaseResourceFormSet(BaseImportModelFormSet):
    def clean(self):
        paths = [form.cleaned_data.get("path") for form in self if form.cleaned_data.get("path")]

        for form in self:
            for deployed_to in form.deployed_to_paths:
                if deployed_to not in paths:
                    # The `path` is not in the import data, let's try to find it in the DB.
                    try:
                        CodebaseResource.objects.get(
                            path=deployed_to,
                            product=form.cleaned_data["product"],
                            dataspace=form.dataspace,
                        )
                    except CodebaseResource.DoesNotExist:
                        if "deployed_to" not in form._errors:
                            form._errors["deployed_to"] = self.error_class([])
                        form._errors["deployed_to"].append(f"Path {deployed_to} is not available.")


class CodebaseResourceImporter(BaseImporter):
    model_form = CodebaseResourceImportForm
    formset_class = CodebaseResourceFormSet

    def save_all(self):
        super().save_all()

        for form in self.formset:
            for deployed_to_path in form.deployed_to_paths:
                deployed_from = CodebaseResource.objects.get(
                    path=form.cleaned_data.get("path"),
                    product=form.cleaned_data["product"],
                    dataspace=self.dataspace,
                )
                deployed_to = CodebaseResource.objects.get(
                    path=deployed_to_path,
                    product=form.cleaned_data["product"],
                    dataspace=self.dataspace,
                )
                CodebaseResourceUsage.objects.get_or_create(
                    deployed_from=deployed_from,
                    deployed_to=deployed_to,
                    dataspace=self.dataspace,
                )


class ImportFromScan:
    def __init__(
        self, product, user, upload_file, create_codebase_resources=True, stop_on_error=False
    ):
        self.product = product
        self.dataspace = product.dataspace
        self.user = user
        self.upload_file = upload_file
        self.create_codebase_resources = create_codebase_resources
        self.stop_on_error = stop_on_error

        self.data = {}
        self.created_counts = {}
        self.warnings = []
        self.product_packages_by_id = {}
        self.scancode_project = None

        self.resource_additional_fields = [
            "programming_language",
            "detected_license_expression",
            "detected_license_expression_spdx",
            "size",
            "date",
            "mime_type",
            "file_type",
            "md5",
            "sha1",
        ]

    def save(self):
        self.create_scancode_project()
        self.load_data_from_file()
        self.validate_headers()
        self.import_packages()
        if self.create_codebase_resources:
            self.import_codebase_resources()
        self.update_scancode_project()
        return self.warnings, self.created_counts

    def load_data_from_file(self):
        try:
            with self.upload_file.open("r", encoding="utf-8") as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON file: {e}")

    def validate_headers(self):
        """
        Check the input `headers` to ensure that the provided input was generated with
        the supported tools and options.
        """
        headers = self.data.get("headers", [])
        if not headers:
            raise ValidationError("The uploaded file is not a proper ScanCode output results.")

        header = headers[0]
        tool_name = header.get("tool_name", "")

        if tool_name == "scancode-toolkit":
            scan_options = header.get("options", {}).keys()
            self.validate_toolkit_options(scan_options)

        elif tool_name == "scanpipe":
            if not (self.data.get("packages") or self.data.get("dependencies")):
                raise ValidationError(
                    "This ScanCode.io output does not include packages nor dependencies data."
                )

    @staticmethod
    def validate_toolkit_options(scan_options):
        """Raise a ValidationError if the required toolkit options were not provided."""
        required_options = [
            "--copyright",
            "--license",
            "--info",
            "--package",
        ]

        missing_options = [option for option in required_options if option not in scan_options]

        if missing_options:
            options_str = " ".join(missing_options)
            raise ValidationError(f"The Scan run is missing those required options: {options_str}")

    def import_packages(self):
        product_packages_count = 0
        packages_count = 0
        packages = self.data.get("packages", [])
        if not packages:
            raise ValidationError(
                "No detected Packages to import from the provided scan results. "
                '"packages" is empty in the uploaded json file.'
            )

        dependencies = self.data.get("dependencies", [])
        dependencies_by_package_uid = defaultdict(list)
        for dependency in dependencies:
            for_package_uid = dependency.get("for_package_uid")
            dependencies_by_package_uid[for_package_uid].append(dependency)

        for package_data in packages:
            package_uid = package_data.get("package_uid")
            package_dependencies = package_data.get("dependencies", [])
            if not package_dependencies:
                package_data["dependencies"] = dependencies_by_package_uid.get(package_uid, [])

            prepared = PackageImporter.prepare_package(package_data, path="/")
            if not prepared:
                continue

            package_url = package_data.get("purl")
            if not package_url:
                continue

            package_url = PackageURL.from_string(package_url)
            package_url_dict = package_url.to_dict(encode=True, empty="")

            try:
                package = Package.objects.get(
                    **package_url_dict,
                    filename=prepared.get("filename", ""),
                    download_url=prepared.get("download_url", ""),
                    dataspace=self.dataspace,
                )
            except ObjectDoesNotExist:
                package = None

            if not package:
                # In the context of ScanCode-Toolkit, the `license_expression` is
                # available in the `declared_license_expression` field.
                if "license_expression" not in prepared:
                    license_expression = package_data.get("declared_license_expression") or ""
                    prepared["license_expression"] = license_expression

                prepared.update(package_url_dict)
                package = Package(
                    created_by=self.user,
                    dataspace=self.dataspace,
                    **prepared,
                )

                try:
                    package.full_clean()
                except ValidationError as e:
                    # Catch the validation error raised from `validate_against_reference_data()`
                    if "Copy to my Dataspace" not in str(e):
                        msg = [
                            f"{package_uid} {field}: {','.join(messages)}"
                            for field, messages in e.message_dict.items()
                        ]
                        if self.stop_on_error:
                            raise ValidationError(msg)
                        self.warnings.extend(msg)
                        continue

                package.save()
                packages_count += 1

            pp, created = ProductPackage.objects.get_or_create(
                product=self.product,
                package=package,
                dataspace=self.dataspace,
                defaults={
                    "license_expression": package.license_expression,
                    "notes": f"Imported from {self.upload_file.name}",
                    "created_by": self.user,
                },
            )
            self.product_packages_by_id[package_uid] = pp
            if created:
                product_packages_count += 1

        if packages_count:
            self.created_counts["Packages"] = packages_count
        if product_packages_count:
            self.created_counts["Product Packages"] = product_packages_count

    def import_codebase_resources(self):
        codebase_resources_count = 0
        files = self.data.get("files", [])
        for file in files:
            for identifier in file.get("for_packages", []):
                extra = {}
                path = file.get("path")

                max_length = CodebaseResource._meta.get_field("path").max_length
                if len(path) > max_length:
                    msg = f'Path too long > {max_length} for "{path}"'
                    if self.stop_on_error:
                        raise ValidationError(msg)
                    self.warnings.extend(msg)
                    continue

                product_package = self.product_packages_by_id.get(identifier, None)
                if product_package:
                    extra["product_package"] = product_package

                if not extra:
                    continue

                additional_details = {
                    "import_source": self.upload_file.name,
                }

                for field_name in self.resource_additional_fields:
                    value = file.get(field_name)
                    if value not in EMPTY_VALUES:
                        additional_details[field_name] = value

                _, created = CodebaseResource.objects.get_or_create(
                    product=self.product,
                    path=path,
                    dataspace=self.dataspace,
                    defaults={
                        "additional_details": additional_details,
                        "created_by": self.user,
                        **extra,
                    },
                )
                if created:
                    codebase_resources_count += 1

            if codebase_resources_count:
                self.created_counts["Codebase Resources"] = codebase_resources_count

    def create_scancode_project(self):
        """Create a ScanCodeProject entry to log this import on the Product."""
        self.scancode_project = ScanCodeProject.objects.create(
            product=self.product,
            dataspace=self.product.dataspace,
            type=ScanCodeProject.ProjectType.IMPORT_SCAN_RESULTS,
            input_file=self.upload_file,
            created_by=self.user,
            status=ScanCodeProject.Status.IMPORT_STARTED,
        )

    def update_scancode_project(self):
        """Update the ScanCodeProject entry with import results."""
        if self.created_counts:
            status = ScanCodeProject.Status.SUCCESS
            import_log = [
                f"- Imported {count} {label.lower()}"
                for label, count in self.created_counts.items()
            ]
        else:
            status = ScanCodeProject.Status.WARNING
            import_log = ["Nothing imported."]

        if self.warnings:
            import_log.extend(self.warnings)

        self.scancode_project.update(
            status=status,
            import_log=import_log,
        )


class ImportPackageFromScanCodeIO:
    """
    Creates, and assign to a product, packages in Dejacode from a ScanCode.io project
    discovered packages.
    """

    unique_together_fields = [
        *PACKAGE_URL_FIELDS,
        "download_url",
        "filename",
    ]

    def __init__(
        self,
        user,
        project_uuid,
        product,
        update_existing=False,
        scan_all_packages=False,
        infer_download_urls=False,
    ):
        self.licensing = Licensing()
        self.created = defaultdict(list)
        self.existing = defaultdict(list)
        self.errors = defaultdict(list)
        # Use to assign dependencies to the correct Package instance
        self.package_uid_mapping = {}

        self.user = user
        self.project_uuid = project_uuid
        self.product = product
        self.update_existing = update_existing
        self.scan_all_packages = scan_all_packages
        self.infer_download_urls = infer_download_urls

        scancodeio = ScanCodeIO(user.dataspace)
        self.packages = scancodeio.fetch_project_packages(self.project_uuid)
        if not self.packages:
            raise Exception("Packages could not be fetched from ScanCode.io")
        self.dependencies = scancodeio.fetch_project_dependencies(self.project_uuid)

    def save(self):
        self.import_packages()
        self.import_dependencies()

        if self.scan_all_packages:
            transaction.on_commit(lambda: self.product.scan_all_packages_task(self.user))

        if self.user.dataspace.enable_vulnerablecodedb_access:
            self.product.fetch_vulnerabilities()

        return dict(self.created), dict(self.existing), dict(self.errors)

    def import_packages(self):
        for package_data in self.packages:
            self.import_package(package_data)

    def import_dependencies(self):
        for dependency_data in self.dependencies:
            self.import_dependency(dependency_data)

    def import_package(self, package_data):
        # Vulnerabilities are fetched post import.
        package_data.pop("affected_by_vulnerabilities", None)

        # Check if the package already exists to prevent duplication.
        package = self.look_for_existing_package(package_data)

        # Infer a download URL from the Package URL
        if (
            self.infer_download_urls
            and not package_data.get("download_url")
            and (purl := package_data.get("purl"))
            and (download_url := download.infer_download_url(purl))
        ):
            package_data["download_url"] = download_url

        if license_expression := package_data.get("declared_license_expression"):
            license_expression = str(self.licensing.dedup(license_expression))
            package_data["license_expression"] = license_expression

        if package and self.update_existing:
            package.update_from_data(self.user, package_data, override=False, override_unknown=True)

        if not package:
            try:
                package = Package.create_from_data(self.user, package_data, validate=True)
            except ValidationError as errors:
                self.errors["package"].append(str(errors))
                return
            self.created["package"].append(str(package))

        ProductPackage.objects.get_or_create(
            product=self.product,
            package=package,
            dataspace=self.product.dataspace,
            defaults={
                "license_expression": package.license_expression,
                "notes": "Imported from ScanCode.io",
                "created_by": self.user,
            },
        )
        package_uid = package_data.get("package_uid") or package.uuid
        self.package_uid_mapping[package_uid] = package

    def import_dependency(self, dependency_data):
        dependency_uid = dependency_data.get("dependency_uid")

        dependency_qs = self.product.dependencies.all()
        if dependency_qs.filter(dependency_uid=dependency_uid).exists():
            self.existing["dependency"].append(str(dependency_uid))
            return

        for_package = None
        resolved_to_package = None
        dependency_data["product"] = self.product
        if for_package_uid := dependency_data.get("for_package_uid"):
            for_package = self.package_uid_mapping.get(for_package_uid)
            dependency_data["for_package"] = for_package
        if resolved_to_package_uid := dependency_data.get("resolved_to_package_uid"):
            resolved_to_package = self.package_uid_mapping.get(resolved_to_package_uid)
            dependency_data["resolved_to_package"] = resolved_to_package

        # Check if the dependency entry already exists in the product.
        if for_package and resolved_to_package:
            resolved_dependency_qs = dependency_qs.filter(
                for_package=for_package,
                resolved_to_package=resolved_to_package,
            )
            if resolved_dependency_qs.exists():
                self.existing["dependency"].append(str(dependency_uid))
                return

        if purl := dependency_data.get("purl"):
            dependency_data["declared_dependency"] = purl

        try:
            dependency = ProductDependency.create_from_data(
                user=self.user,
                data=dependency_data,
                validate=True,
            )
        except ValidationError as errors:
            self.errors["dependency"].append(str(errors))
            return

        self.created["dependency"].append(str(dependency.dependency_uid))

    def look_for_existing_package(self, package_data):
        package = None
        package_qs = Package.objects.scope(self.user.dataspace)

        # 1. Check if the Package already exists in the local Dataspace
        # Using exact match first: purl + download_url + filename
        exact_match_lookups = {
            field: package_data.get(field, "") for field in self.unique_together_fields
        }
        with suppress(ObjectDoesNotExist):
            package = package_qs.get(**exact_match_lookups)
            self.existing["package"].append(str(package))
            return package

        # 2. If the package data does not include a download_url value:
        # Attemp to find an existing package using purl-only match.
        if not package_data.get("download_url"):
            purl_lookups = {field: package_data.get(field, "") for field in PACKAGE_URL_FIELDS}
            same_purl_packages = package_qs.filter(**purl_lookups)
            if len(same_purl_packages) == 1:
                package = same_purl_packages[0]
                self.existing["package"].append(str(package))
                return package

        # Check if the Package already exists in the reference Dataspace
        # Using exact match only: purl + download_url + filename
        reference_dataspace = Dataspace.objects.get_reference()
        user_dataspace = self.user.dataspace
        if not package and user_dataspace != reference_dataspace:
            qs = Package.objects.scope(reference_dataspace).filter(**exact_match_lookups)
            if qs.exists():
                reference_object = qs.first()
                try:
                    package = copy_object(reference_object, user_dataspace, self.user, update=False)
                    self.created["package"].append(str(package))
                except IntegrityError as error:
                    self.errors["package"].append(str(error))

        return package
