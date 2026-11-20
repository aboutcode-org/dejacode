#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from types import SimpleNamespace

from django.test import TestCase

from dje.list_display import AsJoinList


class ListDisplayTestCase(TestCase):
    def test_list_display_as_join_list_escapes_values(self):
        list_display_item = AsJoinList("keywords", "<br>")
        instance = SimpleNamespace(keywords=["one", "<img src=x>"])

        self.assertEqual("one<br>&lt;img src=x&gt;", list_display_item(instance))
