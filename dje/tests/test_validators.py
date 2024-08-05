#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.exceptions import ValidationError
from django.test import TestCase

from dje.validators import generic_uri_validator


class DJEValidatorsTestCase(TestCase):
    def test_generic_uri_validator(self):
        valid_values = [
            "http://a",
            "https://a",
            "git://a",
            "git+https://a",
            "git-https://a",
            "git_https://a",
            "https://github.com/django/django.git",
            "git://codeaurora.org/quic/qsdk/oss/boot/bootdrv"
            "@528551389b5979010764aba410a240344e1f8458ec47ff32b",
        ]

        invalid_values = [
            "",
            " ",
            "http ://a",
            "git://",
            "git@github.com:django/django.git",
            "git:///bootdrv@5285513 89b59",
        ]

        for value in valid_values:
            try:
                generic_uri_validator(value)
            except ValidationError:
                self.fail("{} raised when validating '{}'".format(ValidationError.__name__, value))

        for value in invalid_values:
            try:
                generic_uri_validator(value)
            except ValidationError:
                pass
            else:
                self.fail(
                    "{} not raised when validating '{}'".format(ValidationError.__name__, value)
                )
