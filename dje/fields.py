#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import zoneinfo
from datetime import datetime

from django import forms
from django.conf import settings
from django.db import models
from django.template.defaultfilters import filesizeformat
from django.utils.text import normalize_newlines
from django.utils.translation import gettext_lazy as _

from dje.tasks import send_mail_to_admins_task
from dje.validators import validate_list


class NoStripTextField(models.TextField):
    """
    TextField without the default stripping.
    Also normalize CRLF and CR newlines to just LF.
    """

    def formfield(self, **kwargs):
        kwargs["strip"] = False
        return super().formfield(**kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        return normalize_newlines(value)


class ExtendedNullBooleanSelect(forms.widgets.NullBooleanSelect):
    """
    Custom widget to extend the supported values for `BooleanField.null=True`.
    This need to be done at the widget level as a non-supported value from `data`
    will be `None` from the `value_from_datadict` output.
    Everything else will be considered Unknown (`NULL` in the database).
    """

    def value_from_datadict(self, data, files, name):
        value = data.get(name, None)
        return {
            "on": True,
            "2": True,
            True: True,
            "True": True,
            "3": False,
            "False": False,
            False: False,
            # Extended values for 'True'
            "true": True,
            "t": True,
            "T": True,
            "yes": True,
            "Yes": True,
            "y": True,
            "Y": True,
            # Extended values for 'False'
            "false": False,
            "f": False,
            "F": False,
            "no": False,
            "No": False,
            "n": False,
            "N": False,
        }.get(value, None)


class ExtendedBooleanCheckboxInput(forms.widgets.CheckboxInput):
    def value_from_datadict(self, data, files, name):
        value = data.get(name, None)
        return {
            "on": True,
            True: True,
            "1": True,
            "True": True,
            "true": True,
            "t": True,
            "T": True,
            "yes": True,
            "Yes": True,
            "y": True,
            "Y": True,
            False: False,
            "0": False,
            "False": False,
            "false": False,
            "f": False,
            "F": False,
            "no": False,
            "No": False,
            "n": False,
            "N": False,
        }.get(value, None)


class SmartFileField(forms.FileField):
    """
    A smarter file field with these extra features:

    - Limit file upload by size and/or extensions.
    - Run a anti-virus scan if CLAMD_ENABLED is activiated.

    If `max_upload_size` is not provided, the MAX_UPLOAD_SIZE settings is used.

    Note that we cannot trust the file content_type since it is supplied by the user.
    https://docs.djangoproject.com/en/dev/ref/files/uploads/
    """

    def __init__(self, *args, **kwargs):
        self.max_upload_size = kwargs.pop("max_upload_size", None)
        if not self.max_upload_size:
            self.max_upload_size = settings.MAX_UPLOAD_SIZE
        self.extensions = kwargs.pop("extensions", [])
        super().__init__(*args, **kwargs)

    def clean(self, *args, **kwargs):
        uploaded_file = super().clean(*args, **kwargs)
        if self.extensions and not uploaded_file.name.endswith(tuple(self.extensions)):
            raise forms.ValidationError(_("File extension not supported."))

        if self.max_upload_size and uploaded_file.size > self.max_upload_size:
            raise forms.ValidationError(
                _(
                    "File size must be under {}. Current file size is {}.".format(
                        filesizeformat(self.max_upload_size), filesizeformat(uploaded_file.size)
                    )
                )
            )

        if settings.CLAMD_ENABLED:
            self.scan_file_for_virus(uploaded_file)

        return uploaded_file

    @staticmethod
    def scan_file_for_virus(file):
        """Run a ClamAV scan on the uploaded file to detect virus infection."""
        import clamd

        if settings.CLAMD_USE_TCP:
            clamd_socket = clamd.ClamdNetworkSocket(settings.CLAMD_TCP_ADDR)
        else:
            clamd_socket = clamd.ClamdUnixSocket()

        try:
            scan_response = clamd_socket.instream(file)
        except clamd.ClamdError:
            subject = "[DejaCode] Clamd Error"
            message = "Error with the ClamAV setup. Make sure the service is properly running."
            send_mail_to_admins_task.delay(subject, message)
            raise forms.ValidationError(
                _("File upload disabled at the moment. Please contact your administrator.")
            )
        except BrokenPipeError:
            raise forms.ValidationError(_("File size is too large."))

        for status, reason in scan_response.values():
            if status == "FOUND":
                raise forms.ValidationError(_("This file is infected. Upload aborted."))
            elif status == "ERROR":
                raise forms.ValidationError(_("File upload error."))


class LastModifiedByField(models.ForeignKey):
    def __init__(self, *args, **kwargs):
        help_text = _("The application user who last modified the object.")

        kwargs.update(
            {
                "to": settings.AUTH_USER_MODEL,
                "on_delete": kwargs.get("on_delete", models.PROTECT),
                "related_name": kwargs.get("related_name", "modified_%(class)ss"),
                "null": True,
                "editable": False,
                "serialize": False,
                "help_text": kwargs.get("help_text", help_text),
            }
        )
        super().__init__(*args, **kwargs)


class JSONListField(models.JSONField):
    """
    Store a list of values in a JSONField.

    The value "list" is set as the default and validation is applied to ensure
    that the provided value is a valid JSON list.
    """

    description = _("A JSON list object")
    empty_values = [list()]
    default_error_messages = {
        "invalid_list": _('Value must be valid JSON list: ["item1", "item2"].'),
    }
    _default_hint = ("list", "[]")
    default_validators = [validate_list]

    def __init__(self, *args, **kwargs):
        kwargs["default"] = list
        super().__init__(*args, **kwargs)


class TimeZoneChoiceField(forms.ChoiceField):
    """Field for selecting time zones, displaying human-readable names with offsets."""

    STANDARD_TIMEZONE_NAMES = {
        "America/Argentina": "Argentina Standard Time",
        "America/Indiana": "Indiana Time",
        "America/Kentucky": "Kentucky Time",
        "America/North_Dakota": "North Dakota Time",
    }

    def __init__(self, *args, **kwargs):
        choices = [("", "Select Time Zone")]
        timezone_groups = {}

        # Collect timezones with offsets
        for tz in sorted(zoneinfo.available_timezones()):
            skip_list = ("Etc/GMT", "GMT", "PST", "CST", "EST", "MST", "UCT", "UTC", "WET", "MET")
            if tz.startswith(skip_list):
                continue

            offset_hours, formatted_offset = self.get_timezone_offset(tz)
            standard_name, city = self.get_timezone_parts(tz)

            formatted_name = f"{formatted_offset}"
            if standard_name:
                formatted_name += f" {standard_name} - {city}"
            else:
                formatted_name += f" {city}"

            if offset_hours not in timezone_groups:
                timezone_groups[offset_hours] = []
            timezone_groups[offset_hours].append((tz, formatted_name))

        # Sort within each offset group and compile final sorted choices
        sorted_offsets = sorted(timezone_groups.keys())  # Sort by GMT offset
        for offset in sorted_offsets:
            for tz, formatted_name in sorted(timezone_groups[offset], key=lambda x: x[1]):
                choices.append((tz, formatted_name))

        kwargs["choices"] = choices
        super().__init__(*args, **kwargs)

    @staticmethod
    def get_timezone_offset(tz):
        """Return the numeric offset for sorting and formatted offset for display."""
        tz_info = zoneinfo.ZoneInfo(tz)
        now = datetime.now(tz_info)
        offset_seconds = now.utcoffset().total_seconds()
        offset_hours = offset_seconds / 3600

        # Format offset as GMT+XX:XX or GMT-XX:XX
        sign = "+" if offset_hours >= 0 else "-"
        hours = int(abs(offset_hours))
        minutes = int((abs(offset_hours) - hours) * 60)
        formatted_offset = f"(GMT{sign}{hours:02}:{minutes:02})"

        return offset_hours, formatted_offset

    @classmethod
    def get_standard_timezone_name(cls, tz):
        """Return a human-friendly standard timezone name if available."""
        for key in cls.STANDARD_TIMEZONE_NAMES:
            if tz.startswith(key):
                return cls.STANDARD_TIMEZONE_NAMES[key]

        if default := tz.split("/")[0]:
            return default

    @classmethod
    def get_timezone_parts(cls, tz):
        """Extract standard timezone name and city for display."""
        parts = tz.split("/")
        region = "/".join(parts[:-1])  # Everything except last part
        city = parts[-1].replace("_", " ")  # City with spaces

        # Get human-readable timezone name
        standard_name = cls.get_standard_timezone_name(region)

        return standard_name, city
