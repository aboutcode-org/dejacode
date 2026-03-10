#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect
from django.utils.html import format_html
from django.views.generic import View


class BaseAPIKeyActionView(View):
    """Base view for API key management actions."""

    success_url = None
    success_message = ""

    def get_success_url(self):
        if not self.success_url:
            raise ImproperlyConfigured("No URL to redirect to. Provide a success_url.")
        return str(self.success_url)

    def get_success_message(self, **kwargs):
        if kwargs:
            return format_html(self.success_message, **kwargs)
        return self.success_message

    def post(self, request, *args, **kwargs):
        raise NotImplementedError


class BaseGenerateAPIKeyView(BaseAPIKeyActionView):
    """Generate a new API key and display it once via a success message."""

    def post(self, request, *args, **kwargs):
        plain_key = request.user.regenerate_api_key()
        messages.success(request, self.get_success_message(plain_key=plain_key))
        return redirect(self.get_success_url())


class BaseRevokeAPIKeyView(BaseAPIKeyActionView):
    """Revoke the current user's API key."""

    def post(self, request, *args, **kwargs):
        request.user.revoke_api_key()
        messages.success(request, self.get_success_message())
        return redirect(self.get_success_url())
