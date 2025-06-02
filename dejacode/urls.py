#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.template.loader import render_to_string
from django.urls import path
from django.views.defaults import page_not_found
from django.views.generic import RedirectView
from django.views.generic import TemplateView

from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from notifications.views import mark_all_as_read
from rest_framework.routers import DefaultRouter

from component_catalog.api import ComponentViewSet
from component_catalog.api import KeywordViewSet
from component_catalog.api import PackageViewSet
from component_catalog.api import SubcomponentViewSet
from component_catalog.views import send_scan_notification
from dje import two_factor
from dje.admin import dejacode_site
from dje.api import ExternalReferenceViewSet
from dje.forms import DejaCodeAuthenticationForm
from dje.registration import DejaCodeActivationView
from dje.registration import DejaCodeRegistrationForm
from dje.views import AccountProfileView
from dje.views import AllNotificationsList
from dje.views import DataspaceAwareAutocompleteLookup
from dje.views import DataspaceAwareRelatedLookup
from dje.views import GlobalSearchListView
from dje.views import IntegrationsStatusView
from dje.views import UnreadNotificationsList
from dje.views import home_view
from dje.views import index_dispatch
from dje.views import urn_resolve_view
from license_library.api import LicenseAnnotationViewSet
from license_library.api import LicenseViewSet
from organization.api import OwnerViewSet
from policy.api import UsagePolicyViewSet
from product_portfolio.api import CodebaseResourceViewSet
from product_portfolio.api import ProductComponentViewSet
from product_portfolio.api import ProductDependencyViewSet
from product_portfolio.api import ProductPackageViewSet
from product_portfolio.api import ProductViewSet
from reporting.api import ReportViewSet
from vulnerabilities.api import VulnerabilityAnalysisViewSet
from vulnerabilities.api import VulnerabilityViewSet
from workflow.api import RequestTemplateViewSet
from workflow.api import RequestViewSet

# Replace the default admin site with the DejaCode one.
admin.site = dejacode_site


# Restframework API
api_router = DefaultRouter()
api_router.register("owners", OwnerViewSet)
api_router.register("licenses", LicenseViewSet)
api_router.register("license_annotations", LicenseAnnotationViewSet)
api_router.register("components", ComponentViewSet)
api_router.register("subcomponents", SubcomponentViewSet)
api_router.register("keywords", KeywordViewSet)
api_router.register("packages", PackageViewSet)
api_router.register("products", ProductViewSet)
api_router.register("product_components", ProductComponentViewSet)
api_router.register("product_dependencies", ProductDependencyViewSet)
api_router.register("product_packages", ProductPackageViewSet)
api_router.register("codebase_resources", CodebaseResourceViewSet)
api_router.register("request_templates", RequestTemplateViewSet)
api_router.register("requests", RequestViewSet)
api_router.register("reports", ReportViewSet)
api_router.register("external_references", ExternalReferenceViewSet)
api_router.register("usage_policies", UsagePolicyViewSet)
api_router.register("vulnerabilities", VulnerabilityViewSet)
api_router.register("vulnerability_analyses", VulnerabilityAnalysisViewSet)


urlpatterns = [
    path("", index_dispatch, name="index_dispatch"),
    path("home/", home_view, name="home"),
    path("integrations_status/", IntegrationsStatusView.as_view(), name="integrations_status"),
    path("account/", include("django.contrib.auth.urls")),
    path("account/profile/", AccountProfileView.as_view(), name="account_profile"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path(
        "login/",
        two_factor.LoginView.as_view(
            authentication_form=DejaCodeAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    # Activation and password views are required for the user creation flow.
    # registration_activation_complete needs to be register before registration_activate
    # so the 'complete/' segment is not caught as the activation_key
    path(
        "account/activate/complete/",
        TemplateView.as_view(template_name="django_registration/activation_complete.html"),
        name="django_registration_activation_complete",
    ),
    path(
        "account/activate/<str:activation_key>/",
        DejaCodeActivationView.as_view(),
        name="django_registration_activate",
    ),
    # Two-factor authentication
    path("account/2fa/enable/", two_factor.EnableView.as_view(), name="account_2fa_enable"),
    path("account/2fa/disable/", two_factor.DisableView.as_view(), name="account_2fa_disable"),
    path("account/2fa/verify/", two_factor.VerifyView.as_view(), name="account_2fa_verify"),
    path("urn/", urn_resolve_view, name="urn_resolve"),
    path("urn/<urn>/", urn_resolve_view, name="urn_resolve"),
    path("admin/", dejacode_site.urls),
    # Grappelli does not have a hook for replacing the ``RelatedLookup`` view
    # class so we hijack the url used by that view and use our own version of
    # ``RelatedLookup``.  The same is done for ``AutocompleteLookup``.
    path(
        "grappelli/lookup/related/",
        DataspaceAwareRelatedLookup.as_view(),
        name="grp_related_lookup",
    ),
    path(
        "grappelli/lookup/autocomplete/",
        DataspaceAwareAutocompleteLookup.as_view(),
        name="grp_autocomplete_lookup",
    ),
    # Disable Grappelli's M2M lookup.
    path("grappelli/lookup/m2m/", page_not_found, name="grp_m2m_lookup"),
    # This need to be registered after the overrides.
    path("grappelli/", include("grappelli.urls")),
    path("favicon.ico", RedirectView.as_view(url="/static/img/favicon.ico", permanent=True)),
]

urlpatterns += [
    path("licenses/", include(("license_library.urls", "license_library"))),
    path("", include(("component_catalog.urls", "component_catalog"))),
    path("products/", include(("product_portfolio.urls", "product_portfolio"))),
    path("owners/", include(("organization.urls", "organization"))),
    path("requests/", include(("workflow.urls", "workflow"))),
    path("reports/", include(("reporting.urls", "reporting"))),
    path("vulnerabilities/", include(("vulnerabilities.urls", "vulnerabilities"))),
    path("global_search/", GlobalSearchListView.as_view(), name="global_search"),
]

notification_patterns = [
    path("", UnreadNotificationsList.as_view(), name="unread"),
    path("all/", AllNotificationsList.as_view(), name="all"),
    path("mark_all_as_read/", mark_all_as_read, name="mark_all_as_read"),
    path(
        "send_scan_notification/<str:key>/", send_scan_notification, name="send_scan_notification"
    ),
]

urlpatterns += [
    path("notifications/", include((notification_patterns, "notifications"))),
]

urlpatterns += [
    path("purldb/", include(("purldb.urls", "purldb"))),
]

api_docs_view = get_schema_view(
    openapi.Info(
        title="DejaCode REST API",
        default_version="v2",
        description=render_to_string(
            "rest_framework/docs/description.html",
            context={"site_url": settings.SITE_URL.rstrip("/")},
        ),
    ),
    public=False,
)

# TODO: Force login_required on all API documentation URLs.
# for doc_url in api_docs_urls[0]:
#     doc_url.callback = login_required(doc_url.callback)
api_docs_patterns = [
    path("", api_docs_view.with_ui("redoc", cache_timeout=0), name="docs-index"),
]

urlpatterns += [
    path("api/v2/", include((api_router.urls, "api_v2"))),
    path("api/v2/docs/", include((api_docs_patterns, "api-docs"))),
]

if settings.ENABLE_SELF_REGISTRATION:
    from django_registration.backends.activation.views import RegistrationView

    urlpatterns += [
        path(
            "account/register/",
            RegistrationView.as_view(form_class=DejaCodeRegistrationForm),
            name="django_registration_register",
        ),
        path("account/", include("django_registration.backends.activation.urls")),
    ]

if settings.DEBUG and settings.DEBUG_TOOLBAR:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
