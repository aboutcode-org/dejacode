#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test

from dje.models import Dataspace


def test_or_set_dataspace_for_anonymous_users(user):
    """
    Return True if the given user is authenticated.
    If user.is_anonymous, check if the ANONYMOUS_USERS_DATASPACE settings
    is enabled then assigned it to the user and Return True.
    Return False if no Dataspace could be assigned to the user.
    """
    if user.is_authenticated:
        return True

    dataspace = settings.ANONYMOUS_USERS_DATASPACE
    if not dataspace:
        # If the feature is not enabled, cannot go further
        return False

    # Get the dataspace defined for Anonymous Users and assigned it to the user
    user.dataspace = Dataspace.objects.get_or_create(name=dataspace)[0]
    return True


def accept_anonymous(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url=None):
    """
    Give Anonymous Users access to a view if the feature is enabled in the settings.
    Requires to define the ANONYMOUS_USERS_DATASPACE.
    Works like login_required otherwise.
    """
    # This logic is similar to django.contrib.auth.decorators.login_required
    actual_decorator = user_passes_test(
        test_or_set_dataspace_for_anonymous_users,
        login_url=login_url,
        redirect_field_name=redirect_field_name,
    )
    if function:
        return actual_decorator(function)
    return actual_decorator
