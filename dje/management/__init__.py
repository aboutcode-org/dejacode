#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.db.models import Q

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
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseChoice
from license_library.models import LicenseProfile
from license_library.models import LicenseProfileAssignedTag
from license_library.models import LicenseStatus
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from license_library.models import LicenseTagGroup
from license_library.models import LicenseTagGroupAssignedTag
from organization.models import Owner
from organization.models import Subowner
from policy.models import AssociatedPolicy
from policy.models import UsagePolicy
from product_portfolio.models import CodebaseResource
from product_portfolio.models import CodebaseResourceUsage
from product_portfolio.models import Product
from product_portfolio.models import ProductAssignedLicense
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductComponentAssignedLicense
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductPackageAssignedLicense
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductStatus
from reporting.models import Card
from reporting.models import CardLayout
from reporting.models import ColumnTemplate
from reporting.models import ColumnTemplateAssignedField
from reporting.models import Filter
from reporting.models import LayoutAssignedCard
from reporting.models import OrderField
from reporting.models import Query
from reporting.models import Report
from workflow.models import Priority
from workflow.models import Question
from workflow.models import Request
from workflow.models import RequestComment
from workflow.models import RequestTemplate

ORGANIZATION_MODELS = [
    Owner,
    Subowner,
]

LICENSE_LIBRARY_MODELS = [
    LicenseCategory,
    LicenseTag,
    LicenseProfile,
    LicenseProfileAssignedTag,
    LicenseStyle,
    LicenseStatus,
    LicenseTagGroup,
    LicenseTagGroupAssignedTag,
    License,
    LicenseAssignedTag,
    LicenseAnnotation,
    LicenseChoice,
]

COMPONENT_CATALOG_MODELS = [
    ComponentType,
    ComponentStatus,
    Component,
    Subcomponent,
    ComponentAssignedLicense,
    SubcomponentAssignedLicense,
    ComponentKeyword,
    Package,
    ComponentAssignedPackage,
    PackageAssignedLicense,
    AcceptableLinkage,
]

PRODUCT_PORTFOLIO_MODELS = [
    ProductStatus,
    Product,
    ProductRelationStatus,
    ProductItemPurpose,
    ProductComponent,
    ProductPackage,
    ProductAssignedLicense,
    ProductComponentAssignedLicense,
    ProductPackageAssignedLicense,
    CodebaseResource,
    CodebaseResourceUsage,
]

ALL_MODELS_NO_PP = ORGANIZATION_MODELS + \
    LICENSE_LIBRARY_MODELS + COMPONENT_CATALOG_MODELS

ALL_MODELS = ALL_MODELS_NO_PP + PRODUCT_PORTFOLIO_MODELS

WORKFLOW_MODELS = [
    Priority,
    RequestTemplate,
    Question,
    Request,
    RequestComment,
]

REPORTING_MODELS = [
    Query,
    Filter,
    OrderField,
    ColumnTemplate,
    ColumnTemplateAssignedField,
    Report,
    Card,
    CardLayout,
    LayoutAssignedCard,
]

POLICY_MODELS = [
    UsagePolicy,
    AssociatedPolicy,
]


def get_component_limited_qs(dataspace):
    """
    Return a limited set of Components based on quality filters.
    The current filters return about 30k Components on the reference Dataspace.

    WARNING: Relaxing those filters to include more Components will start to be
    problematic for the fixtures system.
    In the Components case, the total number of object entries in the fixtures
    is about 10 times the number of Components once all related objects are
    serialized.
    The Django fixtures system is not made to support such large number of
    items and may not be able to properly load the fixtures.
    We should not push the number of Components returned by this over 50k at the
    maximum.
    """
    return (
        Component.objects.scope(dataspace)
        .filter(
            completion_level__gte=55,
        )
        .exclude(
            Q(version__exact="")
            | Q(description__exact="")
            | Q(primary_language__exact="")
            | Q(owner__isnull=True)
            | Q(type__isnull=True)
            | Q(licenses__isnull=True)
            | Q(keywords__isnull=True)
        )
        .select_related(
            "type__dataspace",
            "owner__dataspace",
            "configuration_status__dataspace",
            "usage_policy",
        )
        .distinct()
    )


def get_owner_limited_qs(dataspace):
    # Using list of ids for query performance
    license_qs = License.objects.scope(dataspace)
    license_ids = list(license_qs.values_list("id", flat=True))
    component_limited_qs = get_component_limited_qs(dataspace=dataspace)
    component_ids = list(component_limited_qs.values_list("id", flat=True))
    # Using the unsecured manager since no `user` is available here
    product_qs = Product.unsecured_objects.scope(dataspace)
    product_ids = list(product_qs.values_list("id", flat=True))

    return (
        Owner.objects.scope(dataspace)
        .filter(
            Q(component__id__in=component_ids)
            | Q(license__id__in=license_ids)
            | Q(product__id__in=product_ids)
        )
        .distinct()
    )
