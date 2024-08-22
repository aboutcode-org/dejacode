#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
from random import choice
from unittest import mock

from django.apps.registry import apps
from django.conf import settings
from django.contrib.admindocs.views import extract_views_from_urlpatterns
from django.contrib.admindocs.views import simplify_regex
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.db.models import JSONField
from django.db.models.fields.related import ForeignKey
from django.db.models.fields.related import ManyToManyField
from django.db.models.fields.related import OneToOneField
from django.test import TestCase
from django.test import tag
from django.test.utils import override_settings
from django.urls import reverse

from axes.models import AccessAttempt
from model_bakery import baker

from component_catalog.models import Component
from component_catalog.models import Package
from dje.admin import register_axes_admin
from dje.fields import JSONListField
from dje.fields import LastModifiedByField
from dje.fields import NoStripTextField
from dje.models import Dataspace
from dje.models import DejacodeUser
from dje.models import is_dataspace_related
from dje.tests import create_user
from dje.tests import refresh_url_cache
from license_library.models import License
from notification.models import Webhook
from product_portfolio.models import Product


def gen_content_type():
    return ContentType.objects.get_for_model(choice([License, Component]))


def none():
    return


# Patch model_bakery for custom fields
baker.generators.default_mapping.update(
    {
        ContentType: gen_content_type,
        LastModifiedByField: none,
        NoStripTextField: baker.random_gen.gen_text,
        JSONField: baker.random_gen.gen_json,
        JSONListField: baker.random_gen.gen_array,
    }
)


class ModelMaker:
    """
    A specialized callable for model_bakery to always create objects in a given
    dataspace. This monkey patches the model_bakery module on instantiation and is
    NOT thread-safe. This is a kludge because fixing model model_bakery would
    require way too much refactoring. See why:
        https://github.com/vandersonmota/model_mommy/issues/144

    Use this way:
        maker = ModelMaker(<a dataspace instance>)
        comp = make(Component)
        lic = make('license_library.models.license')
    """

    def __init__(self, dataspace):
        self.dataspace = dataspace

    def __call__(self, model, _quantity=None, make_m2m=False, **attrs):
        return self.make(model, _quantity, make_m2m, **attrs)

    def make(self, model, _quantity=None, make_m2m=False, **attrs):
        """Create persisted instances from a given model and associated models."""
        if is_dataspace_related(model):
            attrs["dataspace"] = self.dataspace

        attrs["_fill_optional"] = True
        maker = baker.Baker(model, make_m2m=make_m2m)
        # more ugly monkey patching
        maker.type_mapping.update(
            {
                ForeignKey: self,
                OneToOneField: self,
                ManyToManyField: self,
            }
        )

        if model == Product:
            attrs["is_active"] = True

        # The `gen_string` generator Return values according to the field max_length.
        # Pushing all the PackageURL fields to the max trigger a database OperationalError
        # as the maximum row size of the unique_together index is exceeded.
        # We force an empty value for qualifiers to not exceed this limit in the tests.
        if model == Package:
            attrs["qualifiers"] = ""

        # We cannot set Dataspace related FKs on the User model since the target
        # object generation would trigger the creation of another User for the
        # created_by/last_modified_by fields and will result in a RecursionError.
        if model == DejacodeUser:
            attrs["homepage_layout"] = None

        if _quantity:
            return [maker.make(**attrs) for _ in range(_quantity)]
        else:
            return maker.make(**attrs)

    @property
    def required(self):
        return [lambda field: ("model", field.related_model)]


def collect_views():
    """Yield all view and url data collected from the root urlconf."""
    urlconf = __import__(settings.ROOT_URLCONF, {}, {}, [""])
    views_from_urls = extract_views_from_urlpatterns(urlconf.urlpatterns)
    for func, regex, namespace, url_name in views_from_urls:
        if hasattr(func, "__name__"):
            func_name = func.__name__
        elif hasattr(func, "__class__"):
            func_name = "{}()".format(func.__class__.__name__)
        yield (
            "{}.{}".format(func.__module__, func_name),
            url_name or "",
            namespace or "",
            regex,
            simplify_regex(regex),
        )


def is_var(segment):
    """
    Return the variable name if a url segment is a variable.
    Return False or None otherwise.
    """
    if segment.startswith("<") and segment.endswith(">"):
        return segment.strip("<>")


def to_segments(url_path):
    """Return a list o segments from a url path"""
    return url_path.strip("/").split("/")


def to_urlpath(segments):
    """Return a URL path from list of segments"""
    return "/" + "/".join(segments) + "/"


excluded_model = (
    DejacodeUser,
    Dataspace,
)


special_views = {
    "dje.admin.archived_history_view": (
        "pk",
        "/admin/reporting/columntemplate/<var>/archived_history/",
    ),
}

special_vars = {
    "<format>": "",
    "<app_label>": "",
    "<uidb64>": "",
    "<content_type_id>/<object_id>/": "",
}


def model_for_url(url_path):
    """
    Given a collected url_path, determine what the model needed to
    create a correct URL filling in the blanks. For each position in the URL
    that needs filling-in, Return a tuple of (Object, field_name). Return a
    list of such tuple where the position in the list corresponds to the
    parameter position in the URL.
    """
    if url_path.startswith("/admin/r/"):
        # special content-type-based path/admin/r/<content_type_id>/<object_id>/
        return

    if url_path.endswith(("annotations/", "hierarchy/")):
        return

    if not url_path.startswith(("/admin", "/grappelli")):
        return

    # this tests only simple gets in the admin for now
    segments = to_segments(url_path)
    has_vars = any(is_var(s) for s in segments)
    if not has_vars:
        # urls without vars do not need any var filling
        return

    app_name = segments[1]
    if apps.is_installed(app_name):
        model = segments[2]
        model_class = apps.get_model(app_name, model)
        if model_class in excluded_model:
            return
        if len(segments) == 5:
            # only consider for now the simple case where we have a direct PK
            # in the admin the next segment is usually the PK
            pk = segments[3]
            if is_var(pk):
                return model_class, 3


def checkable_url(view_name, *args, **kwargs):
    """Return a URL suitable for testing given a view name and crafted args."""
    return reverse(view_name, args=args, **kwargs)


def build_model(ds, class_):
    """Build a random model in dataspace ds. Return the saved model object."""
    maker = ModelMaker(ds)
    return maker(class_)


TEST_PASSWORD = "ch3tst"
DEMO_DATASPACE = "public"


def create_test_user(ds, name, is_staff=False, is_super=False, is_active=True):
    user = get_user_model().objects.create_user(name, "t@t.com", TEST_PASSWORD, ds)
    user.is_staff = is_staff
    user.is_superuser = is_super
    user.is_active = is_active
    user.save()
    return user


def create_ds_and_users(dataspace_name):
    """
    Given a dataspace_name, return a tuple of saved objects:
        (dataspace, regular_user, staff_user, super_user,
         super_not_staff_user, inactive_user)
    """
    ds = Dataspace.objects.create(name=dataspace_name)
    user = create_test_user(ds, "regular_user_" + dataspace_name)
    staff = create_test_user(ds, "staff_user_" + dataspace_name, is_staff=True)
    superu = create_test_user(ds, "super_user_" + dataspace_name, is_staff=True, is_super=True)
    super_not_staff = create_test_user(
        ds, "super_not_staff_user_" + dataspace_name, is_staff=False, is_super=True
    )
    inactive = create_test_user(
        ds, "inactive_user_" + dataspace_name, is_staff=False, is_super=True, is_active=False
    )
    return ds, user, staff, superu, super_not_staff, inactive


class CrossDataspaceAccessControlTestCase(TestCase):
    def setUp(self):
        self.dnx, self.unx, self.snx, self.supnx, self.supnsnx, self.inx = create_ds_and_users(
            "nexB"
        )
        (
            self.dano,
            self.uano,
            self.sano,
            self.supano,
            self.supnsano,
            self.iano,
        ) = create_ds_and_users(DEMO_DATASPACE)
        self.d1, self.ud1, self.sd1, self.supd1, self.supnsd1, self.id1 = create_ds_and_users("d1")
        self.d2, self.ud2, self.sd2, self.supd2, self.supnsd2, self.id2 = create_ds_and_users("d2")

    def check_view_access(self, user, dataspace, test_url, http_code, context):
        """
        Login as user, and try to access the test_url that points to data from
        dataspace. Ensure the http_code equals the response.
        """
        if user:  # no user mean anonymous access
            self.client.login(username=user.username, password=TEST_PASSWORD)
        else:
            self.client.logout()

        user_name = user.username if user else "AnonymousUser"
        user_ds = user.dataspace.name if user else None
        msg = (
            "Failed testing access for user <{user_name}>\n"
            " from dataspace <{user_ds}> to url <{test_url}>\n"
            " pointing to data from dataspace: <{dataspace.name}>.\n"
            "Returned: {response.status_code} Accepted: {http_code}.\n"
            "Test context data:\n"
            "{context}"
        )

        response = self.client.get(test_url)
        if type(http_code) in [list, tuple]:  # Support for multiple possible http_code
            self.assertIn(response.status_code, list(http_code), msg.format(**locals()))
        else:
            self.assertEqual(response.status_code, http_code, msg.format(**locals()))

    @tag("slow")
    @override_settings(ANONYMOUS_USERS_DATASPACE=DEMO_DATASPACE)
    def test_cross_dataspace_access_on_all_urls(self):
        for func, url_name, ns, regex, url_path in collect_views():
            # find model and attr to create
            class_idx = model_for_url(url_path)
            if not class_idx:
                continue

            class_, idx = class_idx

            obj_instance = build_model(self.d1, class_)
            pk = str(obj_instance.pk)
            segments = to_segments(url_path)
            segments[idx] = pk
            test_url = to_urlpath(segments)

            test_context = dict(
                obj_instance=obj_instance, idx=idx, func=func, url_name=url_name, ns=ns, regex=regex
            )

            # anonymous
            self.check_view_access(None, self.d1, test_url, http_code=302, context=test_context)

            self.check_view_access(
                self.uano, self.d1, test_url, http_code=302, context=test_context
            )
            self.check_view_access(
                self.iano, self.d1, test_url, http_code=302, context=test_context
            )
            self.check_view_access(
                self.sano, self.d1, test_url, http_code=[403, 404, 302], context=test_context
            )
            self.check_view_access(
                self.supano, self.d1, test_url, http_code=[302, 404], context=test_context
            )
            self.check_view_access(
                self.supnsano, self.d1, test_url, http_code=302, context=test_context
            )

            self.check_view_access(self.unx, self.d1, test_url, http_code=302, context=test_context)
            self.check_view_access(self.inx, self.d1, test_url, http_code=302, context=test_context)
            self.check_view_access(
                self.supnsnx, self.d1, test_url, http_code=302, context=test_context
            )

            # staff and staff/super in nexB are all seeing
            self.check_view_access(
                self.supnx, self.d1, test_url, http_code=[200, 302, 404], context=test_context
            )

            self.check_view_access(self.ud2, self.d1, test_url, http_code=302, context=test_context)
            self.check_view_access(self.id2, self.d1, test_url, http_code=302, context=test_context)
            self.check_view_access(
                self.sd2, self.d1, test_url, http_code=[403, 404, 302], context=test_context
            )
            self.check_view_access(
                self.supd2, self.d1, test_url, http_code=[302, 404], context=test_context
            )
            self.check_view_access(
                self.supnsd2, self.d1, test_url, http_code=302, context=test_context
            )

            self.check_view_access(self.id1, self.d1, test_url, http_code=302, context=test_context)
            self.check_view_access(self.ud1, self.d1, test_url, http_code=302, context=test_context)
            self.check_view_access(
                self.supd1, self.d1, test_url, http_code=200, context=test_context
            )
            # weirdly enough super not staff cannot access
            self.check_view_access(
                self.supnsd1, self.d1, test_url, http_code=302, context=test_context
            )

            self.check_view_access(
                self.snx, self.d1, test_url, http_code=[403, 404, 302], context=test_context
            )
            self.check_view_access(
                self.sd1, self.d1, test_url, http_code=[403, 404, 302], context=test_context
            )


@override_settings(
    AXES_ENABLED=True,
    AXES_FAILURE_LIMIT=2,
    AXES_LOCKOUT_TEMPLATE="axes_lockout.html",
    ADMINS=[("Admin1", "admin1@localhost.com")],
)
class LoginAttemptsTrackingTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        register_axes_admin()
        refresh_url_cache()

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")

    def test_user_locked_out_on_unsuccessful_login_attempts(self):
        login_url = reverse("login")
        credentials = {
            "username": "fake",
            "password": "wrong",
        }
        response = self.client.post(login_url, data=credentials)
        self.assertEqual(200, response.status_code)
        attempt = AccessAttempt.objects.get(username=credentials["username"])
        self.assertEqual(1, attempt.failures_since_start)

        response = self.client.post(login_url, data=credentials)
        self.assertContains(response, "Account locked", status_code=403)
        attempt = AccessAttempt.objects.get(username=credentials["username"])
        self.assertEqual(2, attempt.failures_since_start)

        user = create_user(username="real_user", dataspace=self.dataspace)
        credentials = {
            "username": user.username,
            "password": "bad_pass",
        }
        response = self.client.post(login_url, data=credentials)
        self.assertEqual(200, response.status_code)
        attempt = AccessAttempt.objects.get(username=credentials["username"])
        self.assertEqual(1, attempt.failures_since_start)

        response = self.client.post(login_url, data=credentials)
        self.assertContains(response, "Account locked", status_code=403)
        attempt = AccessAttempt.objects.get(username=credentials["username"])
        self.assertEqual(2, attempt.failures_since_start)

    @mock.patch("requests.Session.post", autospec=True)
    def test_notification_on_unsuccessful_login_attempts(self, method_mock):
        user = create_user(username="real_user", dataspace=self.dataspace)
        extra_payload = {"username": "DejaCode Webhook"}
        Webhook.objects.create(
            dataspace=self.dataspace,
            target="http://127.0.0.1:8000/",
            user=user,
            event="user.locked_out",
            extra_payload=extra_payload,
        )

        login_url = reverse("login")
        credentials = {
            "username": "fake",
            "password": "wrong",
        }
        self.client.post(login_url, data=credentials)
        response = self.client.post(login_url, data=credentials)
        self.assertEqual(403, response.status_code)

        subject = "[DejaCode] Login attempt on locked account requires review!"
        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(subject, mail.outbox[0].subject)
        self.assertIn('Review access entry for username "fake" at', mail.outbox[0].body)
        self.assertIn('"fake" is NOT an existing DejaCode user.', mail.outbox[0].body)
        self.assertIn("Suggestion: This looks like a malicious login attempt.", mail.outbox[0].body)

        # 3rd attempt, no email notification
        self.client.post(login_url, data=credentials)
        self.assertEqual(1, len(mail.outbox))

        # 4th attempt, notification since AXES_FAILURE_LIMIT * 2 = 4
        self.client.post(login_url, data=credentials)
        self.assertEqual(2, len(mail.outbox))

        payload = json.loads(method_mock.call_args_list[0][1]["data"])
        self.assertEqual("DejaCode Webhook", payload["username"])
        expected = (
            "[DejaCode] Login attempt on locked account requires review!\n"
            'Review access entry for username "fake" at'
        )
        self.assertIn(expected, payload["text"])
        self.assertIn('"fake" is NOT an existing DejaCode user.', payload["text"])

        credentials["username"] = user.username
        response = self.client.post(login_url, data=credentials)
        self.assertEqual(200, response.status_code)
        response = self.client.post(login_url, data=credentials)
        self.assertEqual(403, response.status_code)
        self.assertIn(
            '"real_user" is an existing DejaCode user in Dataspace "nexB"', mail.outbox[2].body
        )
        self.assertIn("Suggestion: The user forgot his password.", mail.outbox[2].body)

    @override_settings(REFERENCE_DATASPACE="nexB")
    def test_axes_reference_access_attempt_admin(self):
        user = create_user(username="user", dataspace=self.dataspace)
        login_url = reverse("login")
        credentials = {
            "username": user.username,
            "password": "secret",
        }
        self.client.post(login_url, data=credentials)

        admin_index_dashboard_url = reverse("admin:index")
        response = self.client.get(admin_index_dashboard_url)
        self.assertEqual(302, response.status_code)

        access_attempt_url = reverse("admin:axes_accessattempt_changelist")
        user.is_staff = True
        user.save()
        response = self.client.get(admin_index_dashboard_url)
        self.assertNotContains(response, access_attempt_url)

        user.is_superuser = True
        user.save()
        self.assertTrue(user.dataspace.is_reference)
        response = self.client.get(admin_index_dashboard_url)
        self.assertContains(response, access_attempt_url)
        response = self.client.get(access_attempt_url)
        self.assertEqual(200, response.status_code)

        with override_settings(REFERENCE_DATASPACE="Another"):
            user.refresh_from_db()
            self.assertFalse(user.dataspace.is_reference)
            response = self.client.get(admin_index_dashboard_url)
            self.assertNotContains(response, access_attempt_url)
            response = self.client.get(access_attempt_url)
            self.assertEqual(403, response.status_code)
