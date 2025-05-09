#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.urls import path

from product_portfolio.views import AttributionView
from product_portfolio.views import ImportManifestsView
from product_portfolio.views import LoadSBOMsView
from product_portfolio.views import ManageComponentGridView
from product_portfolio.views import ManagePackageGridView
from product_portfolio.views import ProductAddView
from product_portfolio.views import ProductDeleteView
from product_portfolio.views import ProductDetailsView
from product_portfolio.views import ProductExportCSAFDocumentView
from product_portfolio.views import ProductExportCycloneDXBOMView
from product_portfolio.views import ProductExportSPDXDocumentView
from product_portfolio.views import ProductListView
from product_portfolio.views import ProductSendAboutFilesView
from product_portfolio.views import ProductTabCodebaseView
from product_portfolio.views import ProductTabDependenciesView
from product_portfolio.views import ProductTabImportsView
from product_portfolio.views import ProductTabInventoryView
from product_portfolio.views import ProductTabVulnerabilitiesView
from product_portfolio.views import ProductTreeComparisonView
from product_portfolio.views import ProductUpdateView
from product_portfolio.views import PullProjectDataFromScanCodeIOView
from product_portfolio.views import add_customcomponent_ajax_view
from product_portfolio.views import check_package_version_ajax_view
from product_portfolio.views import delete_scan_htmx_view
from product_portfolio.views import edit_productrelation_ajax_view
from product_portfolio.views import import_from_scan_view
from product_portfolio.views import import_packages_from_scancodeio_view
from product_portfolio.views import improve_packages_from_purldb_view
from product_portfolio.views import license_summary_view
from product_portfolio.views import scan_all_packages_view
from product_portfolio.views import scancodeio_project_download_input_view
from product_portfolio.views import scancodeio_project_status_view
from product_portfolio.views import vulnerability_analysis_form_view

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
        "scancodeio_project_download_input/<uuid:scancodeproject_uuid>/",
        scancodeio_project_download_input_view,
        name="scancodeio_project_download_input",
    ),
    path(
        "compare/<uuid:left_uuid>/<uuid:right_uuid>/",
        ProductTreeComparisonView.as_view(),
        name="product_tree_comparison",
    ),
    path(
        "edit/<str:relation_type>/<uuid:relation_uuid>/",
        edit_productrelation_ajax_view,
        name="edit_productrelation_ajax",
    ),
    path(
        "vulnerability_analysis/<uuid:productpackage_uuid>/<str:vulnerability_id>/",
        vulnerability_analysis_form_view,
        name="vulnerability_analysis_form",
    ),
    path(
        "scans/<uuid:project_uuid>/<uuid:package_uuid>/delete/",
        delete_scan_htmx_view,
        name="scan_delete_htmx",
    ),
    *product_path("add_customcomponent_ajax", add_customcomponent_ajax_view),
    *product_path("vulnerability_analysis_form", vulnerability_analysis_form_view),
    *product_path("scan_all_packages", scan_all_packages_view),
    *product_path("improve_packages_from_purldb", improve_packages_from_purldb_view),
    *product_path("about_files", ProductSendAboutFilesView.as_view()),
    *product_path("export_spdx", ProductExportSPDXDocumentView.as_view()),
    *product_path("export_cyclonedx", ProductExportCycloneDXBOMView.as_view()),
    *product_path("export_csaf", ProductExportCSAFDocumentView.as_view()),
    *product_path("attribution", AttributionView.as_view()),
    *product_path("change", ProductUpdateView.as_view()),
    *product_path("delete", ProductDeleteView.as_view()),
    *product_path("import_from_scan", import_from_scan_view),
    *product_path("manage_components", ManageComponentGridView.as_view()),
    *product_path("manage_packages", ManagePackageGridView.as_view()),
    *product_path("license_summary", license_summary_view),
    *product_path("check_package_version", check_package_version_ajax_view),
    *product_path("load_sboms", LoadSBOMsView.as_view()),
    *product_path("import_manifests", ImportManifestsView.as_view()),
    *product_path("tab_codebase", ProductTabCodebaseView.as_view()),
    *product_path("tab_dependencies", ProductTabDependenciesView.as_view()),
    *product_path("tab_vulnerabilities", ProductTabVulnerabilitiesView.as_view()),
    *product_path("tab_imports", ProductTabImportsView.as_view()),
    *product_path("tab_inventory", ProductTabInventoryView.as_view()),
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
