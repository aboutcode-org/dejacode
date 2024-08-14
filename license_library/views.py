#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import FileResponse
from django.template.defaultfilters import force_escape
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView

from dje.client_data import add_client_data
from dje.templatetags.dje_tags import urlize_target_blank
from dje.urn_resolver import URN_HELP_TEXT
from dje.utils import get_help_text as ght
from dje.views import AcceptAnonymousMixin
from dje.views import AdminLinksDropDownMixin
from dje.views import DataspacedFilterView
from dje.views import DataspaceScopeMixin
from dje.views import Header
from dje.views import ObjectDetailsView
from dje.views import TabField
from license_library.filters import LicenseFilterSet
from license_library.models import License
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseProfile
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from policy.models import UsagePolicy


def include_license_type(view_instance):
    return view_instance.dataspace.show_license_type_in_license_list_view


def include_license_profile(view_instance):
    return view_instance.dataspace.show_license_profile_in_license_list_view


def include_policy(view_instance):
    return view_instance.dataspace.show_usage_policy_in_user_views


LICENSE_NAME_HELP = _(
    "The full name of the license, as provided by the original authors, along with the "
    "commonly used license short name and the license key required by license expressions."
)


class LicenseListView(
    AcceptAnonymousMixin,
    AdminLinksDropDownMixin,
    DataspacedFilterView,
):
    model = License
    filterset_class = LicenseFilterSet
    template_name = "license_library/license_list.html"
    template_list_table = "license_library/includes/license_list_table.html"
    include_reference_dataspace = True
    put_results_in_session = True
    table_headers = (
        Header("name", _("License name"),
               help_text=LICENSE_NAME_HELP, filter="in_spdx_list"),
        Header("usage_policy", _("Policy"),
               filter="usage_policy", condition=include_policy),
        Header("category", _("Category"), filter="category"),
        Header(
            "category__license_type",
            _("Type"),
            ght(LicenseCategory._meta, "license_type"),
            filter="category__license_type",
            condition=include_license_type,
        ),
        Header(
            "license_profile",
            _("License profile"),
            filter="license_profile",
            condition=include_license_profile,
        ),
        Header("owner", _("Owner")),
    )

    def get_queryset(self):
        # This QuerySet is not evaluated, but used in the following Prefetch().
        assigned_tags_qs = (
            LicenseAssignedTag.objects.filter(
                license_tag__show_in_license_list_view=True)
            # Warning: This ordering needs to be the same as in license_tags_to_display
            .order_by("license_tag__label")
        )

        qs = (
            super()
            .get_queryset()
            .only(
                "name",
                "short_name",
                "key",
                "spdx_license_key",
                "usage_policy",
                "category",
                "license_profile",
                "owner",
                "request_count",
                "dataspace",
            )
            .filter(is_active=True)
            .select_related(
                "license_profile",
                "category",
                "owner",
                "dataspace",
                "usage_policy",
            )
            .prefetch_related(Prefetch("licenseassignedtag_set", queryset=assigned_tags_qs))
        )

        return qs

    @cached_property
    def license_tags_to_display(self):
        return LicenseTag.objects.scope(self.dataspace).filter(show_in_license_list_view=True)

    def get_table_headers(self):
        headers = super().get_table_headers()

        tag_headers = [
            Header(tag.get_slug_label(), tag.label, tag.text)
            for tag in self.license_tags_to_display
        ]

        return headers[:-1] + tag_headers + headers[-1:]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        categories = LicenseCategory.objects.scope(
            self.dataspace).values_list("id", "text")
        add_client_data(self.request, license_categories=dict(categories))

        context["text_search"] = self.request.GET.get("text_search", "")

        if self.request.user.is_superuser:
            context["show_license_policy_dump_link"] = True

        return context


class LicenseDetailsView(
    AcceptAnonymousMixin,
    ObjectDetailsView,
):
    model = License
    slug_url_kwarg = "key"
    template_name = "license_library/license_details.html"
    show_previous_and_next_object_links = True
    use_annotator = False
    include_reference_dataspace = True
    tabset = {
        "essentials": {
            "fields": [
                "key",
                "name",
                "short_name",
                "is_exception",
                "guidance",
                "guidance_url",
                "reference_notes",
                "attribution_required",
                "redistribution_required",
                "change_tracking_required",
                "category",
                "license_profile",
                "license_style",
                "owner",
                "spdx_license_key",
                "keywords",
                "standard_notice",
                "special_obligations",
                "publication_year",
                "language",
                "urn",
                "dataspace",
            ],
        },
        "license_text": {
            "fields": [
                "full_text",
            ],
        },
        "license_conditions": {
            "fields": [
                "tags",
            ],
        },
        "urls": {
            "verbose_name": _("URLs"),
            "fields": [
                "homepage_url",
                "text_urls",
                "osi_url",
                "faq_url",
                "guidance_url",
                "other_urls",
            ],
        },
        "owner": {
            "fields": [
                "owner",
                "owner_name",
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
            ],
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
        Return the full QS of License objects.
        We are not limiting the QS to is_active license so we can
        access the details view for Component licenses.
        The dataspace scoping is done in the parent class.
        """
        return (
            super()
            .get_queryset()
            .select_related(
                "license_profile",
                "license_style",
                "owner",
            )
            .prefetch_related(
                "licenseassignedtag_set__license_tag",
                "external_references",
            )
        )

    def get_tabsets(self):
        self.license_tagset = self.object.get_tagset()
        return super().get_tabsets()

    def tab_essentials(self):
        obj = self.object
        opts = obj._meta
        dataspace = obj.dataspace

        def show_usage_policy(value):
            if dataspace.show_usage_policy_in_user_views and obj.usage_policy_id:
                return True

        tab_fields = [
            TabField("key"),
            TabField("name"),
            TabField("short_name"),
            TabField(
                "usage_policy",
                source="get_usage_policy_display_with_icon",
                condition=show_usage_policy,
            ),
            TabField("is_exception", condition=bool),
            TabField("guidance", value_func=force_escape, condition=bool),
            TabField("guidance_url", value_func=urlize_target_blank,
                     condition=bool),
            TabField("reference_notes",
                     value_func=urlize_target_blank, condition=bool),
        ]

        if obj.attribution_required:
            help_text = (
                "When true (checked), indicates that the license has at least one License "
                "Tag that requires attribution in the source code or the documentation "
                "of the product where the licensed software is being used, or both."
            )
            tab_fields.append(
                (_("Attribution required"), True,
                 help_text, "includes/boolean_icon.html")
            )

        if obj.redistribution_required:
            help_text = (
                "When true (checked), indicates that the license has at least one License "
                "Tag that requires the product documentation to include instructions "
                "regarding how to obtain source code for the licensed software, including "
                "any modifications to it."
            )
            tab_fields.append(
                (_("Redistribution required"), True,
                 help_text, "includes/boolean_icon.html")
            )

        if obj.change_tracking_required:
            help_text = (
                "When true (checked), indicates that the license has at least one License "
                "Tag that requires any modifications to licensed software to be documented "
                "in the source code, the associated product documentation, or both."
            )
            tab_fields.append(
                (_("Change tracking required"), True,
                 help_text, "includes/boolean_icon.html")
            )

        tab_fields.extend(
            [
                TabField("category"),
                (
                    _("License type"),
                    getattr(obj.category, "license_type", None),
                    ght(LicenseCategory._meta, "license_type"),
                    None,
                ),
                TabField("license_profile"),
                TabField("license_style"),
                TabField("owner", source="owner.get_absolute_link"),
                (_("SPDX short identifier"), obj.spdx_link,
                 ght(opts, "spdx_license_key"), None),
                TabField("keywords"),
                TabField("standard_notice"),
                TabField("special_obligations", value_func=force_escape),
                TabField("publication_year"),
                TabField("language", source="get_language_display",
                         condition=bool),
                (_("URN"), self.object.urn_link, URN_HELP_TEXT, None),
                TabField("dataspace"),
            ]
        )

        return {"fields": self.get_tab_fields(tab_fields)}

    def tab_license_text(self):
        obj = self.object
        opts = obj._meta

        if self.is_user_dataspace and self.license_tagset and obj.annotations.exists():
            self.use_annotator = True

        license_text_context = {
            "license_text": force_escape(obj.full_text),
            "use_annotator": self.use_annotator,
        }

        return {
            "fields": [
                (
                    None,
                    license_text_context,
                    ght(opts, "full_text"),
                    "license_library/tabs/tab_license_text.html",
                ),
            ]
        }

    def tab_license_conditions(self):
        if self.license_tagset:
            return {
                "fields": [
                    (None, self.license_tagset, None,
                     "license_library/tabs/tab_tagset.html")
                ]
            }

    def tab_urls(self):
        tab_fields = [
            TabField("homepage_url", value_func=urlize_target_blank),
            TabField("text_urls", value_func=urlize_target_blank),
            TabField("osi_url", value_func=urlize_target_blank),
            TabField("faq_url", value_func=urlize_target_blank),
            TabField("guidance_url", value_func=urlize_target_blank),
            TabField("other_urls", value_func=urlize_target_blank),
        ]

        return {"fields": self.get_tab_fields(tab_fields)}

    def tab_usage_policy(self):
        if not self.object.dataspace.show_usage_policy_in_user_views:
            return

        instance = self.object
        if instance.usage_policy_id and instance.usage_policy.guidelines:
            tab_fields = [
                TabField("usage_policy",
                         source="get_usage_policy_display_with_icon"),
                (
                    _("Usage policy guidelines"),
                    getattr(self.object.usage_policy, "guidelines", ""),
                    ght(UsagePolicy._meta, "guidelines"),
                    None,
                ),
            ]

            return {"fields": self.get_tab_fields(tab_fields)}

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        if self.use_annotator:
            context_data["use_annotator"] = True
            annotations_qs = self.object.annotations.order_by(
                "range_start_offset")

            add_client_data(
                self.request,
                license_pk=self.object.pk,
                api_url=reverse("api_v2:api-root"),
                # Force the QuerySet into a proper list to be handled in JavaScript.
                annotation_pks=list(
                    annotations_qs.values_list("pk", flat=True)),
            )

        return context_data


class LicenseStyleDetailView(
    LoginRequiredMixin,
    DataspaceScopeMixin,
    DetailView,
):
    """
    Admin view that Return a LicenseStyle object details.
    Used in the License changeform view in a pop-in.
    """

    model = LicenseStyle
    context_object_name = "licensestyle"
    template_name = "admin/license_library/licensestyle_detail.html"


class LicenseProfileDetailView(
    LoginRequiredMixin,
    DataspaceScopeMixin,
    DetailView,
):
    """
    Admin view that Return a LicenseProfile object details.
    Used in the License changeform view in a pop-in.
    """

    model = LicenseProfile
    template_name = "admin/license_library/tagset_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["tags"] = [
            {
                "value": tag.value,
                "label": tag.license_tag.label,
                "text": tag.license_tag.text,
            }
            for tag in self.object.licenseprofileassignedtag_set.all()
        ]
        return context


class LicenseDownloadTextView(ObjectDetailsView):
    model = License
    slug_url_kwarg = "key"

    def get(self, request, *args, **kwargs):
        license = self.get_object()
        response = FileResponse(license.full_text, content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="{license.key}.LICENSE"'
        return response
