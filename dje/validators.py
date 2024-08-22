#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import re

from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

validate_url_segment = validators.RegexValidator(
    re.compile(r'^[ .a-zA-Z0-9!#"\':,&()+_-]+$'),
    _("Enter a valid value consisting of spaces, periods, letters, numbers, or !#\"':,&()+_-."),
    "invalid",
)

# Similar to validate_url_segment minus the colon `:`
validate_version = validators.RegexValidator(
    re.compile(r'^[ .a-zA-Z0-9!#"\',&()+_-]+$'),
    _("Enter a valid value consisting of spaces, periods, letters, numbers, or !#\"',&()+_-."),
    "invalid",
)

generic_uri_validator = validators.RegexValidator(
    re.compile(r"^[\w+-_]+://[\S]+$"),
    message=_("Enter a valid URI."),
    code="invalid",
)


def validate_list(value):
    if not isinstance(value, list):
        raise ValidationError(_('Enter a valid list: ["item1", "item2"]'), code="invalid_list")


class SpecialCharacterPasswordValidator:
    """Validate whether the password contains one special character."""

    SPECIAL_CHARS = "!?*@#$%^&+~=,.:;_/(){}<>\\-"

    def validate(self, password, user=None):
        if not re.search(r"(?=.*[{}])".format(self.SPECIAL_CHARS), password):
            raise ValidationError(
                self.get_help_text(),
                code="password_special_char",
            )

    def get_help_text(self):
        return _("Your password must contain at least one special character.")
