#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from django_auth_ldap.backend import LDAPBackend
from django_auth_ldap.backend import _LDAPUser

from dje.models import Dataspace


class DejaCodeLDAPBackend(LDAPBackend):
    def get_or_build_user(self, username, ldap_user):
        """
        Add a new option AUTH_LDAP_AUTOCREATE_USER with default value True.

        When AUTH_LDAP_AUTOCREATE_USER is True the behavior does not change.
        An existing Dataspace name needs to be set in AUTH_LDAP_DATASPACE.

        When AUTH_LDAP_AUTOCREATE_USER is False, an AuthenticationFailed
        is raised if the user does not exist as a Django User, even once the
        authentication with LDAP was correct.
        """
        model = self.get_user_model()
        username_field = getattr(model, "USERNAME_FIELD", "username")

        kwargs = {username_field + "__iexact": username}

        if getattr(settings, "AUTH_LDAP_AUTOCREATE_USER", True):
            dataspace_name = getattr(settings, "AUTH_LDAP_DATASPACE", None)
            if not dataspace_name:
                raise ImproperlyConfigured(
                    "AUTH_LDAP_DATASPACE must be set when AUTH_LDAP_AUTOCREATE_USER is True."
                )

            try:
                dataspace = Dataspace.objects.get(name=dataspace_name)
            except Dataspace.DoesNotExist:
                raise ImproperlyConfigured(
                    f"Dataspace '{dataspace_name}' used in AUTH_LDAP_DATASPACE does not exist"
                )

            kwargs.update(
                {
                    "defaults": {
                        username_field: username.lower(),
                        "dataspace": dataspace,
                    },
                }
            )
            return model.objects.get_or_create(**kwargs)

        try:
            return model.objects.get(**kwargs), False
        except model.DoesNotExist:
            raise _LDAPUser.AuthenticationFailed("User does not exist in Django auth system")
