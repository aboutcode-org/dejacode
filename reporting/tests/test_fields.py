#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime

from django.test import TestCase

from reporting.fields import DateFieldFilterSelect


class ReportingFieldsTestCase(TestCase):
    def test_reporting_date_field_filter_select_render(self):
        widget = DateFieldFilterSelect()

        for choice_value in ["today", "past_7_days", "past_30_days", "past_90_days"]:
            value = widget.value_from_datadict({"value": choice_value}, files=None, name="value")
            html = widget.render("value", value)
            self.assertIn(f'<option value="{choice_value}" selected>', html)

        naive_date = str(widget._get_today().date() - datetime.timedelta(days=3))
        html = widget.render("value", naive_date)
        self.assertIn('<option value="past_7_days" selected>', html)

        for invalid_value in [None, "", "not a date"]:
            html = widget.render("value", invalid_value)
            self.assertIn('<option value="any_date" selected>', html)
