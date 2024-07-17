#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime

from django.test import TestCase
from django.utils import timezone

from dje.models import Dataspace
from dje.templatetags.dje_tags import naturaltime_short
from dje.templatetags.dje_tags import urlize_target_blank
from dje.tests import create_superuser
from organization.models import Owner


class URNResolverTestCase(TestCase):
    def setUp(self):
        self.dataspace1 = Dataspace.objects.create(name="Dataspace")
        self.owner1 = Owner.objects.create(
            name="CCAD - Combined Conditional Access Development, LLC.", dataspace=self.dataspace1
        )

    def test_organization_get_urn(self):
        expected = "urn:dje:owner:CCAD+-+Combined+Conditional+Access+Development%2C+LLC."
        self.assertEqual(expected, self.owner1.urn)

    def test_org_urns_with_colons_in_name_are_valid_urns(self):
        org = Owner.objects.create(name="some:org", dataspace=self.dataspace1)
        self.assertEqual("urn:dje:owner:some%3Aorg", org.urn)


class MiddlewareTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.super_user = create_superuser("nexb_user", self.dataspace)

    def test_prohibit_in_query_string_middleware(self):
        response = self.client.get("/?a=%00", follow=True)
        self.assertEqual(404, response.status_code)

        self.client.login(username=self.super_user.username, password="secret")
        response = self.client.get("/?a=%00")
        self.assertEqual(404, response.status_code)


class TemplateTagsTestCase(TestCase):
    def test_dje_templatetag_urlize_target_blank_template_tag(self):
        inputs = [
            (
                "domain.com",
                '<a target="_blank" href="http://domain.com" rel="nofollow">domain.com</a>',
            ),
            (
                "http://domain.com",
                '<a target="_blank" href="http://domain.com" rel="nofollow">http://domain.com</a>',
            ),
            (
                "https://domain.com",
                '<a target="_blank" href="https://domain.com" rel="nofollow">'
                "https://domain.com"
                "</a>",
            ),
            (
                "ftp://domain.com",
                '<a target="_blank" href="ftp://domain.com" rel="noreferrer nofollow">'
                "ftp://domain.com</a>",
            ),
        ]

        for url, expected in inputs:
            self.assertEqual(expected, urlize_target_blank(url))

    def test_dje_templatetag_naturaltime_short(self):
        now = timezone.now()

        test_list = [
            "test",
            now,
            now - datetime.timedelta(microseconds=1),
            now - datetime.timedelta(seconds=1),
            now - datetime.timedelta(seconds=30),
            now - datetime.timedelta(minutes=1, seconds=30),
            now - datetime.timedelta(minutes=2),
            now - datetime.timedelta(hours=1, minutes=30, seconds=30),
            now - datetime.timedelta(hours=23, minutes=50, seconds=50),
            now - datetime.timedelta(days=1),
            now - datetime.timedelta(days=40),
            now - datetime.timedelta(days=80),
            now - datetime.timedelta(days=500),
        ]
        result_list = [
            "test",
            "now",
            "now",
            "a second ago",
            "30\xa0seconds ago",
            "a minute ago",
            "2\xa0minutes ago",
            "an hour ago",
            "23\xa0hours ago",
            "1\xa0day ago",
            "1\xa0month ago",
            "2\xa0months ago",
            "1\xa0year ago",
        ]

        for value, expected in zip(test_list, result_list):
            self.assertEqual(expected, naturaltime_short(value))
