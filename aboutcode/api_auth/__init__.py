#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import secrets

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.translation import gettext_lazy as _

from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class AbstractAPIToken(models.Model):
    """
    API token using a lookup prefix and PBKDF2 hash for secure verification.

    The full key is never stored. Only a short plain-text prefix is kept for
    DB lookup, and a hashed version of the full key is stored for verification.
    The plain key is returned once at generation time and must be stored safely
    by the client.
    """

    PREFIX_LENGTH = 8

    key_hash = models.CharField(
        max_length=128,
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="api_token",
        on_delete=models.CASCADE,
    )
    prefix = models.CharField(
        max_length=PREFIX_LENGTH,
        unique=True,
        db_index=True,
    )
    created = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"APIToken {self.prefix}... ({self.user})"

    @classmethod
    def generate_key(cls):
        """Generate a plain (not encrypted) key."""
        return secrets.token_hex(32)

    @classmethod
    def create_token(cls, user):
        """Generate a new token for the given user and return the plain key once."""
        plain_key = cls.generate_key()
        prefix = plain_key[: cls.PREFIX_LENGTH]
        cls.objects.create(
            user=user,
            prefix=prefix,
            key_hash=make_password(plain_key),
        )
        return plain_key

    @classmethod
    def verify(cls, plain_key):
        """Return the token instance if the plain key is valid, None otherwise."""
        if not plain_key:
            return

        prefix = plain_key[: cls.PREFIX_LENGTH]
        token = cls.objects.filter(prefix=prefix).select_related("user").first()

        if token and check_password(plain_key, token.key_hash):
            return token

    @classmethod
    def regenerate(cls, user):
        """Delete any existing token instance for the user and generate a new one."""
        cls.objects.filter(user=user).delete()
        return cls.create_token(user)


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

        try:
            return django_apps.get_model(settings.API_TOKEN_MODEL)
        except (ValueError, LookupError):
            raise ImproperlyConfigured("API_TOKEN_MODEL must be of the form 'app_label.model_name'")

    def authenticate_credentials(self, plain_key):
        model = self.get_model()
        token = model.verify(plain_key)

        if token is None:
            raise AuthenticationFailed(_("Invalid token."))

        if not token.user.is_active:
            raise AuthenticationFailed(_("User inactive or deleted."))

        return (token.user, token)
