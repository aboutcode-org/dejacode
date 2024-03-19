#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from product_portfolio.views import AttributionView
from product_portfolio.views import LoadSBOMsView
from product_portfolio.views import ManageComponentGridView
from product_portfolio.views import ManagePackageGridView
from product_portfolio.views import ProductAddView
from product_portfolio.views import ProductDeleteView
from product_portfolio.views import ProductDetailsView
from product_portfolio.views import ProductExportCycloneDXBOMView
from product_portfolio.views import ProductExportSPDXDocumentView
from product_portfolio.views import ProductListView
from product_portfolio.views import ProductSendAboutFilesView
from product_portfolio.views import ProductTabCodebaseView
from product_portfolio.views import ProductTabImportsView
from product_portfolio.views import ProductUpdateView
from product_portfolio.views import PullProjectDataFromScanCodeIOView
from product_portfolio.views import add_customcomponent_ajax_view
from product_portfolio.views import check_package_version_ajax_view
from product_portfolio.views import edit_productrelation_ajax_view
from product_portfolio.views import import_from_scan_view
from product_portfolio.views import import_packages_from_scancodeio_view
from product_portfolio.views import license_summary_view
from product_portfolio.views import product_tree_comparison_view
from product_portfolio.views import scan_all_packages_view
from product_portfolio.views import scancodeio_project_status_view

# WARNING: For views that takes a Product instance in the URL, we need
# 2 patterns to support Product with and without version, as the version
# field is optional.


def product_path(path_segment, view):
    return [
        path(
            f"<str:dataspace>/<str:name>/<str:version>/{path_segment}/",
            view,
            name=f"product_{path_segment}",
        ),
        path(
            f"<str:dataspace>/<str:name>/{path_segment}/",
            view,
            name=f"product_{path_segment}",
        ),
    ]


urlpatterns = [
    path(
        "import_packages_from_scancodeio/<str:key>/",
        import_packages_from_scancodeio_view,
        name="import_packages_from_scancodeio",
    ),
    path(
        "scancodeio_project_status/<uuid:scancodeproject_uuid>/",
        scancodeio_project_status_view,
        name="scancodeio_project_status",
    ),
    path(
        "compare/<uuid:left_uuid>/<uuid:right_uuid>/",
        product_tree_comparison_view,
        name="product_tree_comparison",
    ),
    path(
        "edit/<str:relation_type>/<uuid:relation_uuid>/",
        edit_productrelation_ajax_view,
        name="edit_productrelation_ajax",
    ),
    *product_path("add_customcomponent_ajax", add_customcomponent_ajax_view),
    *product_path("scan_all_packages", scan_all_packages_view),
    *product_path("about_files", ProductSendAboutFilesView.as_view()),
    *product_path("export_spdx", ProductExportSPDXDocumentView.as_view()),
    *product_path("export_cyclonedx", ProductExportCycloneDXBOMView.as_view()),
    *product_path("attribution", AttributionView.as_view()),
    *product_path("change", ProductUpdateView.as_view()),
    *product_path("delete", ProductDeleteView.as_view()),
    *product_path("import_from_scan", import_from_scan_view),
    *product_path("manage_components", ManageComponentGridView.as_view()),
    *product_path("manage_packages", ManagePackageGridView.as_view()),
    *product_path("license_summary", license_summary_view),
    *product_path("check_package_version", check_package_version_ajax_view),
    *product_path("load_sboms", LoadSBOMsView.as_view()),
    *product_path("import_manifests", LoadSBOMsView.as_view()),
    *product_path("tab_codebase", ProductTabCodebaseView.as_view()),
    *product_path("tab_imports", ProductTabImportsView.as_view()),
    *product_path("pull_project_data", PullProjectDataFromScanCodeIOView.as_view()),
    path(
        "<str:dataspace>/<str:name>/<str:version>/",
        ProductDetailsView.as_view(),
        name="product_details",
    ),
    path(
        "<str:dataspace>/<str:name>/",
        ProductDetailsView.as_view(),
        name="product_details",
    ),
    path(
        "add/",
        ProductAddView.as_view(),
        name="product_add",
    ),
    path(
        "",
        ProductListView.as_view(),
        name="product_list",
    ),
]
