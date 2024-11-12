#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import csv
import json
from collections import OrderedDict
from collections import defaultdict
from collections import namedtuple
from operator import attrgetter
from urllib.parse import unquote_plus

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.db.models import F
from django.db.models import Prefetch
from django.db.models.functions import Lower
from django.forms import modelformset_factory
from django.http import Http404
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import DetailView
from django.views.generic import FormView
from django.views.generic import TemplateView

from crispy_forms.utils import render_crispy_form
from guardian.shortcuts import get_perms as guardian_get_perms
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.styles import Border
from openpyxl.styles import Font
from openpyxl.styles import NamedStyle
from openpyxl.styles import Side

from component_catalog.forms import ComponentAjaxForm
from component_catalog.license_expression_dje import build_licensing
from component_catalog.license_expression_dje import parse_expression
from component_catalog.models import Component
from component_catalog.models import Package
from dejacode_toolkit.purldb import PurlDB
from dejacode_toolkit.scancodeio import ScanCodeIO
from dejacode_toolkit.scancodeio import get_hash_uid
from dejacode_toolkit.scancodeio import get_package_download_url
from dejacode_toolkit.scancodeio import get_scan_results_as_file_url
from dejacode_toolkit.utils import sha1
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje import tasks
from dje.client_data import add_client_data
from dje.filters import BooleanChoiceFilter
from dje.filters import HasCountFilter
from dje.models import DejacodeUser
from dje.models import History
from dje.templatetags.dje_tags import urlize_target_blank
from dje.utils import chunked
from dje.utils import get_object_compare_diff
from dje.utils import group_by_simple
from dje.utils import is_uuid4
from dje.views import DataspacedCreateView
from dje.views import DataspacedDeleteView
from dje.views import DataspacedFilterView
from dje.views import DataspacedModelFormMixin
from dje.views import DataspacedUpdateView
from dje.views import DataspaceScopeMixin
from dje.views import ExportCycloneDXBOMView
from dje.views import ExportSPDXDocumentView
from dje.views import GetDataspacedObjectMixin
from dje.views import Header
from dje.views import LicenseDataForBuilderMixin
from dje.views import ObjectDetailsView
from dje.views import PreviousNextPaginationMixin
from dje.views import SendAboutFilesView
from dje.views import TabContentView
from dje.views import TabField
from dje.views import TableHeaderMixin
from dje.views_formset import FormSetView
from license_library.filters import LicenseFilterSet
from license_library.models import License
from license_library.models import LicenseAssignedTag
from product_portfolio.filters import CodebaseResourceFilterSet
from product_portfolio.filters import DependencyFilterSet
from product_portfolio.filters import ProductComponentFilterSet
from product_portfolio.filters import ProductFilterSet
from product_portfolio.filters import ProductPackageFilterSet
from product_portfolio.forms import AttributionConfigurationForm
from product_portfolio.forms import BaseProductRelationshipInlineFormSet
from product_portfolio.forms import ComparisonExcludeFieldsForm
from product_portfolio.forms import ImportFromScanForm
from product_portfolio.forms import ImportManifestsForm
from product_portfolio.forms import LoadSBOMsForm
from product_portfolio.forms import ProductComponentForm
from product_portfolio.forms import ProductComponentInlineForm
from product_portfolio.forms import ProductCustomComponentForm
from product_portfolio.forms import ProductForm
from product_portfolio.forms import ProductGridConfigurationForm
from product_portfolio.forms import ProductPackageForm
from product_portfolio.forms import ProductPackageInlineForm
from product_portfolio.forms import PullProjectDataForm
from product_portfolio.forms import TableInlineFormSetHelper
from product_portfolio.models import CodebaseResource
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductDependency
from product_portfolio.models import ProductPackage
from product_portfolio.models import ScanCodeProject
from vulnerabilities.filters import VulnerabilityFilterSet
from vulnerabilities.models import Vulnerability


class BaseProductViewMixin:
    model = Product
    slug_url_kwarg = ("name", "version")

    def get_queryset(self):
        return self.model.objects.get_queryset(
            user=self.request.user,
            perms="view_product",
        )


class ProductListView(
    LoginRequiredMixin,
    DataspacedFilterView,
):
    model = Product
    filterset_class = ProductFilterSet
    template_name = "product_portfolio/product_list.html"
    template_list_table = "product_portfolio/includes/product_list_table.html"
    paginate_by = 50
    put_results_in_session = False
    group_name_version = True
    table_headers = (
        Header("name", "Product name"),
        Header("version", "Version"),
        Header("license_expression", "License", filter="licenses"),
        Header("primary_language", "Language", filter="primary_language"),
        Header("owner", "Owner"),
        Header("configuration_status", "Status", filter="configuration_status"),
        Header("productinventoryitem_count", "Inventory", help_text="Inventory count"),
        Header("keywords", "Keywords", filter="keywords"),
    )

    def get_queryset(self):
        return (
            self.model.objects.get_queryset(
                user=self.request.user,
                perms="view_product",
            )
            .only(
                "uuid",
                "name",
                "version",
                "license_expression",
                "owner",
                "primary_language",
                "keywords",
                "configuration_status",
                "request_count",
                "dataspace",
            )
            .select_related(
                "owner",
                "configuration_status",
            )
            .prefetch_related(
                "licenses__usage_policy",
            )
            .annotate(
                productinventoryitem_count=Count("productinventoryitem"),
            )
            .order_by(
                "name",
                "version",
            )
        )

    def get_extra_add_urls(self):
        extra_add_urls = super().get_extra_add_urls()
        user = self.request.user

        if user.has_perm("product_portfolio.add_productcomponent"):
            extra_add_urls.append(
                (
                    "Import product components",
                    reverse("admin:product_portfolio_productcomponent_import"),
                )
            )
        if user.has_perm("product_portfolio.add_productpackage"):
            extra_add_urls.append(
                (
                    "Import product packages",
                    reverse("admin:product_portfolio_productpackage_import"),
                )
            )
        if user.has_perm("product_portfolio.add_codebaseresource"):
            extra_add_urls.append(
                (
                    "Import codebase resources",
                    reverse("admin:product_portfolio_codebaseresource_import"),
                )
            )

        return extra_add_urls


class ProductDetailsView(
    LoginRequiredMixin,
    BaseProductViewMixin,
    ObjectDetailsView,
):
    template_name = "product_portfolio/product_details.html"
    include_reference_dataspace = False
    show_previous_and_next_object_links = False
    tabset = {
        "essentials": {
            "fields": [
                "display_name",
                "name",
                "version",
                "owner",
                "description",
                "configuration_status",
                "copyright",
                "homepage_url",
                "keywords",
                "primary_language",
                "release_date",
                "contact",
                "vcs_url",
                "code_view_url",
                "bug_tracking_url",
                "dataspace",
            ],
        },
        "inventory": {
            "fields": [
                "components",
                "packages",
            ],
        },
        "codebase": {
            "fields": [
                "path",
                "is_deployment_path",
                "components",
                "packages",
                "deployed_from",
                "deployed_to",
            ],
        },
        "hierarchy": {
            "fields": [
                "components",
            ],
        },
        "notice": {
            "fields": [
                "notice_text",
            ],
        },
        "license": {
            "fields": [
                "license_expression",
                "licenses",
            ],
        },
        "owner": {
            "fields": [
                "owner",
            ],
        },
        "vulnerabilities": {},
        "dependencies": {
            "fields": [
                "dependencies",
            ],
        },
        "activity": {},
        "imports": {},
        "history": {
            "fields": [
                "created_date",
                "created_by",
                "last_modified_date",
                "last_modified_by",
            ],
        },
    }

    def get_queryset(self):
        licenses_prefetch = Prefetch("licenses", License.objects.select_related("usage_policy"))

        productcomponent_qs = ProductComponent.objects.select_related(
            "component__dataspace",
            "component__owner__dataspace",
            "component__usage_policy",
            "review_status",
            "purpose",
        ).prefetch_related(
            "component__packages",
            "component__children",
            licenses_prefetch,
        )

        productpackage_qs = ProductPackage.objects.select_related(
            "package__dataspace",
            "package__usage_policy",
            "review_status",
            "purpose",
        ).prefetch_related(
            licenses_prefetch,
        )

        return (
            super()
            .get_queryset()
            .select_related(
                "owner",
                "configuration_status",
            )
            .prefetch_related(
                "licenses__category",
                "licenses__usage_policy",
                "scancodeprojects",
                LicenseAssignedTag.prefetch_for_license_tab(),
                Prefetch("productcomponents", queryset=productcomponent_qs),
                Prefetch("productpackages", queryset=productpackage_qs),
            )
        )

    def get_tabsets(self):
        self.filter_productpackage = ProductPackageFilterSet(
            self.request.GET,
            queryset=self.object.productpackages,
            dataspace=self.object.dataspace,
            prefix="inventory",
            anchor="#inventory",
        )

        self.filter_productcomponent = ProductComponentFilterSet(
            self.request.GET,
            queryset=self.object.productcomponents,
            dataspace=self.object.dataspace,
            prefix="inventory",
            anchor="#inventory",
        )

        return super().get_tabsets()

    def tab_essentials(self):
        tab_fields = [
            TabField("name"),
            TabField("version"),
            TabField("owner", source="owner.get_absolute_link"),
            TabField("description"),
            TabField("configuration_status"),
            TabField("copyright"),
            TabField("homepage_url", value_func=urlize_target_blank),
            TabField("keywords", source="keywords", value_func=lambda x: "\n".join(x)),
            TabField("primary_language"),
            TabField("release_date"),
            TabField("contact"),
            TabField("vcs_url", value_func=urlize_target_blank),
            TabField("code_view_url", value_func=urlize_target_blank),
            TabField("bug_tracking_url", value_func=urlize_target_blank),
            TabField("dataspace"),
        ]

        return {"fields": self.get_tab_fields(tab_fields)}

    def tab_notice(self):
        if self.object.notice_text:
            return {"fields": self.get_tab_fields([TabField("notice_text")])}

    def tab_hierarchy(self):
        template = "product_portfolio/tabs/tab_hierarchy.html"
        product = self.object

        productcomponent_qs = (
            product.productcomponents.select_related(
                "component",
            )
            .prefetch_related(
                "component__licenses",
            )
            .annotate(
                children_count=Count("component__children"),
                vulnerability_count=Count("component__affected_by_vulnerabilities"),
            )
            .order_by(
                "feature",
                "component__name",
                "component__version",
                "name",
                "version",
            )
        )

        declared_dependencies_prefetch = Prefetch(
            "package__declared_dependencies", ProductDependency.objects.product(product)
        )

        productpackage_qs = (
            product.productpackages.select_related(
                "package",
            )
            .prefetch_related(
                "package__licenses",
                declared_dependencies_prefetch,
            )
            .annotate(
                vulnerability_count=Count("package__affected_by_vulnerabilities"),
            )
            .order_by(
                "feature",
                "package__type",
                "package__namespace",
                "package__name",
                "package__version",
                "package__filename",
            )
        )

        is_deployed = self.request.GET.get("hierarchy-is_deployed")
        if is_deployed:
            is_deployed_filter = BooleanChoiceFilter(field_name="is_deployed")
            productcomponent_qs = is_deployed_filter.filter(productcomponent_qs, is_deployed)
            productpackage_qs = is_deployed_filter.filter(productpackage_qs, is_deployed)

        is_vulnerable = self.request.GET.get("hierarchy-is_vulnerable")
        if is_vulnerable:
            is_vulnerable_filter = HasCountFilter(field_name="vulnerability")
            productcomponent_qs = is_vulnerable_filter.filter(productcomponent_qs, is_vulnerable)
            productpackage_qs = is_vulnerable_filter.filter(productpackage_qs, is_vulnerable)

        if not (productcomponent_qs or productpackage_qs or is_deployed):
            return

        relations_feature_grouped = defaultdict(list)
        for relation_qs in [productcomponent_qs, productpackage_qs]:
            for feature, relation in relation_qs.group_by("feature").items():
                relations_feature_grouped[feature].extend(relation)

        context = {
            "verbose_name": self.model._meta.verbose_name,
            "verbose_name_plural": self.model._meta.verbose_name_plural,
            "relations_feature_grouped": dict(sorted(relations_feature_grouped.items())),
            "is_deployed": is_deployed,
            "is_vulnerable": is_vulnerable,
        }

        return {"fields": [(None, context, None, template)]}

    def tab_inventory(self):
        productcomponents_count = self.object.productcomponents.count()
        productpackages_count = self.object.productpackages.count()
        inventory_count = productcomponents_count + productpackages_count
        if not inventory_count:
            return

        label = f'Inventory <span class="badge text-bg-primary">{inventory_count}</span>'
        template = "tabs/tab_async_loader.html"

        # Pass the current request query context to the async request
        tab_view_url = self.object.get_url("tab_inventory")
        if full_query_string := self.request.META["QUERY_STRING"]:
            tab_view_url += f"?{full_query_string}"

        tab_context = {
            "tab_view_url": tab_view_url,
            "tab_object_name": "inventory",
        }

        return {
            "label": format_html(label),
            "fields": [(None, tab_context, None, template)],
        }

    def tab_dependencies(self):
        dependencies_count = self.object.dependencies.count()
        if not dependencies_count:
            return

        label = f'Dependencies <span class="badge text-bg-primary">{dependencies_count}</span>'
        template = "tabs/tab_async_loader.html"

        # Pass the current request query context to the async request
        tab_view_url = self.object.get_url("tab_dependencies")
        if full_query_string := self.request.META["QUERY_STRING"]:
            tab_view_url += f"?{full_query_string}"

        tab_context = {
            "tab_view_url": tab_view_url,
            "tab_object_name": "dependencies",
        }

        return {
            "label": format_html(label),
            "fields": [(None, tab_context, None, template)],
        }

    def tab_vulnerabilities(self):
        dataspace = self.object.dataspace
        vulnerablecode = VulnerableCode(self.object.dataspace)
        display_tab_contions = [
            dataspace.enable_vulnerablecodedb_access,
            vulnerablecode.is_configured(),
        ]
        if not all(display_tab_contions):
            return

        vulnerability_qs = self.object.get_vulnerability_qs()
        vulnerability_count = vulnerability_qs.count()
        if not vulnerability_count:
            label = 'Vulnerabilities <span class="badge bg-secondary">0</span>'
            return {
                "label": format_html(label),
                "fields": [],
                "disabled": True,
                "tooltip": "No vulnerabilities found in this Product",
            }

        label = (
            f'Vulnerabilities <span class="badge badge-vulnerability">{vulnerability_count}</span>'
        )

        # Pass the current request query context to the async request
        tab_view_url = self.object.get_url("tab_vulnerabilities")
        if full_query_string := self.request.META["QUERY_STRING"]:
            tab_view_url += f"?{full_query_string}"

        template = "tabs/tab_async_loader.html"
        tab_context = {
            "tab_view_url": tab_view_url,
            "tab_object_name": "vulnerabilities",
        }

        return {
            "label": format_html(label),
            "fields": [(None, tab_context, None, template)],
        }

    def tab_codebase(self):
        codebaseresources_count = self.object.codebaseresources.count()
        if not codebaseresources_count:
            return

        label = f'Codebase <span class="badge text-bg-primary">{codebaseresources_count}</span>'
        template = "tabs/tab_async_loader.html"

        # Pass the current request query context to the async request
        tab_view_url = self.object.get_url("tab_codebase")
        if full_query_string := self.request.META["QUERY_STRING"]:
            tab_view_url += f"?{full_query_string}"

        tab_context = {
            "tab_view_url": tab_view_url,
            "tab_object_name": "codebase resources",
        }

        return {
            "label": format_html(label),
            "fields": [(None, tab_context, None, template)],
        }

    def tab_activity(self, exclude_product_context=False):
        return super().tab_activity(exclude_product_context=True)

    def tab_imports(self):
        scancodeprojects_count = self.object.scancodeprojects.count()
        if not scancodeprojects_count:
            return

        label = f'Imports <span class="badge text-bg-primary">{scancodeprojects_count}</span>'
        template = "tabs/tab_async_loader.html"

        # Pass the current request query context to the async request
        tab_view_url = self.object.get_url("tab_imports")
        if full_query_string := self.request.META["QUERY_STRING"]:
            tab_view_url += f"?{full_query_string}"

        tab_context = {
            "tab_view_url": tab_view_url,
            "tab_object_name": "imports",
        }

        return {
            "label": format_html(label),
            "fields": [(None, tab_context, None, template)],
        }

    def get_context_data(self, **kwargs):
        user = self.request.user
        dataspace = user.dataspace

        # This behavior does not works well in the context of getting informed about
        # tasks completion on the Product.
        if user.is_authenticated:
            self.object.mark_all_notifications_as_read(user)

        context = super().get_context_data(**kwargs)

        context["has_change_codebaseresource_permission"] = user.has_perm(
            "product_portfolio.change_codebaseresource"
        )

        context["filter_productcomponent"] = self.filter_productcomponent
        context["filter_productpackage"] = self.filter_productpackage
        # The reference data label and help does not make sense in the Product context
        context["is_reference_data"] = None

        perms = guardian_get_perms(user, self.object)
        context["has_change_permission"] = "change_product" in perms
        context["has_delete_permission"] = "delete_product" in perms

        context["has_edit_productpackage"] = all(
            [
                user.has_perm("product_portfolio.change_productpackage"),
                context["has_change_permission"],
            ]
        )
        context["has_delete_productpackage"] = user.has_perm(
            "product_portfolio.delete_productpackage"
        )

        context["has_add_productcomponent"] = all(
            [
                user.has_perm("product_portfolio.add_productcomponent"),
                context["has_change_permission"],
            ]
        )
        context["has_edit_productcomponent"] = all(
            [
                user.has_perm("product_portfolio.change_productcomponent"),
                context["has_change_permission"],
            ]
        )
        context["has_delete_productcomponent"] = user.has_perm(
            "product_portfolio.delete_productcomponent"
        )

        if context["has_edit_productpackage"] or context["has_edit_productcomponent"]:
            all_licenses = License.objects.scope(dataspace).filter(is_active=True)
            add_client_data(self.request, license_data=all_licenses.data_for_expression_builder())

        scancodeio = ScanCodeIO(dataspace)
        include_scancodeio_features = all(
            [
                scancodeio.is_configured(),
                user.is_superuser,
                dataspace.enable_package_scanning,
                context["is_user_dataspace"],
            ]
        )
        context["has_scan_all_packages"] = include_scancodeio_features

        if include_scancodeio_features:
            context["pull_project_data_form"] = PullProjectDataForm()
            context["display_scan_features"] = True

        context["purldb_enabled"] = all(
            [
                PurlDB(user.dataspace).is_configured(),
                user.dataspace.enable_purldb_access,
                context["is_user_dataspace"],
            ]
        )

        return context


class ProductTabInventoryView(
    LoginRequiredMixin,
    BaseProductViewMixin,
    PreviousNextPaginationMixin,
    TabContentView,
):
    template_name = "product_portfolio/tabs/tab_inventory.html"
    paginate_by = settings.TAB_PAGINATE_BY
    query_dict_page_param = "inventory-page"
    tab_id = "inventory"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user
        dataspace = user.dataspace
        context["inventory_count"] = self.object.productinventoryitem_set.count()

        license_qs = License.objects.select_related("usage_policy")
        declared_dependencies_qs = ProductDependency.objects.product(self.object)
        package_qs = (
            Package.objects.select_related(
                "dataspace",
                "usage_policy",
            )
            .prefetch_related(Prefetch("declared_dependencies", declared_dependencies_qs))
            .with_vulnerability_count()
        )
        component_qs = Component.objects.select_related(
            "dataspace",
            "owner__dataspace",
            "usage_policy",
        ).with_vulnerability_count()

        productpackage_qs = (
            self.object.productpackages.select_related(
                "review_status",
                "purpose",
            )
            .prefetch_related(
                Prefetch("licenses", license_qs),
                Prefetch("package", package_qs),
            )
            .order_by(
                "feature",
                "package__type",
                "package__namespace",
                "package__name",
                "package__version",
                "package__filename",
            )
        )

        filter_productpackage = ProductPackageFilterSet(
            self.request.GET,
            queryset=productpackage_qs,
            dataspace=self.object.dataspace,
            prefix=self.tab_id,
            anchor="#inventory",
        )

        productcomponent_qs = (
            self.object.productcomponents.select_related(
                "review_status",
                "purpose",
            )
            .prefetch_related(
                Prefetch("component", component_qs),
                Prefetch("licenses", license_qs),
                "component__packages",
                "component__children",
            )
            .order_by(
                "feature",
                "component__name",
                "component__version",
                "name",
                "version",
            )
        )

        filter_productcomponent = ProductComponentFilterSet(
            self.request.GET,
            queryset=productcomponent_qs,
            dataspace=self.object.dataspace,
            prefix=self.tab_id,
            anchor="#inventory",
        )

        productcomponent_qs = filter_productcomponent.qs
        productpackage_qs = filter_productpackage.qs
        # 1. Combine components and packages into a single list of object
        filtered_inventory_items = list(productcomponent_qs) + list(productpackage_qs)

        display_tab = any(
            [
                filtered_inventory_items,
                filter_productcomponent.is_active(),
                filter_productpackage.is_active(),
            ]
        )
        if not display_tab:
            return

        # 2. Paginate the inventory list
        paginator = Paginator(filtered_inventory_items, self.paginate_by)
        page_number = self.request.GET.get(self.query_dict_page_param)
        page_obj = paginator.get_page(page_number)

        # 3. Group objects by features
        object_list = page_obj.object_list
        objects_by_feature = defaultdict(list)
        for feature, items in group_by_simple(object_list, "feature").items():
            objects_by_feature[feature].extend(items)

        # Sort the dictionary by features, so "no-features" items are first
        objects_by_feature = dict(sorted(objects_by_feature.items()))

        # 4. Inject the Scan data when activated
        scancodeio = ScanCodeIO(dataspace)
        display_scan_features = all(
            [
                scancodeio.is_configured(),
                dataspace.enable_package_scanning,
                productpackage_qs,
            ]
        )
        if display_scan_features:
            context["display_scan_features"] = True
            self.inject_scan_data(scancodeio, objects_by_feature, dataspace.uuid)

        # 5. Display the compliance alert based on license policies
        if self.show_licenses_policy:
            context["show_licenses_policy"] = True
            compliance_alerts = set(
                alert
                for inventory_item in filtered_inventory_items
                for alert in inventory_item.compliance_alerts
            )
            if "error" in compliance_alerts:
                context["compliance_errors"] = True

        context.update(
            {
                "filter_productcomponent": filter_productcomponent,
                "inventory_items": dict(objects_by_feature.items()),
                "page_obj": page_obj,
                "search_query": self.request.GET.get("inventory-q", ""),
            }
        )

        perms = guardian_get_perms(user, self.object)
        has_product_change_permission = "change_product" in perms
        context["has_edit_productcomponent"] = all(
            [
                has_product_change_permission,
                user.has_perm("product_portfolio.change_productcomponent"),
            ]
        )
        context["has_edit_productpackage"] = all(
            [
                has_product_change_permission,
                user.has_perm("product_portfolio.change_productpackage"),
            ]
        )
        context["has_delete_productpackage"] = user.has_perm(
            "product_portfolio.delete_productpackage"
        )
        context["has_delete_productcomponent"] = user.has_perm(
            "product_portfolio.delete_productcomponent"
        )

        if page_obj:
            previous_url, next_url = self.get_previous_next(page_obj)
            context.update(
                {
                    "previous_url": (previous_url or "") + f"#{self.tab_id}",
                    "next_url": (next_url or "") + f"#{self.tab_id}",
                }
            )

        return context

    @staticmethod
    def inject_scan_data(scancodeio, feature_grouped, dataspace_uuid):
        download_urls = [
            product_package.package.download_url
            for product_packages in feature_grouped.values()
            for product_package in product_packages
            if isinstance(product_package, ProductPackage)
        ]

        # WARNING: Do not trigger a Request for an empty list of download_urls
        if not download_urls:
            return

        scoped_url_uids = [
            f"{get_hash_uid(url)}.{get_hash_uid(dataspace_uuid)}" for url in download_urls
        ]

        scans = []
        max_results_per_page = 50
        for names in chunked(scoped_url_uids, chunk_size=max_results_per_page):
            scan_list_data = scancodeio.fetch_scan_list(names=",".join(names))
            if scan_list_data:
                scans.extend(scan_list_data.get("results", []))

        if not scans:
            return

        scans_by_uri = {get_package_download_url(scan): scan for scan in scans}

        injected_feature_grouped = {}
        for feature_label, productpackages in feature_grouped.items():
            injected_productpackages = []
            for productpackage in productpackages:
                if not isinstance(productpackage, ProductPackage):
                    continue
                scan = scans_by_uri.get(productpackage.package.download_url)
                if scan:
                    scan["download_result_url"] = get_scan_results_as_file_url(scan)
                    productpackage.scan = scan
                injected_productpackages.append(productpackage)

            if injected_productpackages:
                injected_feature_grouped[feature_label] = injected_productpackages

        return injected_feature_grouped


class ProductTabCodebaseView(
    LoginRequiredMixin,
    BaseProductViewMixin,
    PreviousNextPaginationMixin,
    TabContentView,
):
    template_name = "product_portfolio/tabs/tab_codebase.html"
    paginate_by = 25
    query_dict_page_param = "codebase-page"
    tab_id = "codebase"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        codebaseresource_qs = CodebaseResource.objects.filter(
            product=self.object
        ).default_select_prefetch()

        filter_codebaseresource = CodebaseResourceFilterSet(
            self.request.GET,
            queryset=codebaseresource_qs,
            dataspace=self.object.dataspace,
            prefix=self.tab_id,
        )

        paginator = Paginator(filter_codebaseresource.qs, self.paginate_by)
        page_number = self.request.GET.get(self.query_dict_page_param)
        page_obj = paginator.get_page(page_number)

        fields = [
            "path",
            "is_deployment_path",
            "product_component",
            "product_package",
            "additional_details",
            "deployed_from_paths",
            "deployed_to_paths",
        ]

        codebase_resources = [
            {field: getattr(resource, field, None) for field in fields}
            for resource in page_obj.object_list
        ]

        def has_any_values(field_name):
            filter_is_active = field_name in filter_codebaseresource.form.changed_data
            if filter_is_active:
                return True

            return any(
                [
                    resource.get(field_name)
                    for resource in codebase_resources
                    if resource.get(field_name)
                ]
            )

        context_data.update(
            {
                "filter_codebaseresource": filter_codebaseresource,
                "codebase_resources": codebase_resources,
                "page_obj": page_obj,
                "search_query": self.request.GET.get("codebase-q", ""),
                "has_product_component": has_any_values("product_component"),
                "has_product_package": has_any_values("product_package"),
                "has_deployed_paths": has_any_values("deployed_from_paths"),
            }
        )

        if page_obj:
            previous_url, next_url = self.get_previous_next(page_obj)
            context_data.update(
                {
                    "previous_url": (previous_url or "") + f"#{self.tab_id}",
                    "next_url": (next_url or "") + f"#{self.tab_id}",
                }
            )

        return context_data


class ProductTabDependenciesView(
    LoginRequiredMixin,
    BaseProductViewMixin,
    PreviousNextPaginationMixin,
    TableHeaderMixin,
    TabContentView,
):
    template_name = "product_portfolio/tabs/tab_dependencies.html"
    paginate_by = 50
    table_model = ProductDependency
    filterset_class = DependencyFilterSet
    query_dict_page_param = "dependencies-page"
    tab_id = "dependencies"
    table_headers = (
        Header("for_package", _("For package"), filter="for_package"),
        Header("resolved_to_package", _("Resolved to package"), filter="resolved_to_package"),
        Header("declared_dependency", _("Declared dependency")),
        Header("scope", _("Scope")),
        Header("extracted_requirement", _("Extracted requirement")),
        Header("is_runtime", _("Runtime"), filter="is_runtime"),
        Header("is_optional", _("Optional"), filter="is_optional"),
        Header("is_pinned", _("Pinned"), filter="is_pinned"),
    )

    def get_context_data(self, **kwargs):
        product = self.object
        for_package_qs = Package.objects.only_rendering_fields().with_vulnerability_count()
        resolved_to_package_qs = (
            Package.objects.only_rendering_fields()
            .declared_dependencies_count(product)
            .with_vulnerability_count()
        )
        dependency_qs = product.dependencies.prefetch_related(
            Prefetch("for_package", for_package_qs),
            Prefetch("resolved_to_package", resolved_to_package_qs),
        )

        self.filterset = self.filterset_class(
            self.request.GET,
            queryset=dependency_qs,
            dataspace=product.dataspace,
            prefix=self.tab_id,
        )

        context_data = super().get_context_data(**kwargs)

        filtered_and_ordered_qs = self.filterset.qs.order_by(
            "for_package__type",
            "for_package__namespace",
            "for_package__name",
            "for_package__version",
            "dependency_uid",
        )

        paginator = Paginator(filtered_and_ordered_qs, self.paginate_by)
        page_number = self.request.GET.get(self.query_dict_page_param)
        page_obj = paginator.get_page(page_number)

        context_data.update(
            {
                "filterset": self.filterset,
                "page_obj": page_obj,
                "total_count": product.dependencies.count(),
                "search_query": self.request.GET.get("dependencies-q", ""),
            }
        )

        if page_obj:
            previous_url, next_url = self.get_previous_next(page_obj)
            context_data.update(
                {
                    "previous_url": (previous_url or "") + f"#{self.tab_id}",
                    "next_url": (next_url or "") + f"#{self.tab_id}",
                }
            )

        return context_data


class ProductTabVulnerabilitiesView(
    LoginRequiredMixin,
    BaseProductViewMixin,
    PreviousNextPaginationMixin,
    TableHeaderMixin,
    TabContentView,
):
    template_name = "product_portfolio/tabs/tab_vulnerabilities.html"
    paginate_by = 50
    query_dict_page_param = "vulnerabilities-page"
    tab_id = "vulnerabilities"
    table_model = Vulnerability
    filterset_class = VulnerabilityFilterSet
    table_headers = (
        Header("vulnerability_id", _("Vulnerability")),
        Header("affected_packages", _("Affected packages"), help_text="Affected product packages"),
        Header("exploitability", _("Exploitability"), filter="max_score"),
        Header("weighted_severity", _("Severity"), filter="max_score"),
        Header("risk_score", _("Risk"), filter="max_score"),
        Header("summary", _("Summary")),
    )

    def get_context_data(self, **kwargs):
        product = self.object
        base_vulnerability_qs = product.get_vulnerability_qs()
        total_count = base_vulnerability_qs.count()

        package_qs = Package.objects.filter(product=product).only_rendering_fields()
        vulnerability_qs = base_vulnerability_qs.prefetch_related(
            Prefetch("affected_packages", package_qs)
        ).order_by(
            F("max_score").desc(nulls_last=True),
            "-min_score",
        )

        self.filterset = self.filterset_class(
            self.request.GET,
            queryset=vulnerability_qs,
            dataspace=product.dataspace,
            prefix=self.tab_id,
            anchor=f"#{self.tab_id}",
        )

        # The self.filterset needs to be set before calling super()
        context_data = super().get_context_data(**kwargs)

        paginator = Paginator(self.filterset.qs, self.paginate_by)
        page_number = self.request.GET.get(self.query_dict_page_param)
        page_obj = paginator.get_page(page_number)

        context_data.update(
            {
                "filterset": self.filterset,
                "page_obj": page_obj,
                "total_count": total_count,
                "search_query": self.request.GET.get("vulnerabilities-q", ""),
            }
        )

        if page_obj:
            previous_url, next_url = self.get_previous_next(page_obj)
            context_data.update(
                {
                    "previous_url": (previous_url or "") + f"#{self.tab_id}",
                    "next_url": (next_url or "") + f"#{self.tab_id}",
                }
            )

        return context_data


class ProductTabImportsView(
    LoginRequiredMixin,
    BaseProductViewMixin,
    TabContentView,
):
    template_name = "product_portfolio/tabs/tab_imports.html"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        scancode_projects = self.object.scancodeprojects.all()
        submitted_projects = self.get_submitted_projects(scancode_projects)

        # Check the status of the "submitted" projects on ScanCode.io and update the
        # local ScanCodeProject instances accordingly.
        scancodeio = ScanCodeIO(self.request.user.dataspace)
        for submitted_project in submitted_projects:
            self.synchronize(scancodeio=scancodeio, project=submitted_project)

        context_data.update(
            {
                "scancode_projects": scancode_projects,
                "has_projects_in_progress": bool(submitted_projects),
                "tab_view_url": self.object.get_url("tab_imports"),
            }
        )

        return context_data

    @staticmethod
    def get_submitted_projects(scancode_projects):
        submitted_types = [
            ScanCodeProject.ProjectType.LOAD_SBOMS,
            ScanCodeProject.ProjectType.IMPORT_FROM_MANIFEST,
        ]
        return [
            project
            for project in scancode_projects
            if project.status == ScanCodeProject.Status.SUBMITTED
            and project.type in submitted_types
        ]

    def synchronize(self, scancodeio, project):
        scan_detail_url = scancodeio.get_scan_detail_url(project.project_uuid)
        scan_data = scancodeio.fetch_scan_data(scan_detail_url)
        if not scan_data:
            return

        runs = scan_data.get("runs")
        if not (runs and len(runs) == 1):
            return

        run = runs[0]
        run_status = run.get("status")
        if run_status != project.status:
            if run_status == "success":
                transaction.on_commit(
                    lambda: tasks.pull_project_data_from_scancodeio.delay(
                        scancodeproject_uuid=project.uuid,
                    )
                )
            elif run_status == "failure":
                project.status = ScanCodeProject.Status.FAILURE
                project.save(update_fields=["status"])


@login_required
def add_customcomponent_ajax_view(request, dataspace, name, version=""):
    user = request.user
    form_class = ProductCustomComponentForm

    qs = Product.objects.get_queryset(user, perms="change_product")
    product = get_object_or_404(qs, name=unquote_plus(name), version=unquote_plus(version))

    if not user.has_perm("product_portfolio.add_productcomponent"):
        return JsonResponse({"error_message": "Permission denied"}, status=403)

    if request.method == "POST":
        form = form_class(user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Custom Component relationship successfully added.")
            return JsonResponse({"success": "added"}, status=200)
    else:
        form = form_class(user, initial={"product": product})

    rendered_form = render_crispy_form(form)

    return HttpResponse(rendered_form)


@login_required
def edit_productrelation_ajax_view(request, relation_type, relation_uuid):
    user = request.user

    model_class = {
        "component": ProductComponent,
        "custom-component": ProductComponent,
        "package": ProductPackage,
    }.get(relation_type)

    form_class = {
        "component": ProductComponentForm,
        "custom-component": ProductCustomComponentForm,
        "package": ProductPackageForm,
    }.get(relation_type)

    if not (model_class and form_class):
        return JsonResponse({"error_message": "Permission denied"}, status=403)

    related_model_name = relation_type if relation_type != "custom-component" else "component"
    relationship_model_name = model_class._meta.model_name

    qs = model_class.objects.scope(user.dataspace)
    relation_instance = get_object_or_404(qs, uuid=relation_uuid)
    product = relation_instance.product

    has_permissions = all(
        [
            product.can_be_changed_by(user),
            user.has_perm(f"product_portfolio.change_{relationship_model_name}"),
        ]
    )

    if not has_permissions:
        return JsonResponse({"error_message": "Permission denied"}, status=403)

    has_delete_permission = user.has_perm(f"product_portfolio.delete_{relationship_model_name}")
    if request.GET.get("delete"):
        if has_delete_permission:
            History.log_deletion(user, relation_instance)
            relation_verbose_name = relation_type.replace("-", " ")
            message = f'Deleted {relation_verbose_name} "{relation_instance}"'
            History.log_change(user, product, message=message)
            product.last_modified_by = user
            product.save()
            relation_instance.delete()
            msg = (
                f"{related_model_name.title()} relationship {relation_instance} "
                f"successfully deleted."
            )
            messages.success(request, msg)
        return redirect(f"{product.get_absolute_url()}#inventory")

    if request.method == "POST":
        form = form_class(user, instance=relation_instance, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"{related_model_name.title()} relationship successfully updated."
            )
            return JsonResponse({"success": "updated"}, status=200)
    else:
        form = form_class(user, instance=relation_instance)

    rendered_form = render_crispy_form(form)

    relationship_field = f"""
    <div class="mb-3">
      <label for="id_relationship_instance" class="col-form-label form-label">
        {related_model_name.title()}
      </label>
      <input type="text" value="{relation_instance}" class="form-control" disabled
       id="id_relationship_instance">
    </div>
    """

    if relation_type != "custom-component":
        rendered_form = relationship_field + rendered_form

    return HttpResponse(rendered_form)


class ProductAddView(
    LicenseDataForBuilderMixin,
    DataspacedCreateView,
):
    model = Product
    form_class = ProductForm
    permission_required = "product_portfolio.add_product"


class ProductUpdateView(
    LicenseDataForBuilderMixin,
    BaseProductViewMixin,
    DataspacedUpdateView,
):
    form_class = ProductForm
    permission_required = "product_portfolio.change_product"

    def get_queryset(self):
        return self.model.objects.get_queryset(
            user=self.request.user,
            perms="change_product",
        )

    def get_success_url(self):
        if not self.object.is_active:
            return reverse("product_portfolio:product_list")
        return super().get_success_url()


class ProductDeleteView(BaseProductViewMixin, DataspacedDeleteView):
    permission_required = "product_portfolio.delete_product"

    def get_queryset(self):
        return self.model.objects.get_queryset(
            user=self.request.user,
            perms="delete_product",
        )


class ProductTreeComparisonView(
    LoginRequiredMixin,
    TemplateView,
):
    template_name = "product_portfolio/product_tree_comparison.html"

    def get(self, request, *args, **kwargs):
        guarded_qs = Product.objects.get_queryset(self.request.user)
        self.left_product = get_object_or_404(guarded_qs, uuid=self.kwargs["left_uuid"])
        self.right_product = get_object_or_404(guarded_qs, uuid=self.kwargs["right_uuid"])

        if self.request.GET.get("download_xlsx"):
            context = self.get_context_data(**kwargs)
            return self.comparison_download_xlsx(rows=context["rows"])

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        left_dict = self.get_productrelationship_dict(self.left_product)
        right_dict = self.get_productrelationship_dict(self.right_product)

        left_relationships = set(left_dict.keys())
        right_relationships = set(right_dict.keys())

        removed = list(left_relationships.difference(right_relationships))
        added = list(right_relationships.difference(left_relationships))

        removed_identifiers = [
            self.get_related_object_unique_identifier(left_dict[instance]) for instance in removed
        ]
        added_identifiers = [
            self.get_related_object_unique_identifier(right_dict[instance]) for instance in added
        ]

        # The "update" status is only possible when no more than 2 packages (1 on each side)
        # have the same unique identifier.
        updated = [
            (removed[removed_identifiers.index(name)], added[added_identifiers.index(name)])
            for name in removed_identifiers
            if added_identifiers.count(name) == 1 and removed_identifiers.count(name) == 1
        ]
        for k, v in updated:
            del removed[removed.index(k)]
            del added[added.index(v)]

        unchanged, changed = [], []
        diffs = {}
        excluded = ["product", "uuid"] + self.request.GET.getlist("exclude")

        for k in left_relationships.intersection(right_relationships):
            diff, _ = get_object_compare_diff(left_dict[k], right_dict[k], excluded)
            changed.append(k) if diff else unchanged.append(k)
            diffs[k] = OrderedDict(sorted(diff.items()))

        rows = [("added", None, right_dict[k], None) for k in added]
        rows.extend(("removed", left_dict[k], None, None) for k in removed)
        rows.extend(("updated", left_dict[k], right_dict[v], None) for k, v in updated)
        rows.extend(("changed", left_dict[k], right_dict[k], diffs[k]) for k in changed)
        rows.extend(("unchanged", left_dict[k], right_dict[k], None) for k in unchanged)
        rows.sort(key=self.sort_by_name_version)

        action_filters = [
            {"value": "added", "count": len(added), "checked": True},
            {"value": "changed", "count": len(changed), "checked": True},
            {"value": "updated", "count": len(updated), "checked": True},
            {"value": "removed", "count": len(removed), "checked": True},
            {"value": "unchanged", "count": len(unchanged), "checked": False},
        ]

        context.update(
            {
                "left_product": self.left_product,
                "right_product": self.right_product,
                "action_filters": action_filters,
                "rows": rows,
                "exclude_fields_form": ComparisonExcludeFieldsForm(self.request.GET),
            }
        )

        return context

    @staticmethod
    def get_productrelationship_dict(instance):
        component_qs = instance.productcomponents.select_related(
            "review_status",
            "component__owner",
        ).prefetch_related("licenses")

        package_qs = instance.productpackages.select_related("review_status").prefetch_related(
            "licenses"
        )

        relationship_dict = {}
        for relationship in list(component_qs) + list(package_qs):
            related = relationship.related_component_or_package
            if related:
                key = related.uuid
            elif relationship.name:  # custom component
                key = f"{relationship.name}-{relationship.version}"
            else:
                continue
            relationship_dict[key] = relationship

        return relationship_dict

    @staticmethod
    def get_related_object_unique_identifier(relationship):
        """
        Return a value suitable for identifying object as the same regardless of the
        version.
        - For Component and CustomComponent: using the ``name``.
        - For Package: using the ``type`` + ``namespace`` + ``name`` combination
          from the PackageURL when defined, or the ``filename`` as an alternative.
        """
        related = relationship.related_component_or_package
        if related:
            if isinstance(related, Package):
                if related.type and related.name:
                    return f"{related.type}/{related.namespace}/{related.name}"
                return related.filename  # Use filename for Package without a purl
            return related.name

        return relationship.name  # custom component

    @staticmethod
    def sort_by_name_version(row):
        index = 1 if row[1] else 2
        relationship = row[index]
        related = relationship.related_component_or_package
        if related:
            name = related.name or related.filename
            return name.lower(), related.version
        return relationship.name.lower(), relationship.version

    def comparison_download_xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.title = "Product comparison"
        header = ["Changes", str(self.left_product), str(self.right_product)]
        compare_data = [header]

        def get_relation_data(relation, diff, is_left):
            if not relation:
                return ""

            data = [
                str(relation),
                "",
                f"Review status: {relation.review_status or ''}",
                f"License: {relation.license_expression or ''}",
            ]
            if relation.purpose:
                data.append(f"Purpose: {relation.purpose or ''}")

            if diff:
                data.append("")
                for field, values in diff.items():
                    diff_line = (
                        f"{'-' if is_left else '+'} {field.verbose_name.title()}: "
                        f"{values[0] if is_left else values[1]}"
                    )
                    data.append(diff_line)

            return "\n".join(data)

        # Iterate over each row and populate the Excel worksheet
        for action, left, right, diff in rows:
            compare_data.append(
                [
                    action,
                    get_relation_data(left, diff, is_left=True),
                    get_relation_data(right, diff, is_left=False),
                ]
            )

        for row in compare_data:
            ws.append(row)

        # Styling
        header = NamedStyle(name="header")
        header.font = Font(bold=True)
        header.border = Border(bottom=Side(border_style="thin"))
        header.alignment = Alignment(horizontal="center", vertical="center")
        header_row = ws[1]
        for cell in header_row:
            cell.style = header

        # Freeze first header row
        ws.freeze_panes = "A2"

        # Columns width
        ws.column_dimensions["B"].width = 40
        ws.column_dimensions["C"].width = 40

        # Prepare response
        xlsx_content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        response = HttpResponse(content_type=xlsx_content_type)
        response["Content-Disposition"] = "attachment; filename=product_comparison.xlsx"
        wb.save(response)

        return response


AttributionNode = namedtuple(
    "AttributionNode",
    [
        "model_name",
        "display_name",
        "owner",
        "copyright",
        "extra_attribution_text",
        "relationship_expression",
        "component_expression",
        "notice_text",
        "is_displayed",
        "homepage_url",
        "standard_notice",
    ],
)


class AttributionView(
    LoginRequiredMixin,
    DataspaceScopeMixin,
    GetDataspacedObjectMixin,
    BaseProductViewMixin,
    DetailView,
):
    template_name = "product_portfolio/attribution/base.html"

    def get_template_names(self):
        """
        Prepend a Dataspace specific template in the list of template names.
        If that template exists, it will be used first, in place of the common template.

        To Generate the Dataspace hash for the template directory name:
        >>> from dejacode_toolkit.utils import sha1; sha1(b'<Dataspace name>')[:7]
        """
        names = super().get_template_names()
        dataspace_hash = sha1(self.object.dataspace.name.encode("utf-8"))[:7]
        if not self.template_name.endswith("attribution_configuration.html"):
            names.insert(0, f"product_portfolio/attribution/{dataspace_hash}/base.html")
        return names

    def get_queryset(self):
        return super().get_queryset().select_related("owner")

    def is_displayed(self, instance):
        """
        Return True if the instance is allowed for display,
        ie: not excluded by a Component Query.
        """
        return any(
            [
                not isinstance(instance, Component),
                not self.allowed_component_ids,
                instance.pk in self.allowed_component_ids,
            ]
        )

    @staticmethod
    def get_sorted(data, sort_attr="short_name"):
        """
        Return a list sorted by sort_attr.
        Sorts alphabetically ignoring the case.
        """
        return sorted(set(data), key=lambda x: attrgetter(sort_attr)(x).lower())

    @staticmethod
    def apply_productcomponent_query(productcomponents, query, user):
        """
        Limit a ProductComponent QuerySet using the results of a reporting Query.
        ProductComponent instances not returned in the Query results are excluded.
        """
        ids = query.get_qs(user=user).values_list("id", flat=True)
        return [pc for pc in productcomponents if pc.id in ids]

    def as_attribution_node(self, relationship):
        """Return a AttributionNode from a relationship (ProductComponent or Subcomponent)."""
        component = relationship.related_component_or_package

        if not component:
            return AttributionNode(
                model_name="component",
                display_name=str(relationship),
                owner=relationship.owner,
                copyright=relationship.copyright,
                extra_attribution_text=relationship.extra_attribution_text,
                relationship_expression=relationship.license_expression_attribution,
                component_expression=None,
                notice_text=None,
                is_displayed=True,
                homepage_url=relationship.homepage_url if self.include_homepage_url else "",
                standard_notice=(
                    relationship.standard_notice if self.include_standard_notice else ""
                ),
            )

        copyright_ = ""
        if component.copyright and not getattr(component, "is_copyright_notice", False):
            copyright_ = component.copyright

        component_expression = None
        if self.include_all_licenses:
            licensing = build_licensing()
            rel_ex = parse_expression(
                relationship.license_expression, validate_known=False, validate_strict=False
            )
            com_ex = parse_expression(
                component.license_expression, validate_known=False, validate_strict=False
            )
            if not licensing.is_equivalent(rel_ex, com_ex):
                component_expression = component.license_expression_attribution

        return AttributionNode(
            model_name=component._meta.model_name,
            display_name=str(component),
            owner=str(getattr(component, "owner", None) or ""),
            copyright=copyright_,
            extra_attribution_text=relationship.extra_attribution_text,
            relationship_expression=relationship.license_expression_attribution,
            component_expression=component_expression,
            notice_text=component.notice_text,
            is_displayed=self.is_displayed(component),
            homepage_url=component.homepage_url if self.include_homepage_url else "",
            standard_notice=relationship.standard_notice if self.include_standard_notice else "",
        )

    def get_hierarchy(self, relationship_qs, include_subcomponents):
        """
        Return a data structure suitable for the Attribution Generation.

        If a license is only referenced by a Component.license_expression and not by any
        <Relationship>.license_expression then include that license text at the end of the
        document only if "Include all License texts" is checked.
        """
        hierarchy = {}

        for relationship in relationship_qs:
            component = relationship.related_component_or_package

            children_hierarchy = []
            if component and include_subcomponents:
                children_qs = component.related_children.order_by(Lower("child__name"))
                children_hierarchy = self.get_hierarchy(children_qs, include_subcomponents)

            if component and self.is_displayed(component):
                self.hierarchy_licenses.extend(relationship.licenses.all())
                if self.include_all_licenses:
                    self.hierarchy_licenses.extend(component.licenses.all())
            elif not component:  # Custom component
                self.hierarchy_licenses.extend(relationship.licenses.all())

            node = self.as_attribution_node(relationship)
            # Using namedtuples in a set to avoid exact duplicates
            self.unique_component_nodes.add(node)

            feature = getattr(relationship, "feature", "")
            # Not using a defaultdict as not supported by Django templates
            if feature not in hierarchy:
                hierarchy[feature] = []
            hierarchy[feature].append((node, children_hierarchy))

        return hierarchy

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        product = self.object
        submitted = request.GET.get("submit")

        initial = {}
        if not submitted and product.productpackages.exists():
            initial = {"include_packages": True}

        form = AttributionConfigurationForm(request, data=request.GET or None, initial=initial)

        context.update(
            {
                "is_user_dataspace": product.dataspace == request.user.dataspace,
                "is_reference_data": product.dataspace.is_reference,
                "configuration_form": form,
            }
        )

        if not submitted or not form.is_valid():
            self.template_name = "product_portfolio/attribution_configuration.html"
            return context

        product_licenses = list(product.licenses.order_by("short_name"))
        productcomponents = product.productcomponents.order_by("component", "name", "version")

        group_by_feature = bool(form.cleaned_data.get("group_by_feature"))
        if group_by_feature:
            # Empty string first then alphabetical order
            productcomponents = productcomponents.order_by(
                "feature", "component", "name", "version"
            )

        if form.cleaned_data.get("is_deployed"):
            productcomponents = productcomponents.filter(is_deployed=True)

        pc_query = form.cleaned_data.get("pc_query")
        if pc_query:
            productcomponents = self.apply_productcomponent_query(
                productcomponents, pc_query, user=request.user
            )

        component_query = form.cleaned_data.get("component_query")
        self.allowed_component_ids = []
        if component_query:
            self.allowed_component_ids = component_query.get_qs(user=request.user).values_list(
                "id", flat=True
            )

        self.include_all_licenses = bool(form.cleaned_data.get("all_license_texts"))
        self.include_homepage_url = bool(form.cleaned_data.get("include_homepage_url"))
        self.include_standard_notice = bool(form.cleaned_data.get("include_standard_notice"))

        # self.hierarchy_licenses and self.unique_component_nodes are populated during the
        # self.get_hierarchy() call
        self.hierarchy_licenses = []
        self.unique_component_nodes = set()

        include_subcomponents = bool(form.cleaned_data.get("subcomponent_hierarchy"))
        context["hierarchy"] = self.get_hierarchy(productcomponents, include_subcomponents)

        include_packages = bool(form.cleaned_data.get("include_packages"))
        package_nodes = []
        package_nodes_by_feature = {}
        if include_packages:
            productpackages = product.productpackages.all()
            if group_by_feature:
                # Empty string first then alphabetical order
                productpackages = productpackages.order_by("feature")
            for relationship in productpackages:
                attribution_node = self.as_attribution_node(relationship)
                package_nodes.append(attribution_node)
                self.hierarchy_licenses.extend(relationship.licenses.all())
                if group_by_feature:
                    feature = getattr(relationship, "feature", "")
                    if feature not in package_nodes_by_feature:
                        package_nodes_by_feature[feature] = []
                    package_nodes_by_feature[feature].append(attribution_node)

        context["hierarchy_licenses"] = self.get_sorted(set(self.hierarchy_licenses))
        all_available_licenses = product_licenses + context["hierarchy_licenses"]

        context.update(
            {
                "all_available_licenses": self.get_sorted(set(all_available_licenses)),
                "toc_as_nested_list": bool(form.cleaned_data.get("toc_as_nested_list")),
                "group_by_feature": group_by_feature,
                "unique_component_nodes": self.get_sorted(
                    self.unique_component_nodes, "display_name"
                ),
                "package_nodes": package_nodes,
                "package_nodes_by_feature": package_nodes_by_feature,
            }
        )

        return context


class ProductSendAboutFilesView(BaseProductViewMixin, SendAboutFilesView):
    pass


class ProductExportSPDXDocumentView(BaseProductViewMixin, ExportSPDXDocumentView):
    pass


class ProductExportCycloneDXBOMView(BaseProductViewMixin, ExportCycloneDXBOMView):
    pass


@login_required
def scan_all_packages_view(request, dataspace, name, version=""):
    user = request.user
    user_dataspace = user.dataspace

    scancodeio = ScanCodeIO(user_dataspace)
    conditions = [
        scancodeio.is_configured(),
        user.is_superuser,
        user_dataspace.enable_package_scanning,
        user_dataspace.name == dataspace,
    ]

    if not all(conditions):
        raise Http404

    guarded_qs = Product.objects.get_queryset(user)
    product = get_object_or_404(guarded_qs, name=unquote_plus(name), version=unquote_plus(version))

    if not product.all_packages:
        raise Http404("No packages available for this product.")

    transaction.on_commit(lambda: product.scan_all_packages_task(user))

    scan_list_url = reverse("component_catalog:scan_list")
    scancode_msg = format_html(
        'All "{}" packages submitted to ScanCode.io for scanning.'
        ' <a href="{}" target="_blank">Click here to see the Scans list.</a>',
        product.get_absolute_link(),
        scan_list_url,
    )
    messages.success(request, scancode_msg)

    return redirect(product)


@login_required
def import_from_scan_view(request, dataspace, name, version=""):
    """
    Import the scan results in a Product.

    If any errors are raised during the import, the transaction is rollbacked
    an no data will be kept to avoid half-imported results.
    """
    user = request.user
    form_class = ImportFromScanForm

    guarded_qs = Product.objects.get_queryset(user)
    product = get_object_or_404(guarded_qs, name=unquote_plus(name), version=unquote_plus(version))

    if request.method == "POST":
        form = form_class(
            user=request.user,
            data=request.POST,
            files=request.FILES,
        )
        if form.is_valid():
            try:
                warnings, created_counts = form.save(product=product)
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
                return redirect(request.path)

            if not created_counts:
                messages.warning(request, "Nothing imported.")
            else:
                msg = "Imported from Scan:"
                for key, value in created_counts.items():
                    msg += f"<br> &bull; {value} {key}"
                messages.success(request, format_html(msg))
            if warnings:
                messages.warning(request, format_html("<br>".join(warnings)))
            return redirect(product)
    else:
        form = form_class(request.user)

    return render(
        request,
        "product_portfolio/import_from_scan.html",
        {
            "form": form,
            "product": product,
        },
    )


class BaseProductManageGridView(
    LoginRequiredMixin,
    LicenseDataForBuilderMixin,
    GetDataspacedObjectMixin,
    PermissionRequiredMixin,
    BaseProductViewMixin,
    FormSetView,
):
    """A base view for managing product relationship through a grid."""

    formset_class = BaseProductRelationshipInlineFormSet
    helper_class = TableInlineFormSetHelper
    template_name = "product_portfolio/object_manage_grid.html"
    related_model = None
    relationship_model = None
    filterset_class = None
    can_delete_permission = None
    configuration_session_key = None
    base_fields = []

    def get_relationship_queryset(self):
        raise ImproperlyConfigured("`get_relationship_queryset` must be defined.")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.filterset = self.get_filterset()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "update-grid-configuration" in request.POST:
            grid_configuration_form = ProductGridConfigurationForm(data=request.POST)
            if grid_configuration_form.is_valid():
                displayed_fields = request.POST.getlist("displayed_fields")
                request.session[self.configuration_session_key] = displayed_fields
                messages.success(request, "Grid configuration updated.")
            return redirect(self.get_success_url())

        self.object = self.get_object()
        self.filterset = self.get_filterset()
        return super().post(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.get_queryset(
            user=self.request.user,
            perms="change_product",
        )

    def get_success_url(self):
        """
        Use the HTTP_REFERER when available allows to keep the request.GET
        state of the view, keeping sort and filters for example.
        """
        return self.request.META.get("HTTP_REFERER") or self.request.path

    def formset_valid(self, formset):
        request = self.request

        if formset.has_changed():
            formset.save()
            messages.success(request, "Product changes saved.")
        else:
            messages.warning(request, "No changes to save.")

        if "save" in request.POST:
            return redirect(self.object)

        return redirect(self.get_success_url())

    def get_filterset(self):
        filterset = self.filterset_class(
            self.request.GET,
            queryset=self.get_relationship_queryset(),
            dataspace=self.object.dataspace,
        )
        return filterset

    def get_formset(self, formset_class=None):
        can_delete = False
        if self.can_delete_permission:
            can_delete = self.request.user.has_perm(self.can_delete_permission)

        FormSet = modelformset_factory(
            self.relationship_model,
            form=self.form_class,
            formset=self.formset_class,
            fields=self.get_fields(),
            extra=0,
            can_delete=can_delete,
        )

        return FormSet(
            **self.get_formset_kwargs(),
            queryset=self.filterset.qs,
            form_kwargs=self.get_form_kwargs(),
        )

    def get_form_kwargs(self):
        form_kwargs = {
            "user": self.request.user,
            "initial": {"product": self.object.id},
            "filterset": self.filterset,
        }
        return form_kwargs

    def get_fields(self):
        default_fields = ProductGridConfigurationForm.get_fields_name()
        configuration_fields = self.request.session.get(
            self.configuration_session_key, default_fields
        )

        if not configuration_fields:
            configuration_fields = default_fields
        else:
            configuration_fields = [
                field
                for field in configuration_fields
                if field in default_fields  # Discard any non-supported fields
            ]

        self.grid_configuration_form = ProductGridConfigurationForm(
            initial={"displayed_fields": configuration_fields}
        )

        fields = self.base_fields + configuration_fields

        return fields

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data.update(
            {
                "helper": self.helper_class(),
                "filterset": self.filterset,
                "product": self.object,
                "verbose_name_plural": self.object._meta.verbose_name_plural,
                "related_verbose_name": self.related_model._meta.verbose_name,
                "grid_configuration_form": self.grid_configuration_form,
            }
        )
        return context_data


class ManageComponentGridView(BaseProductManageGridView):
    related_model = Component
    relationship_model = ProductComponent
    permission_required = "product_portfolio.change_productcomponent"
    can_delete_permission = "product_portfolio.delete_productcomponent"
    form_class = ProductComponentInlineForm
    filterset_class = ProductComponentFilterSet
    configuration_session_key = "component_grid_configuration"
    base_fields = [
        "product",
        "component",
        "object_display",
    ]

    def get_relationship_queryset(self):
        return self.object.productcomponents.catalogs().select_related(
            "component__dataspace",
            "component__owner",
        )

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        user = self.request.user
        can_add_component = user.has_perm("component_catalog.add_component")
        if can_add_component:
            component_add_form = ComponentAjaxForm(user=user)
            context_data["component_add_form"] = component_add_form

        return context_data


class ManagePackageGridView(BaseProductManageGridView):
    related_model = Package
    relationship_model = ProductPackage
    permission_required = "product_portfolio.change_productpackage"
    can_delete_permission = "product_portfolio.delete_productpackage"
    form_class = ProductPackageInlineForm
    filterset_class = ProductPackageFilterSet
    configuration_session_key = "package_grid_configuration"
    base_fields = [
        "product",
        "package",
        "object_display",
    ]

    def get_relationship_queryset(self):
        return self.object.productpackages.select_related(
            "package__dataspace",
        )


@login_required
def license_summary_view(request, dataspace, name, version=""):
    user = request.user

    guarded_qs = Product.objects.get_queryset(user)
    product = get_object_or_404(guarded_qs, name=unquote_plus(name), version=unquote_plus(version))

    filterset = LicenseFilterSet(
        data=request.GET or None,
        request=request,
        dataspace=product.dataspace,
    )

    product_components = product.components.all()
    product_packages = product.packages.all()

    components_hierarchy = set(product_components)
    for component in product_components:
        components_hierarchy.update(component.get_descendants(set_direct_parent=True))

    packages_hierarchy = set(product_packages)
    for component in components_hierarchy:
        component_packages = []
        for package in component.packages.all():
            package.direct_parent = component
            component_packages.append(package)
        packages_hierarchy.update(component_packages)

    all_licenses = set()
    license_index = defaultdict(list)

    for item in list(components_hierarchy) + list(packages_hierarchy):
        licenses = item.licenses.all()
        all_licenses.update(licenses)
        for license in licenses:
            if license in filterset.qs:
                license_index[license].append(item)

    sorted_index = sorted(license_index.items(), key=lambda item: item[0].name)

    if request.GET.get("export"):
        response = HttpResponse(content_type="text/csv")
        prefix = str(product).replace(" ", "_")
        response["Content-Disposition"] = f'attachment; filename="{prefix}_license_summary.csv"'

        fieldnames = ["License", "Usage policy", "Items"]
        writer = csv.writer(response)
        writer.writerow(fieldnames)

        for license, items in sorted_index:
            row = [
                f"{license.name} ({license.key})",
                license.usage_policy,
                ", ".join([repr(item) for item in items]),
            ]
            writer.writerow(row)

        return response

    return render(
        request,
        "product_portfolio/license_summary.html",
        {
            "product": product,
            "license_index": dict(sorted_index),
            "filterset": filterset,
        },
    )


@login_required
def check_package_version_ajax_view(request, dataspace, name, version=""):
    user = request.user
    purldb = PurlDB(user.dataspace)

    purldb_enabled = all(
        [
            purldb.is_configured(),
            user.dataspace.enable_purldb_access,
        ]
    )
    if not purldb_enabled:
        raise Http404

    guarded_qs = Product.objects.get_queryset(user)
    product = get_object_or_404(guarded_qs, name=unquote_plus(name), version=unquote_plus(version))

    purls = []
    packages = product.packages.all()
    for package in packages:
        package_url = package.package_url
        if package_url:
            purls.append(package_url)

    # Chunk into several requests to prevent "Request Line is too large" errors
    max_purls_per_request = 50
    results = []
    for purl_batch in chunked(purls, chunk_size=max_purls_per_request):
        response = purldb.get_package_list(
            page_size=max_purls_per_request,
            extra_payload={"purl": purl_batch},
        )
        if response and response.get("results"):
            results.extend(response["results"])

    def get_latest_version_entry(current_uuid):
        latest_version_entry = request.session.get(current_uuid)
        if latest_version_entry:
            return latest_version_entry

        latest_version_entry = purldb.get_package(f"{current_uuid}/latest_version")
        if latest_version_entry:
            request.session[current_uuid] = latest_version_entry
            return latest_version_entry

    upgrade_available = []
    for purldb_entry in results:
        current_uuid = purldb_entry.get("uuid")
        current_version = purldb_entry.get("version")
        if latest_version_entry := get_latest_version_entry(current_uuid):
            latest_version = latest_version_entry.get("version")
            if current_version != latest_version:
                purldb_entry["latest_version"] = latest_version
                purldb_entry["latest_version_uuid"] = latest_version_entry.get("uuid")
                upgrade_available.append(purldb_entry)

    return JsonResponse({"success": "success", "upgrade_available": upgrade_available})


class BaseProductImportFormView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    GetDataspacedObjectMixin,
    DataspacedModelFormMixin,
    BaseProductViewMixin,
    FormView,
):
    permission_required = "product_portfolio.change_product"
    success_msg = ""

    def get_queryset(self):
        return self.model.objects.get_queryset(
            user=self.request.user,
            perms="change_product",
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.object
        return context

    def get_success_url(self):
        return f"{self.object.get_absolute_url()}#imports"

    def form_valid(self, form):
        self.object = self.get_object()

        try:
            form.submit(product=self.object, user=self.request.user)
        except ValidationError as error:
            messages.error(self.request, error)
            return redirect(self.object.get_absolute_url())

        if self.success_msg:
            messages.success(self.request, self.success_msg)

        return super().form_valid(form)


class LoadSBOMsView(BaseProductImportFormView):
    template_name = "product_portfolio/load_sboms_form.html"
    form_class = LoadSBOMsForm
    success_msg = "SBOM file submitted to ScanCode.io for inspection."


class ImportManifestsView(BaseProductImportFormView):
    template_name = "product_portfolio/import_manifests_form.html"
    form_class = ImportManifestsForm
    success_msg = "Manifest file submitted to ScanCode.io for inspection."


@method_decorator(require_POST, name="dispatch")
class PullProjectDataFromScanCodeIOView(BaseProductImportFormView):
    form_class = PullProjectDataForm
    success_msg = "Packages import from ScanCode.io in progress..."

    def form_invalid(self, form):
        raise Http404


@require_POST
@csrf_exempt
def import_packages_from_scancodeio_view(request, key):
    """
    Import the project scan packages in a Product.
    Used as a callback from ScanCode.io using a webhook on pipeline completion.
    """
    user_uuid = signing.loads(key)
    if not is_uuid4(user_uuid):
        raise Http404("Provided key is not a valid UUID.")

    try:
        json_data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise Http404("Request data is invalid.")

    user = get_object_or_404(DejacodeUser, uuid=user_uuid)
    project_uuid = json_data["project"]["uuid"]
    scancode_project = get_object_or_404(ScanCodeProject, project_uuid=project_uuid)

    # Ensure that the user has permission to change the ScanCodeProject related Product.
    product_qs = Product.objects.get_queryset(user, perms="change_product")
    get_object_or_404(product_qs, id=scancode_project.product_id)

    transaction.on_commit(
        lambda: tasks.pull_project_data_from_scancodeio.delay(
            scancodeproject_uuid=scancode_project.uuid,
        )
    )

    return JsonResponse({"message": "Received, packages import started."})


@login_required
def scancodeio_project_status_view(request, scancodeproject_uuid):
    template = "product_portfolio/scancodeio_project_status.html"
    dataspace = request.user.dataspace
    base_qs = ScanCodeProject.objects.scope(dataspace)
    scancode_project = get_object_or_404(base_qs, uuid=scancodeproject_uuid)

    scancodeio = ScanCodeIO(dataspace)
    scan_detail_url = scancodeio.get_scan_detail_url(scancode_project.project_uuid)
    scan_data = scancodeio.fetch_scan_data(scan_detail_url)

    results = scancode_project.results

    # Backward compatibility
    is_old_results_format = any(isinstance(entry, list) for entry in results.values())
    if is_old_results_format:
        results = {key: {"package": value} for key, value in results.items() if value}

    context = {
        "scancode_project": scancode_project,
        "results": results,
        "scan_data": scan_data,
    }

    return TemplateResponse(request, template, context)


@login_required
def improve_packages_from_purldb_view(request, dataspace, name, version=""):
    user = request.user
    guarded_qs = Product.objects.get_queryset(user)
    product = get_object_or_404(guarded_qs, name=unquote_plus(name), version=unquote_plus(version))

    perms = guardian_get_perms(user, product)
    has_change_permission = "change_product" in perms

    purldb = PurlDB(user.dataspace)
    conditions = [
        purldb.is_configured(),
        user.dataspace.enable_purldb_access,
        has_change_permission,
        user.dataspace.name == dataspace,
    ]

    if not all(conditions):
        raise Http404

    if not product.packages.count():
        raise Http404("No packages available for this product.")

    improve_in_progress = product.scancodeprojects.in_progress().filter(
        type=ScanCodeProject.ProjectType.IMPROVE_FROM_PURLDB,
    )

    if improve_in_progress.exists():
        messages.error(request, "Improve Packages already in progress...")
    else:
        transaction.on_commit(
            lambda: tasks.improve_packages_from_purldb(
                product_uuid=product.uuid,
                user_uuid=user.uuid,
            )
        )
        messages.success(request, "Improve Packages from PurlDB in progress...")
    return redirect(f"{product.get_absolute_url()}#imports")
