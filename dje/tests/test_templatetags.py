#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime

from django.test import TestCase
from django.utils import timezone

from dje.templatetags.dje_tags import naturaltime_short
from dje.templatetags.dje_tags import urlize_target_blank


class TemplateTagsTestCase(TestCase):
    def test_dje_templatetags_urlize_target_blank_template_tag(self):
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

    def test_dje_templatetags_naturaltime_short(self):
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
