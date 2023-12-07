#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from license_library.languages import LANG_INFO


class LicenseLibraryConfig(AppConfig):
    name = "license_library"
    verbose_name = _("License Library")
    languages = [
        (language["code"], language["name"])
        for language in LANG_INFO.values()
        if language.get("code") and language.get("name")
    ]
