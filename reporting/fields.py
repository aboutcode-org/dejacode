#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime

from django.forms.widgets import Select
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

import dateutil


class BooleanSelect(Select):
    """
    A Select Widget intended to be used with BooleanField.
    Added the 'All' choice.
    """

    ALL_CHOICE_VALUE = "ALL"

    def __init__(self, attrs=None, choices=()):
        choices = (("0", _("All")), ("2", _("Yes")), ("3", _("No")))
        super().__init__(attrs, choices)

    def render(self, name, value, attrs=None, renderer=None):
        try:
            value = {True: "2", "True": "2", False: "3", "False": "3", "2": "2", "3": "3"}[value]
        except KeyError:
            value = "0"
        return super().render(name, value, attrs, renderer)

    def value_from_datadict(self, data, files, name):
        value = data.get(name, None)
        return {
            "2": True,
            True: True,
            "True": True,
            "3": False,
            "False": False,
            False: False,
            "0": self.ALL_CHOICE_VALUE,
        }.get(value, None)


class NullBooleanSelect(Select):
    """
    A Select Widget intended to be used with BooleanField.null=True.
    Added the 'All' choice.
    """

    def __init__(self, attrs=None, choices=()):
        choices = (("0", _("All")), ("1", _("Unknown")), ("2", _("Yes")), ("3", _("No")))
        super().__init__(attrs, choices)

    def render(self, name, value, attrs=None, renderer=None):
        converted_value = {
            "None": "1",
            True: "2",
            "True": "2",
            False: "3",
            "False": "3",
            "2": "2",
            "3": "3",
        }.get(value, "0")
        return super().render(name, converted_value, attrs, renderer)

    def value_from_datadict(self, data, files, name):
        value = data.get(name, None)
        return {
            "1": "None",
            "2": True,
            True: True,
            "True": True,
            "3": False,
            "False": False,
            False: False,
        }.get(value, None)


DATE_FILTER_CHOICES = (
    ("any_date", _("Any Date")),
    ("today", _("Today")),
    ("past_7_days", _("Past 7 days")),
    ("past_30_days", _("Past 30 days")),
    ("past_90_days", _("Past 90 days")),
)


class DateFieldFilterSelect(Select):
    """
    Filter to be used with the gte lookup.
    Inspired by django.contrib.admin.filters.DateFieldListFilter
    """

    def __init__(self, attrs=None, choices=()):
        super().__init__(attrs, choices=DATE_FILTER_CHOICES)

    @staticmethod
    def _get_today():
        """Get today's date at midnight in the current timezone."""
        return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

    def render(self, name, value, attrs=None, renderer=None):
        if not value:
            # Force an Exception, empty string Return today in the parser
            value = "ERROR"

        try:
            value_as_date = dateutil.parser.parse(value)
            # Make the parsed datetime timezone-aware to match "today" value
            if timezone.is_naive(value_as_date):
                value_as_date = timezone.make_aware(value_as_date)
        except Exception:
            value = "any_date"
        else:
            today = self._get_today()
            if value_as_date >= today:
                value = "today"
            elif value_as_date >= today - datetime.timedelta(days=7):
                value = "past_7_days"
            elif value_as_date >= today - datetime.timedelta(days=30):
                value = "past_30_days"
            elif value_as_date >= today - datetime.timedelta(days=90):
                value = "past_90_days"

        return super().render(name, value, attrs, renderer)

    def value_from_datadict(self, data, files, name):
        value = data.get(name, None)
        today = self._get_today()

        return {
            "today": str(today),
            "past_7_days": str(today - datetime.timedelta(days=7)),
            "past_30_days": str(today - datetime.timedelta(days=30)),
            "past_90_days": str(today - datetime.timedelta(days=90)),
        }.get(value, None)
