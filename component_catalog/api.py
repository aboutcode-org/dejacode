#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import defaultdict

from django.db import transaction
from django.forms.widgets import HiddenInput

import coreapi
import coreschema
import django_filters
from packageurl.contrib import url2purl
from packageurl.contrib.django.filters import PackageURLFilter
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.fields import ListField
from rest_framework.response import Response
from rest_framework.schemas import AutoSchema

from component_catalog.admin import ComponentAdmin
from component_catalog.admin import PackageAdmin
from component_catalog.filters import IsVulnerableFilter
from component_catalog.fuzzy import FuzzyPackageNameSearch
from component_catalog.license_expression_dje import get_license_objects
from component_catalog.license_expression_dje import normalize_and_validate_expression
from component_catalog.models import Component
from component_catalog.models import ComponentKeyword
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from dejacode_toolkit.download import DataCollectionException
from dejacode_toolkit.download import collect_package_data
from dejacode_toolkit.scancodeio import ScanCodeIO
from dje import tasks
from dje.api import AboutCodeFilesActionMixin
from dje.api import CreateRetrieveUpdateListViewSet
from dje.api import CycloneDXSOMActionMixin
from dje.api import DataspacedAPIFilterSet
from dje.api import DataspacedHyperlinkedRelatedField
from dje.api import DataspacedSerializer
from dje.api import DataspacedSlugRelatedField
from dje.api import ExternalReferenceSerializer
from dje.api import NameVersionHyperlinkedRelatedField
from dje.api import SPDXDocumentActionMixin
from dje.filters import LastModifiedDateFilter
from dje.filters import MultipleCharFilter
from dje.filters import MultipleUUIDFilter
from dje.filters import NameVersionFilter
from dje.models import History
from dje.models import external_references_prefetch
from dje.views import SendAboutFilesMixin
from license_library.models import License
from organization.api import OwnerEmbeddedSerializer


class LicenseSummaryMixin:
    def get_licenses_summary(self, obj):
        licenses = obj.licenses.all()
        primary_license = obj.primary_license

        return [
            {
                "key": license.key,
                "short_name": license.short_name,
                "name": license.name,
                "category": license.category.label if license.category else None,
                "type": license.category.license_type if license.category else None,
                "is_primary": bool(len(licenses) == 1 or license.key == primary_license),
            }
            for license in licenses
        ]


class ValidateLicenseExpressionMixin:
    def validate_license_expression(self, value):
        """
        Validate and return a normalized license expression string.
        Raise a Django ValidationError exception on errors.
        The expression is validated against all the dataspace licenses.
        """
        if not value:
            return value  # Prevent from converting empty string '' into `None`

        licenses = License.objects.scope(self.dataspace).for_expression()
        return normalize_and_validate_expression(
            value, licenses, validate_known=True, include_available=False
        )


class LicenseChoicesExpressionMixin:
    def get_license_choices_expression(self, obj):
        if obj.has_license_choices:
            return obj.license_choices_expression

    def get_license_choices(self, obj):
        if not obj.has_license_choices:
            return []

        all_licenses = License.objects.scope(obj.dataspace)
        choice_licenses = get_license_objects(obj.license_choices_expression, all_licenses)

        return [
            {"key": license.key, "short_name": license.short_name} for license in choice_licenses
        ]


class PackageEmbeddedSerializer(DataspacedSerializer):
    """
    Warning: Ideally, we should extend from `PackageSerializer` to avoid
    code duplication, but we cannot here because of circular import issues.
    """

    absolute_url = serializers.SerializerMethodField()

    class Meta:
        model = Package
        fields = (
            "api_url",
            "absolute_url",
            "download_url",
            "uuid",
            "filename",
            "md5",
            "sha1",
            "sha256",
            "sha512",
            "size",
            "release_date",
            "primary_language",
            "cpe",
            "description",
            "keywords",
            "project",
            "notes",
            "dependencies",
            "copyright",
            "holder",
            "author",
            "license_expression",
            "declared_license_expression",
            "other_license_expression",
            "reference_notes",
            "homepage_url",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "repository_homepage_url",
            "repository_download_url",
            "api_data_url",
            "notice_text",
            "package_url",
            "type",
            "namespace",
            "name",
            "version",
            "qualifiers",
            "subpath",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:package-detail",
                "lookup_field": "uuid",
            },
        }


class KeywordsField(ListField):
    """Create the provided Keyword value if non existing."""

    def create_missing_keywords(self, keywords):
        user = self.context["request"].user
        dataspace = user.dataspace

        qs = ComponentKeyword.objects.scope(dataspace).filter(label__in=keywords)
        existing_labels = qs.values_list("label", flat=True)

        for label in keywords:
            if label not in existing_labels:
                keyword = ComponentKeyword.objects.create(
                    label=label,
                    dataspace=dataspace,
                )
                History.log_addition(user, keyword)

    def run_child_validation(self, data):
        result = super().run_child_validation(data)
        if result:
            result = [value for value in result if value != ""]  # Clean empty string
            self.create_missing_keywords(keywords=result)
        return result


class ComponentSerializer(
    LicenseSummaryMixin,
    LicenseChoicesExpressionMixin,
    ValidateLicenseExpressionMixin,
    DataspacedSerializer,
):
    display_name = serializers.ReadOnlyField(source="__str__")
    absolute_url = serializers.SerializerMethodField()
    owner = DataspacedHyperlinkedRelatedField(
        view_name="api_v2:owner-detail",
        lookup_field="uuid",
        allow_null=True,
        required=False,
        html_cutoff=10,
        slug_field="name",
    )
    owner_name = serializers.SerializerMethodField()
    owner_abcd = OwnerEmbeddedSerializer(
        source="owner",
        read_only=True,
    )
    type = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
    )
    configuration_status = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
    )
    usage_policy = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
        scope_content_type=True,
    )
    keywords = KeywordsField(
        required=False,
    )
    packages = DataspacedHyperlinkedRelatedField(
        many=True,
        view_name="api_v2:package-detail",
        lookup_field="uuid",
        required=False,
        slug_field="uuid",
    )
    packages_abcd = PackageEmbeddedSerializer(
        source="packages",
        many=True,
        read_only=True,
    )
    external_references = ExternalReferenceSerializer(
        many=True,
        read_only=True,
    )
    licenses_summary = serializers.SerializerMethodField(source="get_licenses_summary")
    license_choices_expression = serializers.SerializerMethodField(
        source="get_license_choices_expression"
    )
    license_choices = serializers.SerializerMethodField(source="get_license_choices")

    class Meta:
        model = Component
        fields = (
            "display_name",
            "api_url",
            "absolute_url",
            "id",
            "uuid",
            "name",
            "version",
            "owner",
            "owner_name",
            "owner_abcd",
            "copyright",
            "holder",
            "license_expression",
            "reference_notes",
            "release_date",
            "description",
            "homepage_url",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "primary_language",
            "cpe",
            "project",
            "codescan_identifier",
            "type",
            "notice_text",
            "is_license_notice",
            "is_copyright_notice",
            "is_notice_in_codebase",
            "notice_filename",
            "notice_url",
            "website_terms_of_use",
            "dependencies",
            "configuration_status",
            "is_active",
            "usage_policy",
            "curation_level",
            "completion_level",
            "guidance",
            "admin_notes",
            "keywords",
            "packages",
            "packages_abcd",
            "external_references",
            "ip_sensitivity_approved",
            "affiliate_obligations",
            "affiliate_obligation_triggers",
            "legal_comments",
            "sublicense_allowed",
            "express_patent_grant",
            "covenant_not_to_assert",
            "indemnification",
            "legal_reviewed",
            "approval_reference",
            "distribution_formats_allowed",
            "acceptable_linkages",
            "export_restrictions",
            "approved_download_location",
            "approved_community_interaction",
            "urn",
            "licenses",
            "licenses_summary",
            "license_choices_expression",
            "license_choices",
            "declared_license_expression",
            "other_license_expression",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            # The `default` value set on the model field is not accounted by DRF
            # https://github.com/encode/django-rest-framework/issues/7469
            "is_active": {"default": True},
            "api_url": {
                "view_name": "api_v2:component-detail",
                "lookup_field": "uuid",
            },
            "owner": {
                "view_name": "api_v2:owner-detail",
                "lookup_field": "uuid",
            },
            "licenses": {
                "view_name": "api_v2:license-detail",
                "lookup_field": "uuid",
            },
            "packages": {
                "view_name": "api_v2:package-detail",
                "lookup_field": "uuid",
            },
        }

    def get_fields(self):
        fields = super().get_fields()
        if "completion_level" in fields:
            fields["completion_level"].read_only = True
        return fields

    def save(self, **kwargs):
        instance = super().save(**kwargs)
        instance.update_completion_level()
        return instance

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.name


class ComponentFilterSet(DataspacedAPIFilterSet):
    id = django_filters.NumberFilter(
        help_text="Exact id.",
    )
    uuid = MultipleUUIDFilter()
    name = MultipleCharFilter(
        help_text="Exact name. Multi-value supported.",
    )
    version = django_filters.CharFilter(
        help_text="Exact version.",
    )
    version__lt = django_filters.CharFilter(
        field_name="version",
        lookup_expr="lt",
        help_text="Version is lower than.",
    )
    version__gt = django_filters.CharFilter(
        field_name="version",
        lookup_expr="gt",
        help_text="Version is greater than.",
    )
    primary_language = django_filters.CharFilter(
        help_text="Exact primary language.",
    )
    project = django_filters.CharFilter(
        help_text="Exact project.",
    )
    owner = MultipleCharFilter(
        field_name="owner__name",
        help_text="Exact owner name. Multi-value supported.",
    )
    type = django_filters.CharFilter(
        field_name="type__label",
        help_text="Exact type label.",
    )
    configuration_status = django_filters.CharFilter(
        field_name="configuration_status__label",
        help_text="Exact configuration status label.",
    )
    usage_policy = django_filters.CharFilter(
        field_name="usage_policy__label",
        help_text="Exact usage policy label.",
    )
    curation_level = django_filters.NumberFilter(
        lookup_expr="gte",
        help_text="Curation level is greater than or equal to",
    )
    license_expression = django_filters.CharFilter(
        lookup_expr="icontains",
        help_text="License expression contains (case-insensitive).",
    )
    keywords = django_filters.CharFilter(
        lookup_expr="icontains",
        help_text="Keyword label contains (case-insensitive)",
    )
    last_modified_date = LastModifiedDateFilter()
    name_version = NameVersionFilter(
        label="Name:Version",
    )
    is_vulnerable = IsVulnerableFilter(
        field_name="affected_by_vulnerabilities",
    )
    affected_by = django_filters.CharFilter(
        field_name="affected_by_vulnerabilities__vulnerability_id",
        label="Affected by (vulnerability_id)",
    )

    class Meta:
        model = Component
        fields = (
            # id is required for the add_to_product and license_expression builder features
            "id",
            "uuid",
            "name",
            "version",
            "version__lt",
            "version__gt",
            "primary_language",
            "project",
            "owner",
            "type",
            "configuration_status",
            "usage_policy",
            "license_expression",
            "is_active",
            "legal_reviewed",
            "curation_level",
            "last_modified_date",
            "name_version",
            "keywords",
            "is_vulnerable",
            "affected_by",
        )


class ComponentViewSet(
    SPDXDocumentActionMixin, CycloneDXSOMActionMixin, CreateRetrieveUpdateListViewSet
):
    queryset = Component.objects.all()
    serializer_class = ComponentSerializer
    filterset_class = ComponentFilterSet
    lookup_field = "uuid"
    search_fields = (
        "name",
        "version",
        "copyright",
        "homepage_url",
        "project",
    )
    search_fields_autocomplete = (
        "name",
        "version",
    )
    ordering_fields = (
        "name",
        "version",
        "copyright",
        "license_expression",
        "primary_language",
        "project",
        "codescan_identifier",
        "type",
        "configuration_status",
        "usage_policy",
        "curation_level",
        "completion_level",
        "created_date",
        "last_modified_date",
    )
    email_notification_on = ComponentAdmin.email_notification_on
    allow_reference_access = True

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "type",
                "owner__dataspace",
                "configuration_status",
            )
            .prefetch_related(
                "licenses__category",
                "packages",
                external_references_prefetch,
            )
        )


class ComponentEmbeddedSerializer(ComponentSerializer):
    """
    All Component fields without the relation ones,
    except for Owner that is included in PackageViewSet.queryset
    prefetch_related for this purpose.
    """

    class Meta(ComponentSerializer.Meta):
        fields = (
            "display_name",
            "api_url",
            "absolute_url",
            "uuid",
            "name",
            "version",
            "owner",
            "owner_name",
            "copyright",
            "holder",
            "license_expression",
            "declared_license_expression",
            "other_license_expression",
            "reference_notes",
            "release_date",
            "description",
            "homepage_url",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "primary_language",
            "cpe",
            "project",
            "codescan_identifier",
            "notice_text",
            "is_license_notice",
            "is_copyright_notice",
            "is_notice_in_codebase",
            "notice_filename",
            "notice_url",
            "website_terms_of_use",
            "dependencies",
            "is_active",
            "curation_level",
            "completion_level",
            "guidance",
            "admin_notes",
            "ip_sensitivity_approved",
            "affiliate_obligations",
            "affiliate_obligation_triggers",
            "legal_comments",
            "sublicense_allowed",
            "express_patent_grant",
            "covenant_not_to_assert",
            "indemnification",
            "legal_reviewed",
            "approval_reference",
            "distribution_formats_allowed",
            "acceptable_linkages",
            "export_restrictions",
            "approved_download_location",
            "approved_community_interaction",
            "urn",
            "created_date",
            "last_modified_date",
        )


class PackageSerializer(
    LicenseSummaryMixin,
    ValidateLicenseExpressionMixin,
    LicenseChoicesExpressionMixin,
    DataspacedSerializer,
):
    display_name = serializers.ReadOnlyField(source="__str__")
    absolute_url = serializers.SerializerMethodField()
    components = ComponentEmbeddedSerializer(
        source="component_set",
        many=True,
        read_only=True,
    )
    external_references = ExternalReferenceSerializer(
        many=True,
        read_only=True,
    )
    keywords = KeywordsField(
        required=False,
    )
    licenses_summary = serializers.SerializerMethodField(source="get_licenses_summary")
    license_choices_expression = serializers.SerializerMethodField(
        source="get_license_choices_expression"
    )
    license_choices = serializers.SerializerMethodField(source="get_license_choices")
    usage_policy = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
        scope_content_type=True,
    )
    collect_data = serializers.BooleanField(
        write_only=True,
        required=False,
        allow_null=True,
    )
    affected_by_vulnerabilities = serializers.SerializerMethodField()

    class Meta:
        model = Package
        fields = (
            "display_name",
            "api_url",
            "absolute_url",
            "id",
            "download_url",
            "uuid",
            "filename",
            "md5",
            "sha1",
            "sha256",
            "sha512",
            "size",
            "release_date",
            "primary_language",
            "cpe",
            "description",
            "keywords",
            "project",
            "notes",
            "usage_policy",
            "dependencies",
            "copyright",
            "holder",
            "author",
            "license_expression",
            "licenses",
            "licenses_summary",
            "license_choices_expression",
            "license_choices",
            "declared_license_expression",
            "other_license_expression",
            "reference_notes",
            "homepage_url",
            "vcs_url",
            "code_view_url",
            "bug_tracking_url",
            "repository_homepage_url",
            "repository_download_url",
            "api_data_url",
            "notice_text",
            "components",
            "package_url",
            "type",
            "namespace",
            "name",
            "version",
            "qualifiers",
            "subpath",
            "parties",
            "datasource_id",
            "file_references",
            "external_references",
            "created_date",
            "last_modified_date",
            "collect_data",
            "affected_by_vulnerabilities",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:package-detail",
                "lookup_field": "uuid",
            },
            "licenses": {
                "view_name": "api_v2:license-detail",
                "lookup_field": "uuid",
            },
            "affected_by_vulnerabilities": {
                "view_name": "api_v2:vulnerability-detail",
                "lookup_field": "uuid",
            },
        }
        exclude_from_validate = [
            "collect_data",
        ]

    def get_affected_by_vulnerabilities(self, obj):
        # Using a SerializerMethodField to workaround circular imports
        from vulnerabilities.api import VulnerabilitySerializer

        vulnerabilities = obj.affected_by_vulnerabilities.all()
        fields = [
            "vulnerability_id",
            "api_url",
            "uuid",
        ]
        return VulnerabilitySerializer(
            vulnerabilities, many=True, context=self.context, fields=fields
        ).data

    def create(self, validated_data):
        """Collect data, purl, and submit scan if `collect_data` is provided."""
        user = self.context["request"].user
        dataspace = user.dataspace

        collect_data = validated_data.pop("collect_data", None)
        download_url = validated_data.get("download_url")

        if collect_data and download_url:
            try:
                collected_data = collect_package_data(download_url)
            except DataCollectionException:
                collected_data = {}

            package_url = url2purl.get_purl(download_url)
            if package_url:
                collected_data.update(package_url.to_dict(encode=True, empty=""))

            validated_data.update(collected_data)

        package = super().create(validated_data)

        # Submit the scan if Package was properly created
        scancodeio = ScanCodeIO(dataspace)
        if scancodeio.is_configured() and dataspace.enable_package_scanning:
            # Ensure the task is executed after the transaction is successfully committed
            transaction.on_commit(
                lambda: tasks.scancodeio_submit_scan.delay(
                    uris=download_url,
                    user_uuid=user.uuid,
                    dataspace_uuid=dataspace.uuid,
                )
            )

        return package


class PackageAPIFilterSet(DataspacedAPIFilterSet):
    id = django_filters.NumberFilter(
        help_text="Exact id.",
    )
    uuid = MultipleUUIDFilter()
    download_url = django_filters.CharFilter(
        help_text="Exact Download URL.",
    )
    filename = MultipleCharFilter(
        help_text="Exact filename. Multi-value supported.",
    )
    type = django_filters.CharFilter(
        lookup_expr="iexact",
        help_text="Exact type. (case-insensitive)",
    )
    namespace = django_filters.CharFilter(
        lookup_expr="iexact",
        help_text="Exact namespace. (case-insensitive)",
    )
    name = MultipleCharFilter(
        lookup_expr="iexact",
        help_text="Exact name. Multi-value supported. (case-insensitive)",
    )
    version = MultipleCharFilter(
        help_text="Exact version. Multi-value supported.",
    )
    md5 = MultipleCharFilter(
        help_text="Exact MD5. Multi-value supported.",
    )
    sha1 = MultipleCharFilter(
        help_text="Exact SHA1. Multi-value supported.",
    )
    size = django_filters.NumberFilter(
        help_text="Exact size in bytes.",
    )
    primary_language = django_filters.CharFilter(
        help_text="Exact primary language.",
    )
    license_expression = django_filters.CharFilter(
        lookup_expr="icontains",
        help_text="License expression contains (case-insensitive).",
    )
    keywords = django_filters.CharFilter(
        lookup_expr="icontains",
        help_text="Keyword label contains (case-insensitive)",
    )
    project = django_filters.CharFilter(
        help_text="Exact project.",
    )
    usage_policy = django_filters.CharFilter(
        field_name="usage_policy__label",
        help_text="Exact usage policy label.",
    )
    last_modified_date = LastModifiedDateFilter()
    fuzzy = FuzzyPackageNameSearch(widget=HiddenInput)
    purl = PackageURLFilter(label="Package URL")
    is_vulnerable = IsVulnerableFilter(
        field_name="affected_by_vulnerabilities",
    )
    affected_by = django_filters.CharFilter(
        field_name="affected_by_vulnerabilities__vulnerability_id",
        label="Affected by (vulnerability_id)",
    )

    class Meta:
        model = Package
        fields = (
            # id is required for the add_to_product and license_expression builder features
            "id",
            "uuid",
            "download_url",
            "filename",
            "type",
            "namespace",
            "name",
            "version",
            "sha1",
            "md5",
            "size",
            "primary_language",
            "keywords",
            "project",
            "license_expression",
            "usage_policy",
            "last_modified_date",
            "fuzzy",
            "purl",
            "is_vulnerable",
            "affected_by",
        )


def collect_create_scan(download_url, user):
    dataspace = user.dataspace
    package_qs = Package.objects.filter(download_url=download_url, dataspace=dataspace)
    if package_qs.exists():
        return False

    try:
        package_data = collect_package_data(download_url)
    except DataCollectionException:
        return False

    package_url = url2purl.get_purl(download_url)
    if package_url:
        package_data.update(package_url.to_dict(encode=True, empty=""))

    package = Package.create_from_data(user, package_data)

    scancodeio = ScanCodeIO(dataspace)
    if scancodeio.is_configured() and dataspace.enable_package_scanning:
        tasks.scancodeio_submit_scan.delay(
            uris=download_url,
            user_uuid=user.uuid,
            dataspace_uuid=dataspace.uuid,
        )

    return package


class PackageViewSet(
    SendAboutFilesMixin,
    AboutCodeFilesActionMixin,
    SPDXDocumentActionMixin,
    CycloneDXSOMActionMixin,
    CreateRetrieveUpdateListViewSet,
):
    queryset = Package.objects.all()
    serializer_class = PackageSerializer
    filterset_class = PackageAPIFilterSet
    lookup_field = "uuid"
    search_fields = (
        "filename",
        "project",
    )
    search_fields_autocomplete = (
        "type",
        "namespace",
        "name",
        "version",
        "filename",
    )
    ordering_fields = (
        "download_url",
        "filename",
        "size",
        "release_date",
        "primary_language",
        "project",
        "copyright",
        "license_expression",
        "usage_policy",
        "created_date",
        "last_modified_date",
    )
    email_notification_on = PackageAdmin.email_notification_on
    allow_reference_access = True

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related(
                "component_set__owner",
                "licenses__category",
                "affected_by_vulnerabilities",
                external_references_prefetch,
            )
        )

    @action(detail=True)
    def about(self, request, uuid):
        package = self.get_object()
        return Response({"about_data": package.as_about_yaml()})

    download_url_description = (
        "A single, or list of, Download URL(s).<br><br>"
        '<b>cURL style</b>: <code>-d "download_url=url1&download_url=url2"</code><br><br>'
        '<b>Python</b>: <code>data = {"download_url": ["url1", "url2"]}</code>'
    )

    add_action_schema = AutoSchema(
        manual_fields=[
            coreapi.Field(
                "download_url",
                required=True,
                location="body",
                schema=coreschema.String(description=download_url_description),
            ),
        ]
    )

    @action(detail=False, methods=["post"], name="Package Add", schema=add_action_schema)
    def add(self, request):
        """
        Alternative way to add a package providing only its `download_url`.

        Multiple URLs can be submitted through a single request.

        Note that this feature is intended only for publicly available open
        source packages, not your private code.

        DejaCode will automatically collect the `filename`, `sha1`, `md5`, and
        `size` and apply them to the package definition.
        The `package_url` will also be generated when possible.

        If package scanning is enabled in your dataspace, DejaCode will also
        submit the package to ScanCode.io and the results will be returned to
        the "Scan" detail tab of the package when that scan is complete.
        """
        download_urls = request.POST.getlist("download_url")
        if not download_urls:
            error = {"download_url": "This field is required."}
            return Response(error, status=400)

        results = defaultdict(list)
        for url in download_urls:
            url = url.strip()
            package = collect_create_scan(url, request.user)
            if package:
                results["added"].append(url)
            else:
                results["failed"].append(url)

        return Response(results)


class SubcomponentSerializer(
    ValidateLicenseExpressionMixin,
    DataspacedSerializer,
):
    parent = NameVersionHyperlinkedRelatedField(
        view_name="api_v2:component-detail",
        lookup_field="uuid",
        allow_null=False,
    )
    child = NameVersionHyperlinkedRelatedField(
        view_name="api_v2:component-detail",
        lookup_field="uuid",
        allow_null=False,
    )
    usage_policy = DataspacedSlugRelatedField(
        slug_field="label",
        allow_null=True,
        required=False,
        scope_content_type=True,
    )

    class Meta:
        model = Subcomponent
        fields = (
            "api_url",
            "uuid",
            "parent",
            "child",
            "license_expression",
            "reference_notes",
            "usage_policy",
            "purpose",
            "notes",
            "is_deployed",
            "is_modified",
            "extra_attribution_text",
            "package_paths",
            "created_date",
            "last_modified_date",
        )
        extra_kwargs = {
            # The `default` value set on the model field is not accounted by DRF
            # https://github.com/encode/django-rest-framework/issues/7469
            "is_deployed": {"default": True},
            "api_url": {
                "view_name": "api_v2:subcomponent-detail",
                "lookup_field": "uuid",
            },
            "component": {
                "view_name": "api_v2:component-detail",
                "lookup_field": "uuid",
            },
        }


class SubcomponentFilterSet(DataspacedAPIFilterSet):
    uuid = MultipleUUIDFilter()
    parent = NameVersionFilter(
        name_field_name="parent__name",
        version_field_name="parent__version",
    )
    child = NameVersionFilter(
        name_field_name="child__name",
        version_field_name="child__version",
    )
    last_modified_date = LastModifiedDateFilter()

    class Meta:
        model = Subcomponent
        fields = (
            "uuid",
            "parent",
            "child",
            "last_modified_date",
        )


class SubcomponentViewSet(CreateRetrieveUpdateListViewSet):
    queryset = Subcomponent.objects.all()
    serializer_class = SubcomponentSerializer
    filterset_class = SubcomponentFilterSet
    lookup_field = "uuid"
    search_fields = ("notes",)
    ordering_fields = (
        "license_expression",
        "created_date",
        "last_modified_date",
    )

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "parent",
                "child",
            )
        )


class KeywordSerializer(DataspacedSerializer):
    class Meta:
        model = ComponentKeyword
        fields = (
            "api_url",
            "uuid",
            "label",
            "description",
        )
        extra_kwargs = {
            "api_url": {
                "view_name": "api_v2:componentkeyword-detail",
                "lookup_field": "uuid",
            },
        }


class KeywordViewSet(CreateRetrieveUpdateListViewSet):
    queryset = ComponentKeyword.objects.all()
    serializer_class = KeywordSerializer
    lookup_field = "uuid"
    search_fields = (
        "label",
        "description",
    )
    search_fields_autocomplete = ("label",)
    ordering_fields = (
        "label",
        "created_date",
        "last_modified_date",
    )
    allow_reference_access = True
