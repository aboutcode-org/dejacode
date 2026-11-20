#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from dje.widgets import DropDownWidget


class WidgetsTestCase(TestCase):
    def test_widgets_dropdown_widget_render_option_escapes_label(self):
        widget = DropDownWidget()
        widget.data = {}

        option = widget.render_option("status", [], "1", "<b>Label</b>")
        self.assertEqual(
            '<a href="?status=1" class="dropdown-item">&lt;b&gt;Label&lt;/b&gt;</a>', option
        )
