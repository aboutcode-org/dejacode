#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.utils.translation import gettext_lazy as _

from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from aboutcode.api_auth.models import get_api_token_model


class APITokenAuthentication(TokenAuthentication):
    """
    Token authentication using a hashed API token for secure verification.

    Extends Django REST Framework's TokenAuthentication, replacing the plain-text lookup
    with a prefix-based lookup and PBKDF2 hash verification.
    """

    model = None

    def get_model(self):
        if self.model is not None:
            return self.model
        return get_api_token_model()

    def authenticate_credentials(self, plain_key):
        model = self.get_model()
        token = model.verify(plain_key)

        if token is None:
            raise AuthenticationFailed(_("Invalid token."))

        if not token.user.is_active:
            raise AuthenticationFailed(_("User inactive or deleted."))

        return (token.user, token)
