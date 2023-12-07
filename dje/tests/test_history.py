#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.test.client import RequestFactory
from django.urls import reverse

from dje.models import Dataspace
from dje.models import History
from dje.tests import create_superuser
from dje.views import ActivityLog
from organization.models import Owner


class HistoryTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.super_user = create_superuser("super_user", self.dataspace)
        self.owner = Owner.objects.create(name="Test Organization", dataspace=self.dataspace)

    def test_history_on_admin_owner_add(self):
        self.client.login(username=self.super_user.username, password="secret")
        original_count = Owner.objects.count()

        url = reverse("admin:organization_owner_add")
        params = {
            "key": "organization1",
            "name": "OrganizationName",
            "type": "Organization",
            "related_children-TOTAL_FORMS": 0,
            "related_children-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }

        self.client.post(url, params)
        self.assertEqual(original_count + 1, Owner.objects.count())
        owner = Owner.objects.all()[0]

        self.assertFalse(History.objects.get_for_object(owner).exists())
        self.assertEqual(self.super_user, owner.created_by)
        self.assertTrue(owner.created_date)

    @override_settings(REFERENCE_DATASPACE="Dataspace")
    def test_history_on_admin_dataspace_add(self):
        self.client.login(username=self.super_user.username, password="secret")
        original_count = Dataspace.objects.count()

        url = reverse("admin:dje_dataspace_add")
        params = {
            "name": "new_dataspace",
            "configuration-TOTAL_FORMS": 0,
            "configuration-INITIAL_FORMS": 0,
        }

        self.client.post(url, params)
        self.assertEqual(original_count + 1, Dataspace.objects.count())
        dataspace = Dataspace.objects.get(name=params["name"])

        history = History.objects.get_for_object(dataspace).get()
        self.assertIsNone(history.object_dataspace)
        self.assertEqual(self.super_user.id, history.user_id)
        self.assertEqual(params["name"], history.object_repr)
        self.assertEqual('[{"added": {}}]', history.change_message)

    def test_history_on_admin_owner_change(self):
        # Testing a simple change of an existing object through an admin view of a DataspacedAdmin.
        self.client.login(username=self.super_user.username, password="secret")
        url = self.owner.get_admin_url()
        response = self.client.get(url)
        text = f'value="{self.owner.name}"'
        self.assertContains(response, text)
        # Changing the owner name through a post request in the admin view
        new_name = "NewName"
        params = {
            "name": new_name,
            "type": "Organization",
            "related_children-TOTAL_FORMS": 0,
            "related_children-INITIAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-TOTAL_FORMS": 0,
            "dje-externalreference-content_type-object_id-INITIAL_FORMS": 0,
        }
        response = self.client.post(url, params)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(new_name, Owner.objects.get(id=self.owner.id).name)

        history = History.objects.get_for_object(self.owner, action_flag=History.CHANGE).get()
        self.assertEqual(self.dataspace, history.object_dataspace)
        self.assertEqual(self.super_user.id, history.user_id)
        self.assertEqual('[{"changed": {"fields": ["Name"]}}]', history.change_message)
        self.assertEqual("Changed Name.", history.get_change_message())

    def test_activity_log_view_get_history_entries(self):
        # Setup some History entries first
        History.log_addition(self.super_user, self.owner)

        # This one should never be part of the activity log because in a different dataspace
        dataspace2 = Dataspace.objects.create(name="Dataspace2")
        owner2 = Owner.objects.create(name="Owner2", dataspace=dataspace2)
        History.log_addition(self.super_user, owner2)

        request = RequestFactory()
        # Simulate a logged-in user by setting request.user manually.
        request.user = self.super_user
        view = ActivityLog(model=self.owner._meta.model)
        view.request = request
        history_entries = view.get_history_entries(days=90)
        self.assertEqual(1, len(history_entries))

    def test_history_on_user_addition(self):
        self.client.login(username=self.super_user.username, password="secret")

        url = reverse("admin:dje_dejacodeuser_add")
        data = {
            "username": "new_user",
            "email": "user@mail.com",
            "dataspace": self.dataspace.id,
        }

        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "was added successfully.")
        new_user = get_user_model().objects.get(username="new_user")

        history = History.objects.get_for_object(new_user).get()
        self.assertEqual(self.dataspace, history.object_dataspace)
        self.assertEqual(self.super_user.id, history.user_id)
        self.assertEqual("new_user", history.object_repr)
        self.assertEqual('[{"added": {}}]', history.change_message)

    def test_history_on_user_deletion(self):
        self.client.login(username=self.super_user.username, password="secret")
        some_user = get_user_model().objects.create_user(
            "some_user", "test2@test.com", "oth3r", self.dataspace
        )

        url = reverse("admin:dje_dejacodeuser_delete", args=[some_user.pk])

        self.assertTrue(some_user.is_active)
        data = {"post": "yes"}
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("admin:dje_dejacodeuser_changelist"))
        some_user.refresh_from_db()
        self.assertFalse(some_user.is_active)

        history = History.objects.get_for_object(some_user, action_flag=History.CHANGE).get()
        self.assertEqual("Set as inactive.", history.change_message)
