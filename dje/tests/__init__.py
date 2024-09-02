#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import random
import string
import sys
from importlib import reload

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DEFAULT_DB_ALIAS
from django.db import connections
from django.test.runner import DiscoverRunner
from django.test.utils import CaptureQueriesContext
from django.urls import clear_url_caches

from model_bakery import baker

User = get_user_model()


def make_string(length):
    return "".join(random.choices(string.ascii_letters, k=length))


def create(model, dataspace, **kwargs):
    """Wrap the `model_bakery.baker.make` to add a required `dataspace` argument."""
    return baker.make(model, dataspace=dataspace, **kwargs)


def create_user(username, dataspace, password="secret", email="user@email.com", **extra_fields):
    return User.objects.create_user(username, email, password, dataspace, **extra_fields)


def create_admin(*args, **kwargs):
    kwargs["is_staff"] = True
    return create_user(*args, **kwargs)


def create_superuser(
    username, dataspace, password="secret", email="user@email.com", **extra_fields
):
    return User.objects.create_superuser(username, email, password, dataspace, **extra_fields)


def add_perm(user, codename):
    """Return a refreshed instance of the User with the given Permission added."""
    user.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=user.pk)


def add_perms(user, codenames):
    """Return a refreshed instance of the User with the given Permissions added."""
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=user.pk)


def refresh_url_cache():
    """
    Clear the URLs cache and reloading the URLs module.
    Useful when changing the value of a settings trigger different URLs
    availability.
    """
    clear_url_caches()
    if settings.ROOT_URLCONF in sys.modules:
        reload(sys.modules[settings.ROOT_URLCONF])


class DejaCodeTestRunner(DiscoverRunner):
    """Contain DejaCode customization for running tests."""

    def setup_test_environment(self, **kwargs):
        """Force ScanCode.io integration to be available in test context."""
        super().setup_test_environment(**kwargs)

        from dejacode_toolkit import scancodeio

        scancodeio.is_configured = lambda: True


class _AssertMaxQueriesContext(CaptureQueriesContext):
    """Copy of `_AssertNumQueriesContext` but based on `assertLessEqual`."""

    def __init__(self, test_case, num, connection):
        self.test_case = test_case
        self.num = num
        super().__init__(connection)

    def __exit__(self, exc_type, exc_value, traceback):
        super().__exit__(exc_type, exc_value, traceback)
        if exc_type is not None:
            return
        executed = len(self)
        self.test_case.assertLessEqual(
            executed,
            self.num,
            "%d queries executed, %d max expected\nCaptured queries were:\n%s"
            % (
                executed,
                self.num,
                "\n".join(
                    "%d. %s" % (i, query["sql"])
                    for i, query in enumerate(self.captured_queries, start=1)
                ),
            ),
        )


class MaxQueryMixin:
    """Copy of `assertNumQueries` but based on `_AssertMaxQueriesContext`."""

    def assertMaxQueries(self, num, func=None, *args, using=DEFAULT_DB_ALIAS, **kwargs):
        conn = connections[using]

        context = _AssertMaxQueriesContext(self, num, conn)
        if func is None:
            return context

        with context:
            func(*args, **kwargs)
