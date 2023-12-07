#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from os.path import dirname
from os.path import join

from django.test import TestCase
from django.urls import reverse

from bleach._vendor import html5lib

from dje.models import Dataspace
from dje.tests import create_superuser


class HTMLValidationTestCase(TestCase):
    # Do not use the following, it makes the CommandsTestCase to run twice.
    # fixtures = CommandsTestCase.fixtures

    testfiles_location = join(dirname(__file__), "testfiles")
    # Taken from CommandsTestCase.fixtures
    fixtures = [
        join(testfiles_location, "test_dataset_user_only.json"),
        join(testfiles_location, "test_dataset_organization_only.json"),
        join(testfiles_location, "test_dataset_ll_only.json"),
        join(testfiles_location, "test_dataset_cc_only.json"),
        join(testfiles_location, "test_dataset_pp_only.json"),
        join(testfiles_location, "test_dataset_workflow.json"),
    ]

    def setUp(self):
        nexb_dataspace = Dataspace.objects.get(name="nexB")
        self.super_user = create_superuser("superuser", nexb_dataspace)

    def test_html5_validity(self):
        self.client.login(username=self.super_user.username, password="secret")

        # Only simple User available URLs, admin validity is not critical.
        # We should eventually collect all the possible URLs.
        urls = [
            "index_dispatch",  # redirection
            # 'logout',  # redirection and requires re-login
            "home",
            "urn_resolve",
            "global_search",
            "license_library:license_list",
            ("license_library:license_details", "nexB", "license1"),
            "component_catalog:component_list",
            ("component_catalog:component_details", "nexB", "AES", "12th September 2011"),
            ("component_catalog:component_details", "nexB", "Zlib", "1.2.5"),
            "component_catalog:package_list",
            ("component_catalog:package_details", "nexB", "b91a9a06-b709-45a4-ac8e-a57bde0c8f38"),
            "product_portfolio:product_list",
            ("product_portfolio:product_details", "nexB", "Starship Widget Framework", "7.1"),
            ("product_portfolio:product_attribution", "nexB", "Starship Widget Framework", "7.1"),
            "organization:owner_list",
            ("organization:owner_details", "nexB", "Test Organization"),
            "password_reset",
            "password_reset_done",
            "password_reset_complete",
            "password_change",
            "password_change_done",
            "account_profile",
        ]

        from django.contrib.contenttypes.models import ContentType

        from dje.models import Dataspace
        from workflow.models import Request
        from workflow.models import RequestTemplate

        request_template = RequestTemplate.objects.all()[:1].get()
        ct = ContentType.objects.get(app_label="component_catalog", model="component")
        request = Request.objects.create(
            title="Title",
            request_template=request_template,
            dataspace=Dataspace.objects.get(),
            requester=self.super_user,
            content_type=ct,
        )
        urls.extend(
            [
                "workflow:request_list",
                ("workflow:request_add", request_template.uuid),
                ("workflow:request_details", request.uuid),
            ]
        )

        for url in urls:
            args = None
            if isinstance(url, tuple):
                url, args = url[0], url[1:]

            response = self.client.get(reverse(url, args=args), follow=True)
            parser = html5lib.HTMLParser()
            parser.parse(response.content)
            if parser.errors:
                raise self.failureException(f'Invalid HTML for "{url}"')
