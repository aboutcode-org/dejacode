#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings

from dejacode import __version__ as DEJACODE_VERSION


def dejacode_context(request):
    """Return all the DejaCode specific context variables."""
    return {
        "DEJACODE_VERSION": DEJACODE_VERSION,
        "FAVICON_HREF": settings.FAVICON_HREF,
        "SITE_TITLE": settings.SITE_TITLE,
        "HEADER_TEMPLATE": settings.HEADER_TEMPLATE,
        "FOOTER_TEMPLATE": settings.FOOTER_TEMPLATE,
        "SHOW_PP_IN_NAV": settings.SHOW_PP_IN_NAV,
        "SHOW_TOOLS_IN_NAV": settings.SHOW_TOOLS_IN_NAV,
        "AXES_ENABLED": settings.AXES_ENABLED,
        "LOGIN_FORM_ALERT": settings.LOGIN_FORM_ALERT,
    }
