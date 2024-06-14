#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
import json
import zipfile
from collections import Counter
from operator import itemgetter
from urllib.parse import quote_plus

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.core.validators import EMPTY_VALUES
from django.db.models import Count
from django.db.models import Prefetch
from django.http import FileResponse
from django.http import Http404
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.dateparse import parse_datetime
from django.utils.formats import date_format
from django.utils.html import escape
from django.utils.html import format_html
from django.utils.text import normalize_newlines
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.generic import FormView
from django.views.generic.edit import BaseFormView

from crispy_forms.utils import render_crispy_form
from natsort import natsorted
from notifications.signals import notify
from packageurl import PackageURL
from packageurl.contrib import purl2url

from component_catalog.filters import ComponentFilterSet
from component_catalog.filters import PackageFilterSet
from component_catalog.forms import AddMultipleToComponentForm
from component_catalog.forms import AddToComponentForm
from component_catalog.forms import AddToProductAdminForm
from component_catalog.forms import AddToProductMultipleForm
from component_catalog.forms import ComponentAddToProductForm
from component_catalog.forms import ComponentAjaxForm
from component_catalog.forms import ComponentForm
from component_catalog.forms import PackageAddToProductForm
from component_catalog.forms import PackageForm
from component_catalog.forms import ScanSummaryToPackageForm
from component_catalog.forms import ScanToPackageForm
from component_catalog.forms import SetPolicyForm
from component_catalog.license_expression_dje import get_formatted_expression
from component_catalog.license_expression_dje import get_licensing_for_formatted_render
from component_catalog.license_expression_dje import get_unique_license_keys
from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.models import PackageAlreadyExistsWarning
from component_catalog.models import Subcomponent
from dejacode_toolkit.download import DataCollectionException
from dejacode_toolkit.purldb import PurlDB
from dejacode_toolkit.scancodeio import ScanCodeIO
from dejacode_toolkit.scancodeio import get_package_download_url
from dejacode_toolkit.scancodeio import get_scan_results_as_file_url
from dejacode_toolkit.vulnerablecode import VulnerableCode
from dje import tasks
from dje.client_data import add_client_data
from dje.models import DejacodeUser
from dje.models import History
from dje.templatetags.dje_tags import urlize_target_blank
from dje.urn_resolver import URN_HELP_TEXT
from dje.utils import get_cpe_vuln_link
from dje.utils import get_help_text as ght
from dje.utils import get_preserved_filters
from dje.utils import is_available
from dje.utils import is_uuid4
from dje.utils import str_to_id_list
from dje.views import AcceptAnonymousMixin
from dje.views import APIWrapperListView
from dje.views import DataspacedCreateView
from dje.views import DataspacedFilterView
from dje.views import DataspacedUpdateView
from dje.views import FieldLastLoop
from dje.views import FieldSeparator
from dje.views import Header
from dje.views import LicenseDataForBuilderMixin
from dje.views import ObjectDetailsView
from dje.views import TabContentView
from dje.views import TabField
from dje.views import normalize_tab_fields
from license_library.models import LicenseAssignedTag
from policy.models import UsagePolicy
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage

License = apps.get_model("license_library", "License")

COPYRIGHT_PLACEHODLER = "copyright_placeholder"


def format_dependencies(value):
    if not value:
        return ""

    try:
        return json.dumps(value, indent=2)
    except (ValueError, TypeError):
        return value


class AddToProductFormMixin(BaseFormView):
    open_add_to_package_modal = False
    add_to_product_perm = None

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["open_add_to_package_modal"] = self.open_add_to_package_modal

        add_to_product_form = context_data.get("form")
        if add_to_product_form:
            if self.object.license_expression:
                to_product_licenses = self.object.licenses.all().data_for_expression_builder()
                add_client_data(self.request, to_product_licenses=to_product_licenses)
            else:
                all_licenses = (
                    License.objects.scope(self.request.user.dataspace)
                    .filter(is_active=True)
                    .data_for_expression_builder()
                )
                add_client_data(self.request, license_data=all_licenses)

        return context_data

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            {
                "user": self.request.user,
                self.model._meta.model_name: self.object,
            }
        )
        return kwargs

    def get_initial(self):
        return {
            self.model._meta.model_name: self.object,
            "license_expression": self.object.license_expression,
        }

    def post(self, request, *args, **kwargs):
        if not hasattr(self, "object"):
            self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_form(self, form_class=None):
        if self.is_user_dataspace and self.request.user.has_perm(self.add_to_product_perm):
            form = super().get_form(form_class)
            # Do not include the `form` if the Product QuerySet is empty
            if form.fields["product"].queryset:
                return form

    def form_valid(self, form):
        created = form.save()
        product = form.cleaned_data["product"]
        opts = self.model._meta

        if created:
            msg = f'{opts.model_name.title()} "{self.object}" added to product "{product}".'
            messages.success(self.request, msg)
            redirect_url = f"{product.get_absolute_url()}#{opts.model_name}s"
        else:
            msg = f"Error assigning the {opts.model_name} to this product."
            messages.error(self.request, msg)
            redirect_url = self.request.path

        return redirect(redirect_url)

    def form_invalid(self, form):
        # Open the Add to Package modal on page load
        self.open_add_to_package_modal = True
        return self.get(self.request)


class AddToProductMultipleMixin(BaseFormView):
    form_class = AddToProductMultipleForm

    def get_form(self, form_class=None):
        if self.is_user_dataspace and self.request.user.has_perm(self.add_to_product_perm):
            form = super().get_form(form_class)
            # Do not include the `form` if the Product QuerySet is empty
            if form.fields["product"].queryset:
                return form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            {
                "request": self.request,
                "model": self.model,
                "relation_model": self.relation_model,
            }
        )
        return kwargs

    def form_valid(self, form):
        created_count, updated_count, unchanged_count = form.save()
        product = form.cleaned_data["product"]
        opts = self.model._meta

        msg = ""
        if created_count:
            msg = f'{created_count} {opts.model_name}(s) added to "{product}". '
        if updated_count:
            msg += f'{updated_count} {opts.model_name}(s) updated on "{product}".'

        if msg:
            messages.success(self.request, msg)
        else:
            msg = f"No new {opts.model_name}(s) were assigned to this product."
            messages.warning(self.request, msg)

        redirect_url = f"{product.get_absolute_url()}#{opts.model_name}s"
        return redirect(redirect_url)

    def form_invalid(self, form):
        return redirect(self.request.path)


def include_policy(view_instance):
    return view_instance.dataspace.show_usage_policy_in_user_views


def include_type(view_instance):
    return view_instance.dataspace.show_type_in_component_list_view


class TabVulnerabilityMixin:
    vulnerability_matching_field = None

    def tab_vulnerabilities(self):
        matching_value = getattr(self.object, self.vulnerability_matching_field)
        dataspace = self.object.dataspace
        vulnerablecode = VulnerableCode(self.request.user)

        # The display of vulnerabilities is controlled by the object Dataspace
        display_tab = all(
            [
                matching_value,
                dataspace.enable_vulnerablecodedb_access,
                vulnerablecode.is_configured(),
            ]
        )

        if not display_tab:
            return

        vulnerability_getter_function = {
            "cpe": vulnerablecode.get_vulnerabilities_by_cpe,
            "package_url": vulnerablecode.get_vulnerabilities_by_purl,
        }.get(self.vulnerability_matching_field)

        vulnerabilities = vulnerability_getter_function(matching_value, timeout=3)
        if not vulnerabilities:
            return

        fields, vulnerabilities_count = self.get_vulnerabilities_tab_fields(vulnerabilities)

        if fields:
            label = (
                f"Vulnerabilities"
                f' <span class="badge badge-vulnerability">{vulnerabilities_count}</span>'
            )
            return {
                "fields": fields,
                "label": format_html(label),
            }

    def get_vulnerabilities_tab_fields(self, vulnerabilities):
        raise NotImplementedError

    @staticmethod
    def get_vulnerability_fields(vulnerability, dataspace):
        include_fixed_packages = "fixed_packages" in vulnerability.keys()
        summary = vulnerability.get("summary")
        references = vulnerability.get("references", [])

        reference_urls = []
        reference_ids = []

        for reference in references:
            url = reference.get("reference_url")
            reference_id = reference.get("reference_id")
            if url and reference_id:
                reference_ids.append(f'<a href="{url}" target="_blank">{reference_id}</a>')
            elif reference_id:
                reference_ids.append(reference_id)
            elif url:
                reference_urls.append(url)

        reference_urls_joined = "\n".join(reference_urls)
        reference_ids_joined = "\n".join(reference_ids)

        tab_fields = [
            (_("Summary"), summary, "Summary of the vulnerability"),
        ]

        if vulnerability_url := vulnerability.get("resource_url"):
            vulnerability_url_help = "Link to the VulnerableCode app."
            url_as_link = format_html(
                '<a href="{vulnerability_url}" target="_blank">{vulnerability_url}</a>',
                vulnerability_url=vulnerability_url,
            )
            tab_fields.append((_("VulnerableCode URL"), url_as_link, vulnerability_url_help))

        if include_fixed_packages:
            fixed_packages = vulnerability.get("fixed_packages", [])
            fixed_packages_sorted = natsorted(fixed_packages, key=itemgetter("purl"))
            add_package_url = reverse("component_catalog:package_add")
            vulnerability_icon = (
                '<span data-bs-toggle="tooltip" title="Vulnerabilities"'
                ' data-boundary="viewport">'
                '<i class="fas fa-bug vulnerability ms-1"></i>'
                "</span>"
            )
            no_vulnerabilities_icon = (
                '<span class="fa-stack fa-small text-muted-light ms-1"'
                ' data-bs-toggle="tooltip" title="No vulnerabilities found"'
                ' data-boundary="viewport">'
                '  <i class="fas fa-bug fa-stack-1x"></i>'
                '  <i class="fas fa-ban fa-stack-2x"></i>'
                "</span>"
            )

            fixed_packages_values = []
            for fixed_package in fixed_packages_sorted:
                purl = fixed_package.get("purl")
                is_vulnerable = fixed_package.get("is_vulnerable")
                package_instances = Package.objects.scope(dataspace).for_package_url(purl)

                for package in package_instances:
                    absolute_url = package.get_absolute_url()
                    display_value = package.get_html_link(href=absolute_url)
                    if is_vulnerable:
                        display_value += package.get_html_link(
                            href=f"{absolute_url}#vulnerabilities",
                            value=format_html(vulnerability_icon),
                        )
                    else:
                        display_value += no_vulnerabilities_icon
                    fixed_packages_values.append(display_value)

                if not package_instances:
                    display_value = purl.replace("pkg:", "")
                    if is_vulnerable:
                        display_value += vulnerability_icon
                    else:
                        display_value += no_vulnerabilities_icon
                    # Warning: do not add spaces between HTML elements as this content
                    # is displayed in a <pre>
                    display_value += (
                        f'<a href="{add_package_url}?package_url={purl}"'
                        f'   target="_blank" class="ms-1">'
                        f'<span data-bs-toggle="tooltip" title="Add Package"'
                        f'      data-boundary="viewport">'
                        f'<i class="fas fa-plus-circle"></i>'
                        f"</span>"
                        f"</a>"
                    )
                    fixed_packages_values.append(display_value)

            tab_fields.append(
                (
                    _("Fixed packages"),
                    format_html("\n".join(fixed_packages_values)),
                    "The identifiers of Package Versions that have been reported to fix a "
                    "specific vulnerability and collected in VulnerableCodeDB.",
                ),
            )

        tab_fields.extend(
            [
                (
                    _("Reference IDs"),
                    format_html(reference_ids_joined),
                    "Reference IDs to the reported vulnerability, such as a DSA "
                    "(Debian Security Advisory) ID or a CVE (Common Vulnerabilities "
                    "and Exposures) ID, when available.",
                ),
                (
                    _("Reference URLs"),
                    urlize_target_blank(reference_urls_joined),
                    "The URLs collected in VulnerableCodeDB that give you quick "
                    "access to public websites that provide details about a "
                    "vulnerability.",
                ),
                FieldLastLoop,
            ]
        )

        return tab_fields


class ComponentListView(
    AcceptAnonymousMixin,
    AddToProductMultipleMixin,
    DataspacedFilterView,
):
    model = Component
    relation_model = ProductComponent
    add_to_product_perm = "product_portfolio.add_productcomponent"
    template_name = "component_catalog/base_component_package_list.html"
    filterset_class = ComponentFilterSet
    template_list_table = "component_catalog/includes/component_list_table.html"
    include_reference_dataspace = True
    put_results_in_session = True
    paginate_by = settings.PAGINATE_BY or 200
    group_name_version = True

    table_headers = (
        Header("name", _("Component name")),
        Header("version", _("Version")),
        Header("usage_policy", _("Policy"), filter="usage_policy", condition=include_policy),
        Header("license_expression", _("Concluded license"), filter="licenses"),
        Header("primary_language", _("Language"), filter="primary_language"),
        Header("owner", _("Owner")),
        Header("keywords", _("Keywords"), filter="keywords"),
        Header("type", _("Type"), filter="type", condition=include_type),
    )

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .only(
                "name",
                "version",
                "usage_policy",
                "license_expression",
                "primary_language",
                "owner",
                "type",
                "keywords",
                "created_date",
                "last_modified_date",
                "request_count",
                "cpe",
                "dataspace",
            )
            .filter(is_active=True)
            .select_related(
                "usage_policy",
                "owner",
                "type",
                "dataspace",
            )
            .prefetch_related(
                "licenses__usage_policy",
            )
            .with_has_hierarchy()
            .order_by(
                "-last_modified_date",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vulnerablecode = VulnerableCode(self.request.user)

        # The display of vulnerabilities is controlled by the objects Dataspace
        enable_vulnerabilities = all(
            [
                self.dataspace.enable_vulnerablecodedb_access,
                vulnerablecode.is_configured(),
            ]
        )

        if enable_vulnerabilities:
            context["vulnerable_cpes"] = vulnerablecode.get_vulnerable_cpes(
                components=context["object_list"],
            )

        return context


class ComponentDetailsView(
    AcceptAnonymousMixin,
    TabVulnerabilityMixin,
    ObjectDetailsView,
    AddToProductFormMixin,
):
    model = Component
    slug_url_kwarg = ("name", "version")
    template_name = "component_catalog/component_details.html"
    form_class = ComponentAddToProductForm
    add_to_product_perm = "product_portfolio.add_productcomponent"
    show_previous_and_next_object_links = True
    include_reference_dataspace = True
    vulnerability_matching_field = "cpe"
    tabset = {
        "essentials": {
            "fields": [
                "display_name",
                "name",
                "version",
                "owner",
                "owner_name",
                "description",
                "copyright",
                "holder",
                "homepage_url",
                "keywords",
                "primary_language",
                "cpe",
                "project",
                "codescan_identifier",
                "release_date",
                "type",
                "vcs_url",
                "code_view_url",
                "bug_tracking_url",
                "completion_level",
                "urn",
                "dataspace",
            ],
        },
        "notice": {
            "fields": [
                "notice_text",
                "is_license_notice",
                "is_copyright_notice",
                "is_notice_in_codebase",
                "notice_filename",
                "notice_url",
                "website_terms_of_use",
                "dependencies",
            ],
        },
        "owner": {
            "fields": [
                "owner",
                "owner_name",
            ],
        },
        "license": {
            "fields": [
                "license_expression",
                "reference_notes",
                "licenses",
                "licenses_summary",
                "declared_license_expression",
                "declared_license_expression_spdx",
                "other_license_expression",
                "other_license_expression_spdx",
            ],
        },
        "hierarchy": {},
        "subcomponents": {},
        "product_usage": {},
        "packages": {
            "fields": [
                "packages",
            ],
        },
        "activity": {},
        "external_references": {
            "fields": [
                "external_references",
            ],
        },
        "usage_policy": {
            "fields": [
                "usage_policy",
                "guidance",
                "legal_reviewed",
                "approval_reference",
                "distribution_formats_allowed",
                "acceptable_linkages",
                "acceptable",
                "export_restrictions",
                "approved_download_location",
                "approved_community_interaction",
            ],
        },
        "legal": {
            "fields": [
                "license_expression",
                "ip_sensitivity_approved",
                "affiliate_obligations",
                "affiliate_obligation_triggers",
                "legal_comments",
                "sublicense_allowed",
                "express_patent_grant",
                "covenant_not_to_assert",
                "indemnification",
            ],
        },
        "vulnerabilities": {
            "verbose_name": "Vulnerabilities",
        },
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
        """
        Return the full QS of Component limited to the is_active=True only.
        The dataspace scoping is done in the parent class.
        """
        component_prefetch_qs = Component.objects.select_related(
            "dataspace",
            "owner",
        ).prefetch_related(
            "licenses",
        )

        related_children_qs = (
            Subcomponent.objects.select_related(
                "usage_policy",
            )
            .prefetch_related(
                "licenses",
                Prefetch("child", queryset=component_prefetch_qs),
            )
            .annotate(
                child_count=Count("child__children"),
            )
            .order_by(
                "child__name",
                "child__version",
            )
        )

        related_parents_qs = (
            Subcomponent.objects.select_related(
                "usage_policy",
            )
            .prefetch_related(
                "licenses",
                Prefetch("parent", queryset=component_prefetch_qs),
            )
            .annotate(
                parent_count=Count("parent__related_parents"),
            )
            .order_by(
                "parent__name",
                "parent__version",
            )
        )

        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related(
                "type",
                "owner__dataspace",
                "configuration_status",
                "usage_policy",
            )
            .prefetch_related(
                "licenses__category",
                "licenses__usage_policy",
                LicenseAssignedTag.prefetch_for_license_tab(),
                "packages__licenses__usage_policy",
                "external_references",
                Prefetch("related_children", queryset=related_children_qs),
                Prefetch("related_parents", queryset=related_parents_qs),
            )
        )

    def get_tabsets(self):
        self.hide_empty_fields = self.object.dataspace.hide_empty_fields_in_component_details_view
        user = self.request.user
        self.productcomponents = []

        # Product data in Component views are not available to AnonymousUser for security reason
        if user.is_authenticated:
            self.productcomponents = (
                self.object.productcomponents.product_secured(user)
                .select_related(
                    "review_status",
                    "purpose",
                )
                .prefetch_related(
                    "licenses__usage_policy",
                )
            )
        self.related_parents = self.object.related_parents.all()
        self.related_children = self.object.related_children.all()

        return super().get_tabsets()

    def tab_essentials(self):
        obj = self.object
        dataspace = obj.dataspace

        def show_usage_policy(value):
            if dataspace.show_usage_policy_in_user_views and obj.usage_policy_id:
                return True

        def copyright_placeholder(value):
            copyright = value or gettext(COPYRIGHT_PLACEHODLER)
            if copyright == COPYRIGHT_PLACEHODLER:
                return ""  # Empty string if no translation available
            return copyright

        tab_fields = [
            TabField("name"),
            TabField("version"),
            TabField(
                "usage_policy",
                source="get_usage_policy_display_with_icon",
                condition=show_usage_policy,
            ),
            TabField("owner", source="owner.get_absolute_link"),
            TabField("description"),
            TabField("copyright", value_func=copyright_placeholder),
            TabField("holder", condition=bool),
            TabField("homepage_url", value_func=urlize_target_blank),
            TabField("keywords", source="keywords", value_func=lambda x: "\n".join(x)),
            TabField("primary_language"),
            TabField("cpe", condition=bool, value_func=get_cpe_vuln_link),
            TabField("project", condition=bool),
            TabField("codescan_identifier"),
            TabField("release_date"),
            TabField("type"),
            TabField("vcs_url", value_func=urlize_target_blank, condition=bool),
            TabField("code_view_url", value_func=urlize_target_blank, condition=bool),
            TabField("bug_tracking_url", value_func=urlize_target_blank, condition=bool),
            TabField("completion_level", value_func=lambda x: f"{x}%"),
            (_("URN"), self.object.urn_link, URN_HELP_TEXT, None),
            TabField("dataspace"),
        ]

        return {"fields": self.get_tab_fields(tab_fields)}

    def tab_notice(self):
        tab_fields = [
            TabField("notice_text"),
            TabField("is_license_notice"),
            TabField("is_copyright_notice"),
            TabField("is_notice_in_codebase"),
            TabField("notice_filename"),
            TabField("notice_url", value_func=urlize_target_blank),
            TabField("website_terms_of_use"),
            TabField("dependencies", value_func=format_dependencies),
        ]

        fields = self.get_tab_fields(tab_fields)
        # At least 1 value need to be set for the tab to be available.
        if not any([1 for field in fields if field[1]]):
            return

        return {"fields": fields}

    def tab_hierarchy(self):
        if self.related_parents or self.related_children or self.productcomponents:
            template = "component_catalog/tabs/tab_hierarchy.html"
            context = {
                "related_parents": self.related_parents,
                "related_children": self.related_children,
                "productcomponents": self.productcomponents,
                "verbose_name": self.model._meta.verbose_name,
                "verbose_name_plural": self.model._meta.verbose_name_plural,
            }

            return {"fields": [(None, context, None, template)]}

    def tab_subcomponents(self):
        dataspace = self.object.dataspace
        components = []

        for subcomponent in self.related_children:
            fields_data = {
                "child": subcomponent.child,
                "subcomponent": subcomponent,
            }

            if dataspace.show_usage_policy_in_user_views:
                usage_policy = subcomponent.get_usage_policy_display_with_icon()
                if not usage_policy:
                    usage_policy = format_html("&nbsp;")
                fields_data["usage_policy"] = usage_policy

            components.append(fields_data)

        if components:
            subcomponents_fields = [
                (None, components, None, "component_catalog/tabs/tab_subcomponents.html"),
            ]
            return {"fields": subcomponents_fields}

    def tab_product_usage(self):
        template = "component_catalog/tabs/tab_product_usage.html"
        if self.productcomponents:
            return {
                "fields": [
                    (None, self.productcomponents, None, template),
                ]
            }

    def tab_packages(self):
        packages = []
        for package in self.object.packages.all():
            packages.extend(self.get_package_fields(package))

        if packages:
            return {"fields": packages}

    def tab_usage_policy(self):
        if not self.object.dataspace.show_usage_policy_in_user_views:
            return

        tab_fields = [
            TabField("usage_policy", source="get_usage_policy_display_with_icon"),
            (
                _("Usage policy guidelines"),
                getattr(self.object.usage_policy, "guidelines", ""),
                ght(UsagePolicy._meta, "guidelines"),
                None,
            ),
            TabField("guidance"),
            TabField("legal_reviewed"),
            TabField("approval_reference"),
            TabField("distribution_formats_allowed"),
            TabField("acceptable_linkages", value_func=lambda x: "\n".join(x or [])),
            TabField("export_restrictions"),
            TabField("approved_download_location"),
            TabField("approved_community_interaction"),
        ]

        fields = self.get_tab_fields(tab_fields)
        # At least 1 value need to be set for the tab to be available.
        if not any([1 for field in fields if field[1]]):
            return

        return {"fields": fields}

    def tab_legal(self):
        tab_fields = [
            TabField("license_expression", source="license_expression_linked"),
            TabField("ip_sensitivity_approved"),
            TabField("affiliate_obligations"),
            TabField("affiliate_obligation_triggers"),
            TabField("legal_comments"),
            TabField("sublicense_allowed"),
            TabField("express_patent_grant"),
            TabField("covenant_not_to_assert"),
            TabField("indemnification"),
        ]

        fields = self.get_tab_fields(tab_fields)
        # At least 1 value need to be set for the tab to be available.
        if not any([1 for field in fields if field[1] and field[0] != "License expression"]):
            return

        return {"fields": fields}

    def get_vulnerabilities_tab_fields(self, vulnerabilities):
        dataspace = self.object.dataspace
        fields = []
        vulnerabilities_count = 0

        for vulnerability in vulnerabilities:
            vulnerability_fields = self.get_vulnerability_fields(vulnerability, dataspace)
            fields.extend(vulnerability_fields)
            vulnerabilities_count += 1

        return fields, vulnerabilities_count

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["has_change_subcomponent_permission"] = user.has_perm(
            "component_catalog.change_subcomponent"
        )
        context["has_change_package_permission"] = user.has_perm("component_catalog.change_package")
        return context


class BaseAdminActionFormView(FormView):
    model = None
    perm = None

    def dispatch(self, request, *args, **kwargs):
        ids = self.request.GET.get("ids") or self.request.POST.get("ids")
        has_perm = request.user.has_perm(self.perm)

        if not ids or not has_perm:
            raise Http404

        # Check to confirm that the dataspace of the objects being added is
        # equal to the dataspace of the user (and thus the products he is able
        # to edit)
        ids = [id_ for id_ in ids.split(",") if id_]

        if ids:
            for obj in self.model.objects.filter(pk__in=ids):
                if obj.dataspace != request.user.dataspace:
                    messages.error(
                        request,
                        ("The dataspace of the selected objects did " "not match your dataspace."),
                    )
                    return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            "ids": self.request.GET.get("ids") or self.request.POST.get("ids"),
        }

    def get_form_kwargs(self):
        """Inject the request in the Form kwargs."""
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["opts"] = self.model._meta
        context["preserved_filters"] = get_preserved_filters(
            self.request, self.model, parameter_name="_changelist_filters"
        )
        return context

    def get_success_url(self):
        url = super().get_success_url()
        preserved_filters = get_preserved_filters(
            self.request, self.model, parameter_name="_changelist_filters"
        )
        return add_preserved_filters(
            {"preserved_filters": preserved_filters, "opts": self.model._meta}, url
        )


class AddToProductAdminView(LoginRequiredMixin, BaseAdminActionFormView):
    form_class = AddToProductAdminForm
    template_name = "admin/component_catalog/add_to_product.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["model"] = self.model
        kwargs["relation_model"] = self.relation_model
        return kwargs

    def form_valid(self, form):
        created_count, updated_count, unchanged_count = form.save()
        model_name = self.model._meta.model_name
        product_name = form.cleaned_data["product"].name

        msg = f"{created_count} {model_name}(s) added to {product_name}."
        if updated_count:
            msg += f" {updated_count} {model_name}(s) updated on {product_name}."
        if unchanged_count:
            msg += f" {unchanged_count} {model_name}(s) were already assigned."

        messages.success(self.request, msg)
        return super().form_valid(form)


class ComponentAddToProductAdminView(AddToProductAdminView):
    model = Component
    relation_model = ProductComponent
    perm = "product_portfolio.add_productcomponent"
    success_url = reverse_lazy("admin:component_catalog_component_changelist")


class PackageAddToProductAdminView(AddToProductAdminView):
    model = Package
    relation_model = ProductPackage
    perm = "product_portfolio.add_productpackage"
    success_url = reverse_lazy("admin:component_catalog_package_changelist")


class BaseSetPolicyView(LoginRequiredMixin, BaseAdminActionFormView):
    form_class = SetPolicyForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["model_class"] = self.model
        kwargs["policy_attr"] = self.policy_attr
        return kwargs

    def form_valid(self, form):
        policy_count = form.save()
        if policy_count:
            messages.success(self.request, f"{policy_count} usage policies updated.")
        return super().form_valid(form)


class SetComponentPolicyView(BaseSetPolicyView):
    model = Component
    perm = "component_catalog.change_component"
    template_name = "admin/component_catalog/component/set_policy.html"
    success_url = reverse_lazy("admin:component_catalog_component_changelist")
    policy_attr = "policy_from_primary_license"


class SetSubcomponentPolicyView(BaseSetPolicyView):
    model = Subcomponent
    perm = "component_catalog.change_subcomponent"
    template_name = "admin/component_catalog/subcomponent/set_policy.html"
    success_url = reverse_lazy("admin:component_catalog_subcomponent_changelist")
    policy_attr = "policy_from_child_component"


class SetPackagePolicyView(BaseSetPolicyView):
    model = Package
    perm = "component_catalog.change_package"
    template_name = "admin/component_catalog/package/set_policy.html"
    success_url = reverse_lazy("admin:component_catalog_package_changelist")
    policy_attr = "policy_from_primary_license"


PACKAGE_COMPONENTS_HELP = _(
    "The software components associated with packages. A component might reference more than "
    "one package (for example, source and binary packages) but a package is usually only "
    "associated with one component."
)


class AddPackagePermissionMixin:
    def get_context_data(self, **kwargs):
        """Support for List and Details Dataspace related views."""
        context = super().get_context_data(**kwargs)
        user = self.request.user

        is_user_dataspace = True
        if getattr(self, "object", None):
            is_user_dataspace = user.dataspace == self.object.dataspace
        elif hasattr(self, "dataspace"):
            is_user_dataspace = user.dataspace == self.dataspace

        if is_user_dataspace:
            add_package_perm = user.has_perm("component_catalog.add_package")
            context["has_add_package_permission"] = add_package_perm
        return context


class PackageListView(
    AcceptAnonymousMixin,
    AddPackagePermissionMixin,
    AddToProductMultipleMixin,
    DataspacedFilterView,
):
    model = Package
    relation_model = ProductPackage
    add_to_product_perm = "product_portfolio.add_productpackage"
    filterset_class = PackageFilterSet
    template_name = "component_catalog/package_list.html"
    template_list_table = "component_catalog/includes/package_list_table.html"
    include_reference_dataspace = True
    put_results_in_session = True
    table_headers = (
        Header("sortable_identifier", _("Identifier"), Package.identifier_help()),
        Header("usage_policy", _("Policy"), filter="usage_policy", condition=include_policy),
        Header("license_expression", _("Concluded license"), filter="licenses"),
        Header("primary_language", _("Language"), filter="primary_language"),
        Header("filename", _("Download"), help_text="Download link"),
        Header("components", "Components", PACKAGE_COMPONENTS_HELP, "component"),
    )

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .only(
                "uuid",
                "filename",
                "type",
                "namespace",
                "name",
                "version",
                "qualifiers",
                "subpath",
                "usage_policy",
                "download_url",
                "license_expression",
                "primary_language",
                "created_date",
                "last_modified_date",
                "request_count",
                "dataspace",
            )
            .annotate_sortable_identifier()
            .select_related(
                "usage_policy",
            )
            .prefetch_related(
                "licenses__usage_policy",
                "component_set",
            )
            .order_by(
                "-last_modified_date",
            )
        )

    def get_extra_add_urls(self):
        extra_add_urls = super().get_extra_add_urls()
        extra_add_urls.insert(0, ("Add Package form", reverse("component_catalog:package_add")))
        return extra_add_urls

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.user.has_perm("component_catalog.change_component"):
            context["add_to_component_form"] = AddMultipleToComponentForm(self.request)

        vulnerablecode = VulnerableCode(self.request.user)
        # The display of vulnerabilities is controlled by the objects Dataspace
        enable_vulnerabilities = all(
            [
                self.dataspace.enable_vulnerablecodedb_access,
                vulnerablecode.is_configured(),
            ]
        )

        if enable_vulnerabilities:
            packages = context["object_list"]
            context["vulnerable_purls"] = vulnerablecode.get_vulnerable_purls(packages)

        return context

    def post_add_to_component(self, form_class):
        request = self.request

        form = form_class(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            created_count, unchanged_count = form.save()
            component = form.cleaned_data["component"]

            if created_count:
                msg = f'{created_count} package(s) added to "{component}".'
                messages.success(request, msg)
            else:
                msg = f"No new packages were assigned to this {component}."
                messages.warning(request, msg)

            if component.is_active:
                return redirect(f"{component.get_absolute_url()}#packages")
            return redirect(request.path)

        error_msg = f"Error assigning packages to a component.\n{form.errors}"
        messages.error(request, format_html(error_msg))
        return redirect(request.path)

    def post(self, request, *args, **kwargs):
        if request.POST.get("submit-add-to-component-form"):
            if self.request.user.has_perm("component_catalog.change_component"):
                return self.post_add_to_component(AddMultipleToComponentForm)
        return super().post(request, *args, **kwargs)


class PackageDetailsView(
    AcceptAnonymousMixin,
    AddPackagePermissionMixin,
    TabVulnerabilityMixin,
    AddToProductFormMixin,
    ObjectDetailsView,
):
    model = Package
    slug_url_kwarg = "uuid"
    include_reference_dataspace = True
    show_previous_and_next_object_links = True
    template_name = "component_catalog/package_details.html"
    form_class = PackageAddToProductForm
    add_to_product_perm = "product_portfolio.add_productpackage"
    vulnerability_matching_field = "package_url"
    tabset = {
        "essentials": {
            "fields": [
                "package_url",
                "filename",
                "download_url",
                "inferred_url",
                "size",
                "release_date",
                "primary_language",
                "cpe",
                "description",
                "keywords",
                "project",
                "notes",
                "license_expression",
                "dataspace",
            ],
        },
        "license": {
            "fields": [
                "license_expression",
                "reference_notes",
                "licenses",
                "licenses_summary",
                "declared_license_expression",
                "declared_license_expression_spdx",
                "other_license_expression",
                "other_license_expression_spdx",
            ],
        },
        "terms": {
            "fields": [
                "copyright",
                "holder",
                "author",
                "notice_text",
                "dependencies",
            ],
        },
        "urls": {
            "fields": [
                "homepage_url",
                "vcs_url",
                "code_view_url",
                "bug_tracking_url",
                "repository_homepage_url",
                "repository_download_url",
                "api_data_url",
            ],
            "verbose_name": "URLs",
        },
        "checksums": {
            "fields": [
                "md5",
                "sha1",
                "sha256",
                "sha512",
            ],
        },
        "others": {
            "fields": [
                "parties",
                "datasource_id",
                "file_references",
            ],
        },
        "components": {
            "fields": [
                "components",
            ],
        },
        "product_usage": {},
        "activity": {},
        "external_references": {
            "fields": [
                "external_references",
            ],
        },
        "usage_policy": {
            "fields": [
                "usage_policy",
                "guidance",
            ],
        },
        "scan": {},
        "purldb": {
            "verbose_name": "PurlDB",
        },
        "vulnerabilities": {
            "verbose_name": "Vulnerabilities",
        },
        "aboutcode": {
            "verbose_name": "AboutCode",
        },
        "history": {
            "fields": [
                "created_date",
                "created_by",
                "last_modified_date",
                "last_modified_by",
            ],
        },
    }

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated:
            self.object.mark_all_notifications_as_read(user)

        has_change_package_permission = user.has_perm("component_catalog.change_package")
        context_data["has_change_package_permission"] = has_change_package_permission

        # License data is required for the Scan tab "scan to package" license expression fields
        client_data = getattr(self.request, "client_data", {})
        include_all_licenses = all(
            [
                has_change_package_permission,
                self.request.user.dataspace.enable_package_scanning,
                "license_data" not in client_data.keys(),
            ]
        )
        if include_all_licenses:
            all_licenses = License.objects.scope(user.dataspace).filter(is_active=True)
            add_client_data(self.request, license_data=all_licenses.data_for_expression_builder())

        if user.has_perm("component_catalog.change_component"):
            context_data["add_to_component_form"] = AddToComponentForm(
                user, initial={self.model._meta.model_name: self.object}
            )

        return context_data

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "usage_policy",
            )
            .prefetch_related(
                "licenses__category",
                "licenses__usage_policy",
                LicenseAssignedTag.prefetch_for_license_tab(),
                "component_set__packages",
                "component_set__licenses__dataspace",
                "component_set__licenses__usage_policy",
                "external_references",
            )
        )

    def tab_essentials(self):
        essentials_fields = self.get_package_fields(self.object, essential_tab=True)
        return {"fields": essentials_fields}

    def tab_usage_policy(self):
        if not self.object.dataspace.show_usage_policy_in_user_views:
            return

        instance = self.object
        if instance.usage_policy_id and instance.usage_policy.guidelines:
            tab_fields = [
                TabField("usage_policy", source="get_usage_policy_display_with_icon"),
                (
                    _("Usage policy guidelines"),
                    getattr(self.object.usage_policy, "guidelines", ""),
                    ght(UsagePolicy._meta, "guidelines"),
                    None,
                ),
            ]

            return {"fields": self.get_tab_fields(tab_fields)}

    def tab_terms(self):
        tab_fields = [
            TabField("copyright"),
            TabField("notice_text"),
            TabField("holder"),
            TabField("author"),
            TabField("dependencies", value_func=format_dependencies),
        ]

        fields = self.get_tab_fields(tab_fields)
        # At least 1 value need to be set for the tab to be available.
        if not any([1 for field in fields if field[1]]):
            return

        return {"fields": fields}

    def tab_urls(self):
        tab_fields = [
            TabField(field_name, value_func=urlize_target_blank)
            for field_name in self.tabset["urls"]["fields"]
        ]

        fields = self.get_tab_fields(tab_fields)
        # At least 1 value need to be set for the tab to be available.
        if not any([1 for field in fields if field[1]]):
            return

        return {"fields": fields}

    def tab_checksums(self):
        tab_fields = [
            TabField("md5"),
            TabField("sha1"),
            TabField("sha256"),
            TabField("sha512"),
        ]
        return {"fields": self.get_tab_fields(tab_fields)}

    def tab_others(self):
        tab_fields = [
            TabField("parties"),
            TabField("datasource_id"),
            TabField("file_references"),
        ]

        fields = self.get_tab_fields(tab_fields)
        # At least 1 value need to be set for the tab to be available.
        if not any([1 for field in fields if field[1]]):
            return

        return {"fields": fields}

    def tab_product_usage(self):
        user = self.request.user
        # Product data in Package views are not available to AnonymousUser for security reason
        if not user.is_authenticated:
            return

        productpackages = (
            self.object.productpackages.product_secured(user)
            .select_related(
                "review_status",
                "purpose",
            )
            .prefetch_related(
                "licenses__usage_policy",
            )
        )

        template = "component_catalog/tabs/tab_product_usage.html"
        if productpackages:
            return {"fields": [(None, productpackages, None, template)]}

    def tab_scan(self):
        scancodeio = ScanCodeIO(self.request.user)
        scan_tab_display_conditions = [
            self.object.download_url,
            scancodeio.is_configured(),
            self.request.user.dataspace.enable_package_scanning,
            self.is_user_dataspace,
        ]

        if not all(scan_tab_display_conditions):
            return

        # Pass the current request query context to the async request
        tab_view_url = self.object.get_url("tab_scan")
        if full_query_string := self.request.META["QUERY_STRING"]:
            tab_view_url += f"?{full_query_string}"

        template = "tabs/tab_async_loader.html"
        tab_context = {
            "tab_view_url": tab_view_url,
            "tab_object_name": "scan data",
        }
        return {"fields": [(None, tab_context, None, template)]}

    def tab_purldb(self):
        display_tab_purldb = [
            PurlDB(self.request.user).is_configured(),
            self.is_user_dataspace,
            self.request.user.dataspace.enable_purldb_access,
        ]

        if not all(display_tab_purldb):
            return

        # Pass the current request query context to the async request
        tab_view_url = self.object.get_url("tab_purldb")
        if full_query_string := self.request.META["QUERY_STRING"]:
            tab_view_url += f"?{full_query_string}"

        template = "tabs/tab_async_loader.html"
        tab_context = {
            "tab_view_url": tab_view_url,
            "tab_object_name": "PurlDB data",
        }
        return {"fields": [(None, tab_context, None, template)]}

    def tab_aboutcode(self):
        template = "component_catalog/tabs/tab_aboutcode.html"
        context = {
            "about_content": self.object.as_about_yaml(),
            "notice_content": normalize_newlines(self.object.notice_text),
        }

        return {"fields": [(None, context, None, template)]}

    def get_vulnerabilities_tab_fields(self, vulnerabilities):
        dataspace = self.object.dataspace
        fields = []
        vulnerabilities_count = 0

        for entry in vulnerabilities:
            unresolved = entry.get("affected_by_vulnerabilities", [])
            for vulnerability in unresolved:
                vulnerability_fields = self.get_vulnerability_fields(vulnerability, dataspace)
                fields.extend(vulnerability_fields)
                vulnerabilities_count += 1

        return fields, vulnerabilities_count

    @staticmethod
    def readable_date(date):
        if date:
            return date_format(parse_datetime(date), "N j, Y, f A T")

    def post_scan_to_package(self, form_class):
        request = self.request

        form = form_class(
            user=request.user,
            data=self.request.POST,
            instance=self.object,
        )

        if form.is_valid():
            if form.changed_data:
                form.save()
                msg = f'Values for {", ".join(form.changed_data)} assigned to the package.'
                messages.success(request, msg)
            else:
                messages.warning(request, "No new values to assign.")
        else:
            error_msg = f"Error assigning values to the package.\n{form.errors}"
            messages.error(request, format_html(error_msg))

        return redirect(f"{request.path}#essentials")

    def post_add_to_component(self, form_class):
        request = self.request
        form = form_class(user=request.user, data=request.POST)
        if form.is_valid():
            component_package = form.save()
            component = component_package.component
            package = component_package.package
            package_link = package.get_absolute_link()
            msg = format_html('"{}" added to "{}".', package_link, component)
            messages.success(self.request, msg)
            if component.is_active:
                return redirect(f"{component.get_absolute_url()}#packages")
            return redirect(request.path)

        msg = format_html("Error assigning the package to a component.\n{}", form.errors)
        messages.error(request, msg)
        return redirect(request.path)

    def post(self, request, *args, **kwargs):
        if not hasattr(self, "object"):
            self.object = self.get_object()

        if request.POST.get("submit-add-to-component-form"):
            if self.request.user.has_perm("component_catalog.change_component"):
                return self.post_add_to_component(AddToComponentForm)
        if request.POST.get("submit-scan-to-package-form"):
            return self.post_scan_to_package(ScanToPackageForm)
        elif request.POST.get("submit-scan-summary-to-package-form"):
            return self.post_scan_to_package(ScanSummaryToPackageForm)

        return super().post(request, *args, **kwargs)


@login_required
def package_scan_view(request, dataspace, uuid):
    user = request.user
    package = get_object_or_404(Package, uuid=uuid, dataspace=user.dataspace)
    download_url = package.download_url

    scancodeio = ScanCodeIO(request.user)
    if scancodeio.is_configured() and user.dataspace.enable_package_scanning:
        if is_available(download_url):
            # Run the task synchronously to prevent from race condition.
            tasks.scancodeio_submit_scan(
                uris=download_url,
                user_uuid=user.uuid,
                dataspace_uuid=user.dataspace.uuid,
            )
            scancode_msg = "The Package URL was submitted to ScanCode.io for scanning."
            messages.success(request, scancode_msg)
        else:
            scancode_msg = f"The URL {download_url} is not reachable."
            messages.error(request, scancode_msg)

    return redirect(f"{package.details_url}#scan")


@login_required
@require_POST
def package_create_ajax_view(request):
    user = request.user
    if not user.has_perm("component_catalog.add_package"):
        return JsonResponse({"error_message": "Permission denied"}, status=403)

    urls = request.POST.get("download_urls", "").strip().split()
    if not urls:
        return JsonResponse({"error_message": "Missing Download URL"}, status=400)

    created = []
    errors = []
    warnings = []
    scan_msg = ""

    for url in urls:
        try:
            package = Package.create_from_url(url, user)
            created.append(package)
        except PackageAlreadyExistsWarning as warning:
            warnings.append(str(warning))
        except (DataCollectionException, Exception) as error:
            errors.append(str(error))

    redirect_url = reverse("component_catalog:package_list")
    len_created = len(created)

    scancodeio = ScanCodeIO(request.user)
    if scancodeio.is_configured() and user.dataspace.enable_package_scanning:
        # The availability of the each `download_url` is checked in the task.
        tasks.scancodeio_submit_scan.delay(
            uris=[package.download_url for package in created if package.download_url],
            user_uuid=user.uuid,
            dataspace_uuid=user.dataspace.uuid,
        )
        scan_msg = " and submitted to ScanCode.io for scanning"

    if len_created == 1:
        redirect_url = created[0].get_absolute_url()
        messages.success(request, "The Package was successfully created.")
    elif len_created > 1:
        packages = "\n".join([package.get_absolute_link() for package in created])
        msg = f"The following Packages were successfully created{scan_msg}:\n{packages}"
        messages.success(request, format_html(msg))

    if errors:
        messages.error(request, format_html("\n".join(errors)))
    if warnings:
        messages.warning(request, format_html("\n".join(warnings)))

    return JsonResponse({"redirect_url": redirect_url})


@csrf_protect
@require_POST
@login_required
def component_create_ajax_view(request):
    user = request.user

    if not user.has_perm("component_catalog.add_component"):
        return JsonResponse({"error_message": "Permission denied"}, status=403)

    form = ComponentAjaxForm(user, data=request.POST)
    if form.is_valid():
        component = form.save()
        History.log_addition(user, component)

        serialized_data = {
            "id": component.id,
            "object_repr": str(component),
            "license_expression": component.license_expression,
        }
        return JsonResponse({"serialized_data": serialized_data}, status=200)

    else:
        rendered_form = render_crispy_form(form)
        return HttpResponse(rendered_form)


@login_required
def send_scan_data_as_file_view(request, project_uuid, filename):
    if not request.user.dataspace.enable_package_scanning:
        raise Http404

    scancodeio = ScanCodeIO(request.user)
    scan_results_url = scancodeio.get_scan_results_url(project_uuid)
    scan_results = scancodeio.fetch_scan_data(scan_results_url)
    scan_summary_url = scancodeio.get_scan_summary_url(project_uuid)
    scan_summary = scancodeio.fetch_scan_data(scan_summary_url)

    in_memory_zip = io.BytesIO()
    with zipfile.ZipFile(in_memory_zip, "a", zipfile.ZIP_DEFLATED, False) as zipf:
        zipf.writestr(f"{filename}_scan.json", json.dumps(scan_results, indent=2))
        zipf.writestr(f"{filename}_summary.json", json.dumps(scan_summary, indent=2))

    in_memory_zip.seek(0)
    response = FileResponse(in_memory_zip, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}_scan.zip"'
    return response


@login_required
def delete_scan_view(request, project_uuid):
    if not request.user.dataspace.enable_package_scanning:
        raise Http404

    scancodeio = ScanCodeIO(request.user)
    scan_list = scancodeio.fetch_scan_list(uuid=str(project_uuid))

    if not scan_list or scan_list.get("count") != 1:
        raise Http404("Scan not found.")

    scan_detail_url = scancodeio.get_scan_detail_url(project_uuid)
    deleted = scancodeio.delete_scan(scan_detail_url)

    if not deleted:
        raise Http404("Scan could not be deleted.")

    messages.success(request, "Scan deleted.")
    return redirect("component_catalog:scan_list")


class ScanListView(
    LoginRequiredMixin,
    AddPackagePermissionMixin,
    APIWrapperListView,
):
    paginate_by = 50
    template_name = "component_catalog/scan_list.html"
    template_list_table = "component_catalog/includes/scan_list_table.html"

    def dispatch(self, request, *args, **kwargs):
        user = self.request.user
        if user.is_authenticated and not user.dataspace.enable_package_scanning:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        dataspace = user.dataspace

        filters = {
            "page": self.request.GET.get("page"),
        }

        scancodeio = ScanCodeIO(user)
        self.list_data = (
            scancodeio.fetch_scan_list(
                dataspace=dataspace,
                user=user if self.request.GET.get("created_by_me") else None,
                **filters,
            )
            or {}
        )

        return self.list_data.get("results", [])

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        urls = (
            get_package_download_url(project_data) for project_data in context_data["object_list"]
        )

        package_qs = Package.objects.scope(self.request.user.dataspace).filter(
            download_url__in=urls
        )
        packages_by_url = {package.download_url: package for package in package_qs}

        scans = []
        for scan in context_data["object_list"]:
            package_download_url = get_package_download_url(scan)
            package = packages_by_url.get(package_download_url)
            scan["package"] = package
            scan["download_result_url"] = get_scan_results_as_file_url(scan)
            scan["created_date"] = parse_datetime(scan.get("created_date"))
            scan["delete_url"] = reverse("component_catalog:scan_delete", args=[scan.get("uuid")])
            scans.append(scan)

        context_data.update(
            {
                "scans": scans,
            }
        )

        return context_data


@require_POST
@csrf_exempt
def send_scan_notification(request, key):
    try:
        json_data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise Http404

    user_uuid = signing.loads(key)
    if not is_uuid4(user_uuid):
        raise Http404("Provided key is not a valid UUID.")

    user = get_object_or_404(DejacodeUser, uuid=user_uuid)
    dataspace = user.dataspace

    project = json_data.get("project")
    input_sources = project.get("input_sources")
    if not input_sources:
        raise Http404("Missing `input_sources` entry in provided data.")
    download_url = input_sources[0].get("download_url")

    package = get_object_or_404(Package, download_url=download_url, dataspace=user.dataspace)
    description = package.download_url

    run = json_data.get("run")
    scan_status = run.get("status")

    update_package_from_scan = all(
        [
            dataspace.enable_package_scanning,
            dataspace.update_packages_from_scan,
            scan_status.lower() == "success",
        ]
    )

    # Triggers the Package data automatic update from Scan results, if enabled.
    if update_package_from_scan:
        scancodeio = ScanCodeIO(user)
        updated_fields = scancodeio.update_from_scan(package, user)
        if updated_fields:
            description = (
                f'Automatically updated {", ".join(updated_fields)} from scan results\n'
                + description
            )

    notify.send(
        sender=user,
        verb=f"Scan {scan_status}",
        action_object=package,
        recipient=user,
        description=description,
    )

    return JsonResponse({"message": "Notification created"})


class ComponentAddView(
    LicenseDataForBuilderMixin,
    DataspacedCreateView,
):
    model = Component
    form_class = ComponentForm
    permission_required = "component_catalog.add_component"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        package_ids = self.request.GET.get("package_ids")
        package_ids = str_to_id_list(package_ids)

        packages = (
            Package.objects.scope(self.request.user.dataspace)
            .filter(id__in=package_ids)
            .values(
                "id",
                "name",
                "version",
                "description",
                "primary_language",
                "cpe",
                "license_expression",
                "keywords",
                "usage_policy",
                "copyright",
                "holder",
                "notice_text",
                "dependencies",
                "reference_notes",
                "release_date",
                "homepage_url",
                "project",
            )
        )

        initial = {"packages_ids": ",".join([str(entry.pop("id")) for entry in packages])}
        if packages:
            for key in packages[0].keys():
                unique_values = set()
                for entry in packages:
                    value = entry.get(key)
                    if not value:
                        continue
                    if isinstance(value, list):
                        value = ", ".join(value)
                    unique_values.add(value)
                if len(unique_values) == 1:
                    initial[key] = list(unique_values)[0]

        kwargs.update({"initial": initial})

        return kwargs


class ComponentUpdateView(
    LicenseDataForBuilderMixin,
    DataspacedUpdateView,
):
    model = Component
    form_class = ComponentForm
    permission_required = "component_catalog.change_component"
    slug_url_kwarg = ("name", "version")

    def get_success_url(self):
        if not self.object.is_active:
            return reverse("component_catalog:component_list")
        return super().get_success_url()


class PackageAddView(
    LicenseDataForBuilderMixin,
    DataspacedCreateView,
):
    model = Package
    form_class = PackageForm
    permission_required = "component_catalog.add_package"
    template_name = "component_catalog/package_form.html"

    def get_initial(self):
        """Pre-fill the form with initial data from a PurlDB entry or a `package_url`."""
        initial = super().get_initial()

        if purldb_entry := self.get_entry_from_purldb():
            purldb_entry["license_expression"] = purldb_entry.get("declared_license_expression")
            model_fields = [
                field.name
                for field in Package._meta.get_fields()
                # Generic keywords are not supported because of validation
                if field.name != "keywords"
            ]
            initial_from_purldb_entry = {
                field_name: value
                for field_name, value in purldb_entry.items()
                if value not in EMPTY_VALUES and field_name in model_fields
            }
            initial.update(initial_from_purldb_entry)
            messages.info(self.request, "Initial data fetched from PurlDB.")

        elif package_url := self.request.GET.get("package_url", None):
            purl = PackageURL.from_string(package_url)
            package_url_dict = purl.to_dict(encode=True, empty="")
            initial.update(package_url_dict)
            if download_url := purl2url.get_download_url(package_url):
                initial.update({"download_url": download_url})

        return initial

    def get_entry_from_purldb(self):
        user = self.request.user
        purldb = PurlDB(user)
        is_purldb_enabled = all(
            [
                purldb.is_configured(),
                user.dataspace.enable_purldb_access,
            ]
        )

        if not is_purldb_enabled:
            return

        purldb_uuid = self.request.GET.get("purldb_uuid", None)
        package_url = self.request.GET.get("package_url", None)

        if purldb_uuid:
            return purldb.get_package(purldb_uuid)
        elif package_url:
            return purldb.get_package_by_purl(package_url)

    def get_success_message(self, cleaned_data):
        success_message = super().get_success_message(cleaned_data)

        if cleaned_data.get("data_collected"):
            success_message += "\nSHA1, MD5, and Size data collection in progress..."
        if cleaned_data.get("scan_submitted"):
            success_message += (
                "\nThe Package Download URL was submitted to ScanCode.io for scanning."
            )

        return success_message


class PackageUpdateView(
    LicenseDataForBuilderMixin,
    DataspacedUpdateView,
):
    model = Package
    form_class = PackageForm
    permission_required = "component_catalog.change_package"
    slug_url_kwarg = "uuid"
    template_name = "component_catalog/package_form.html"


class PackageTabScanView(AcceptAnonymousMixin, TabContentView):
    model = Package
    slug_url_kwarg = "uuid"
    template_name = "component_catalog/tabs/tab_scan.html"
    detected_package_data = {}

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.dataspace.enable_package_scanning:
            raise Http404("Package scanning is not enabled.")

        has_change_package_permission = user.has_perm("component_catalog.change_package")
        context_data["has_change_package_permission"] = has_change_package_permission

        tab_scan = self.tab_scan()
        if tab_scan:
            context_data["tab_context"] = normalize_tab_fields(tab_scan)
        else:
            context_data["show_scan_package_btn"] = True

        if has_change_package_permission:
            context_data["scan_summary_to_package_form"] = ScanSummaryToPackageForm(
                user=user,
                instance=self.object,
            )

            # Needs to be placed after the `tab_scan()` call so
            # self.detected_package_data is set
            if self.detected_package_data:
                context_data["scan_to_package_form"] = ScanToPackageForm(
                    user=user,
                    initial=self.detected_package_data,
                    instance=self.object,
                )

        return context_data

    @staticmethod
    def _cleanup_braces(value):
        """Escapes `{` and `}` to prevent issues when applying format_html() functions."""
        return value.replace("{", "&lbrace;").replace("}", "&rbrace;")

    @classmethod
    def _generate_license_match_card(cls, path, detection_data):
        if "/" in path:
            location, filename = path.rsplit("/", 1)
            path_for_display = f"{location}/<strong>{filename}</strong>"
        else:
            path_for_display = f"<strong>{path}</strong>"
        path_for_display = cls._cleanup_braces(path_for_display)

        html_content = ""
        for detection_entry in detection_data:
            for match in detection_entry.get("matches", []):
                matched_text = match.get("matched_text")
                matched_text = escape(matched_text)
                matched_text = cls._cleanup_braces(matched_text)
                match_license_expression = match.get("license_expression")
                html_content += f"""
                <div class="card-header py-1 border-top border-bottom-0">
                    Detected: <span class="fw-bold">{match_license_expression}</span>
                </div>
                <div class="card-body pb-0 pt-2">
                    <pre class="mb-2"><code>{matched_text}</code></pre>
                </div>
                """

        return f"""
            <div class="card mb-3">
              <div class="card-header">
                <i class="far fa-file-alt me-1"></i> {path_for_display}
              </div>
              {html_content}
            </div>
            """

    @staticmethod
    def _get_licensing_for_formatted_render(dataspace, license_expressions):
        # Get the set of unique license symbols as an optimization
        # to filter the License QuerySet to relevant objects.
        license_keys = set()
        for entry in license_expressions:
            expression = entry.get("value")
            if expression:
                license_keys.update(get_unique_license_keys(expression))

        show_policy = dataspace.show_usage_policy_in_user_views
        licensing = get_licensing_for_formatted_render(dataspace, show_policy, license_keys)

        return licensing, show_policy

    @classmethod
    def get_license_expressions_scan_values(
        cls, dataspace, license_expressions, input_type, license_matches, checked=False
    ):
        licensing, show_policy = cls._get_licensing_for_formatted_render(
            dataspace, license_expressions
        )
        values = []
        for entry in license_expressions:
            license_expression = entry.get("value")
            if not license_expression:
                continue

            value = get_formatted_expression(licensing, license_expression, show_policy)
            count = entry.get("count")
            checked_html = "checked" if checked else ""
            select_input = (
                f'<input type="{input_type}" name="license_expression" '
                f'value="{license_expression}" {checked_html}>'
            )

            if count:
                html_content = (
                    f"{select_input} {value}"
                    f' <span class="badge text-bg-secondary rounded-pill">{count}</span>'
                )
            else:
                html_content = f"{select_input} {value}"

            # Warning: The ``count`` from the summary is not directly correlated with
            # the number of ``matched_text``.
            match_data = ""
            matches = license_matches.get(license_expression, {})
            for path, detection_data in matches.items():
                match_data += cls._generate_license_match_card(path, detection_data)

            if match_data:
                html_content += (
                    f'<button type="button"'
                    f' class="btn btn-primary badge text-bg-primary rounded-pill ms-1"'
                    f' data-bs-toggle="modal" '
                    f' data-bs-target="#scan-matches-modal"'
                    f' data-license-key="{license_expression}"'
                    f' data-matches="{escape(match_data)}">'
                    f' <i class="far fa-file-alt"></i>'
                    f"</button>"
                )

            values.append(f'<span class="license-expression">{html_content}</span>')

        return values

    @staticmethod
    def license_clarity_fields(license_clarity_score):
        if not license_clarity_score:
            return []

        field_context = {
            "pretitle": "License Clarity",
            "help_text": "License Clarity is a set of metrics that indicate how clearly, "
            "comprehensively and accurately a software project has defined "
            "and communicated the licensing that applies to the software.",
        }
        tab_fields = [
            (None, field_context, None, "includes/field_pretitle.html"),
        ]

        table = []
        for label, field, help_text, weight in ScanCodeIO.LICENSE_CLARITY_FIELDS:
            field_value = license_clarity_score.get(field, "")
            td_class = "text-center"
            th_class = None

            if field_value is True:
                badge_color = "text-bg-success" if weight.startswith("+") else "text-bg-danger"
                value = f'<span class="badge {badge_color} fs-85pct">{weight}</span>'

            elif field == "score":
                td_class += " bg-body-tertiary"
                th_class = "bg-body-tertiary"
                badge_color = "text-bg-primary"
                value = f'<span class="badge {badge_color} fs-85pct">{field_value}</span>'

            else:
                value = ""

            table.append(
                {
                    "label": label,
                    "value": format_html(value),
                    "help_text": help_text,
                    "td_class": td_class,
                    "th_class": th_class,
                }
            )

        tab_fields.append((None, table, None, "includes/field_table.html"))
        return tab_fields

    @staticmethod
    def get_key_file_summary(key_file_data):
        dt = '<dt class="col-sm-2 text-end pt-2 pe-0">{}</dt>'
        dd = '<dd class="col-sm-10"><pre class="pre-bg-body-tertiary mb-1">{}</pre></dd>'
        summary = ""

        for label, field, value_key in ScanCodeIO.KEY_FILE_DETECTION_FIELDS:
            values = key_file_data.get(field)
            if not values:
                continue

            if isinstance(values, list):
                if isinstance(values[0], dict):
                    values = [value.get(value_key) for value in values]
            else:
                values = [values]

            values = [
                f'{escape(value)} <span class="badge text-bg-secondary rounded-pill">{count}</span>'
                for value, count in Counter(values).items()
            ]
            summary += dt.format(label)
            summary += dd.format("\n".join(values))

        return summary

    def key_files_fields(self, key_files):
        if not key_files:
            return []

        field_context = {
            "pretitle": "Key files",
            "help_text": "Key files are top-level codebase files such as "
            "COPYING, README and package manifests",
        }

        for key_file in key_files:
            key_file["summary"] = self.get_key_file_summary(key_file)

            # Inject the matched values as a grouped list for usage in the template
            # Limit the matched_text to 300 chars to prevent rendering issues.
            MATCHED_MAX_LENGTH = 300
            license_detections = key_file.get("license_detections", [])

            matched_texts = []
            for detection_data in license_detections:
                for match in detection_data.get("matches"):
                    matched_text = match.get("matched_text")
                    if matched_text and len(matched_text) < MATCHED_MAX_LENGTH:
                        matched_texts.append(matched_text)

            key_file_fields = [
                ("copyrights", "copyright"),
                ("holders", "holder"),
                ("authors", "author"),
            ]
            for field, value_field in key_file_fields:
                matched_texts += [
                    escape(entry.get(value_field))
                    for entry in key_file.get(field, [])
                    if len(entry.get(value_field)) < MATCHED_MAX_LENGTH
                ]

            key_file["matched_texts"] = matched_texts

            if detected_license_expression := key_file["detected_license_expression"]:
                licensing, show_policy = self._get_licensing_for_formatted_render(
                    self.object.dataspace, [{"value": detected_license_expression}]
                )
                key_file["formatted_expression"] = get_formatted_expression(
                    licensing,
                    detected_license_expression,
                    show_policy,
                    show_category=True,
                )

        tab_fields = [
            (None, field_context, None, "includes/field_pretitle.html"),
            ("", key_files, None, "component_catalog/tabs/field_key_files_table.html"),
        ]

        return tab_fields

    def github_repo_url_field(self):
        github_repo_url = self.object.github_repo_url
        if github_repo_url:
            field_context = {
                "href": github_repo_url,
                "target": "_blank",
                "icon_class": "fas fa-external-link-alt",
                "btn_class": "btn-sm float-end",
            }
            return "View code repository", field_context, None, "includes/field_button.html"

    def scan_detected_package_fields(self, key_files_packages):
        user = self.request.user
        has_change_package_permission = user.has_perm("component_catalog.change_package")
        detected_package_fields = []

        for detected_package in key_files_packages[:1]:  # Only 1 package entry is supported
            has_package_values = any(
                [field[1] in detected_package for field in ScanCodeIO.SCAN_PACKAGE_FIELD]
            )
            if not has_package_values:
                continue

            right_button_data_target = ""
            if has_change_package_permission:
                right_button_data_target = "#scan-to-package-modal"

            field_context = {
                "pretitle": "Detected Package",
                "help_text": (
                    "A normalized top-level package manifest, if available, that contains "
                    "package metadata such as a name, version, etc.\n"
                    "Package manifests include files such as npm's <code>package.json</code>, "
                    "Apache Maven <code>pom.xml</code>, RPM or Debian metadata, etc. "
                    "that contain structured information about a package."
                ),
                "right_button_data_target": right_button_data_target,
            }
            detected_package_fields.append(
                (None, field_context, None, "includes/field_pretitle.html")
            )

            self.detected_package_data = ScanCodeIO.map_detected_package_data(detected_package)

            # Add the supported Package fields in the tab UI.
            for label, scan_field in ScanCodeIO.SCAN_PACKAGE_FIELD:
                if scan_field == "declared_license_expression":
                    scan_field = "license_expression"
                value = self.detected_package_data.get(scan_field)
                if value:
                    if isinstance(value, list):
                        value = format_html("<br>".join(([escape(entry) for entry in value])))
                    else:
                        value = escape(value)
                    detected_package_fields.append((label, value))

            detected_package_fields.append(FieldSeparator)

        return detected_package_fields

    def scan_summary_fields(self, scan_summary):
        scan_summary_fields = []
        user = self.request.user
        has_change_package_permission = user.has_perm("component_catalog.change_package")

        right_button_data_target = ""
        if has_change_package_permission:
            right_button_data_target = "#scan-summary-to-package-modal"

        summary_pretitle_context = {
            "pretitle": "Scan Summary",
            "help_text": (
                "A top-level summary of the collected scanned data such as license expressions, "
                "copyright statements and copyright holders.\n"
                "For each value the summary has a count of the occurrences of a data item."
            ),
            "right_button_data_target": right_button_data_target,
        }

        summary_fields = ScanCodeIO.SCAN_SUMMARY_FIELDS
        has_summary_values = any(field[1] in scan_summary for field in summary_fields)
        if not has_summary_values:
            return

        scan_summary_fields.append(
            (None, summary_pretitle_context, None, "includes/field_pretitle.html")
        )
        license_matches = scan_summary.get("license_matches") or {}
        self.object.has_license_matches = bool(license_matches)

        for label, field, model_field_name, input_type in summary_fields:
            field_data = scan_summary.get(field, [])
            if field in ("declared_license_expression", "other_license_expressions"):
                if field == "declared_license_expression":
                    field_data = [{"value": field_data, "count": None}]
                    checked = True
                else:
                    checked = False
                values = self.get_license_expressions_scan_values(
                    user.dataspace, field_data, input_type, license_matches, checked
                )

            elif field in ("declared_holder", "primary_language"):
                values = []
                if field_data:
                    values.append(
                        f'<input type="{input_type}" name="{model_field_name}" '
                        f'value="{escape(field_data)}" checked> {escape(field_data)}'
                    )

            else:
                values = [
                    (
                        f'<input type="{input_type}" name="{model_field_name}"'
                        f' value="{escape(entry.get("value"))}">'
                        f' {escape(entry.get("value"))}'
                        f' <span class="badge text-bg-secondary rounded-pill">{entry.get("count")}'
                        f"</span>"
                    )
                    for entry in field_data
                    if entry.get("value")
                ]

            scan_summary_fields.append((label, format_html("\n".join(values))))

        scan_summary_fields.append(FieldSeparator)
        return scan_summary_fields

    @staticmethod
    def readable_date(date):
        if date:
            return date_format(parse_datetime(date), "N j, Y, f A T")

    def scan_status_fields(self, scan):
        scan_status_fields = []
        scan_run = scan.get("runs", [{}])[-1]
        status = scan_run.get("status")
        issue_statuses = ["failure", "stale", "stopped"]
        completed_statuses = ["success", *issue_statuses]

        scan_issue_request_template = settings.SCAN_ISSUE_REQUEST_TEMPLATE
        dataspace_name = self.object.dataspace.name
        request_template_uuid = scan_issue_request_template.get(dataspace_name)
        if request_template_uuid and status in completed_statuses:
            request_form_url = reverse("workflow:request_add", args=[request_template_uuid])
            field_context = {
                "href": f"{request_form_url}?content_object_id={self.object.id}",
                "target": "_blank",
                "btn_class": "btn-outline-request",
                "icon_class": "fas fa-bug",
            }
            scan_status_fields.append(
                ("Report Scan Issues", field_context, None, "includes/field_button.html")
            )

        scan_status_fields.extend(
            [
                ("Status", f"Scan {status}"),
                ("Created date", self.readable_date(scan_run.get("created_date"))),
                ("Start date", self.readable_date(scan_run.get("task_start_date"))),
                ("End date", self.readable_date(scan_run.get("task_end_date"))),
                ("ScanCode.io version", scan_run.get("scancodeio_version")),
            ]
        )

        if status in issue_statuses:
            log = scan_run.get("log")
            if log:
                scan_status_fields.append(("Log", log, None, "includes/field_log.html"))
            task_output = scan_run.get("task_output")
            if task_output:
                scan_status_fields.append(
                    ("Task output", task_output, None, "includes/field_log.html")
                )

        if status == "success":
            filename = self.object.filename or self.object.package_url_filename
            field_context = {
                "href": reverse(
                    "component_catalog:scan_data_as_file",
                    args=[scan.get("uuid"), quote_plus(filename)],
                ),
                "target": "_blank",
                "icon_class": "fas fa-download",
            }
            scan_status_fields.append(
                ("Download Scan data", field_context, None, "includes/field_button.html")
            )

        return scan_status_fields

    def tab_scan(self):
        user = self.request.user
        scancodeio = ScanCodeIO(user)

        scan = scancodeio.get_scan_results(
            download_url=self.object.download_url,
            dataspace=user.dataspace,
        )

        if not scan:
            return

        summary_url = scan.get("url").split("?")[0] + "summary/"
        scan_summary = scancodeio.fetch_scan_data(summary_url)

        tab_fields = []

        github_repo_url_field = self.github_repo_url_field()
        if github_repo_url_field:
            tab_fields.append(github_repo_url_field)

        if scan_summary:
            license_clarity_score = scan_summary.get("license_clarity_score")
            license_clarity_fields = self.license_clarity_fields(license_clarity_score)
            tab_fields.extend(license_clarity_fields)

            key_files = scan_summary.get("key_files")
            key_files_fields = self.key_files_fields(key_files)
            if key_files_fields:
                tab_fields.extend(key_files_fields)

            if key_files_packages := scan_summary.get("key_files_packages", []):
                tab_fields.extend(self.scan_detected_package_fields(key_files_packages))

            scan_summary_fields = self.scan_summary_fields(scan_summary)
            if scan_summary_fields:
                tab_fields.extend(scan_summary_fields)

        scan_status_fields = self.scan_status_fields(scan)
        if scan_status_fields:
            tab_fields.extend(scan_status_fields)

        return {"fields": tab_fields}


class PackageTabPurlDBView(AcceptAnonymousMixin, TabContentView):
    model = Package
    slug_url_kwarg = "uuid"
    template_name = "tabs/tab_content.html"

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.dataspace.enable_purldb_access:
            raise Http404("PurlDB access is not enabled.")

        if tab_fields := self.get_tab_fields():
            context_data["tab_context"] = normalize_tab_fields(tab_fields)
        else:
            alert_context = {
                "message": "No entries found in the PurlDB for this package.",
                "full_width": True,
                "alert_class": "alert-light disable-tab",
            }
            tab_fields = [("", alert_context, None, "includes/field_alert.html")]
            context_data["tab_context"] = {"fields": tab_fields}

        return context_data

    def get_tab_fields(self):
        from purldb.views import get_purldb_tab_fields

        purldb_entries = self.object.get_purldb_entries(
            user=self.request.user,
            max_request_call=1,
            timeout=5,
        )
        if not purldb_entries:
            return

        tab_fields = []

        alert_context = {
            "message": (
                "You are looking at the details for this software package as defined "
                "in the PurlDB which was mined and scanned automatically from a public "
                "source."
            ),
            "full_width": True,
            "alert_class": "alert-primary",
        }
        tab_fields.append(("", alert_context, None, "includes/field_alert.html"))

        if len(purldb_entries) > 1:
            alert_context = {
                "message": "There are multiple entries in the PurlDB for this Package.",
                "full_width": True,
                "alert_class": "alert-warning",
            }
            tab_fields.append(("", alert_context, None, "includes/field_alert.html"))

        user = self.request.user
        for purldb_entry in purldb_entries:
            tab_fields.extend(get_purldb_tab_fields(purldb_entry, user.dataspace))

        return {"fields": tab_fields}
