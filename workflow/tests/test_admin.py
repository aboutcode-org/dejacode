#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import NON_FIELD_ERRORS
from django.test import TestCase
from django.urls import reverse

from dje.models import Dataspace
from dje.tests import create_superuser
from workflow.models import Request
from workflow.models import RequestTemplate


class WorkflowAdminTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.component1 = self.component_ct.model_class().objects.create(
            name="c1", dataspace=self.nexb_dataspace
        )

        self.product_ct = ContentType.objects.get(
            app_label="product_portfolio", model="product")
        self.product1 = self.product_ct.model_class().objects.create(
            name="p1", dataspace=self.nexb_dataspace
        )

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

        serialized_data = json.dumps(
            [
                {"input_type": "CharField", "value": "Response1", "label": "Q1"},
                {"input_type": "CharField", "value": "Response2", "label": "Q2"},
            ]
        )

        self.request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.nexb_user,
            serialized_data=serialized_data,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

    def test_admin_changeform_view_request_link_displayed(self):
        self.client.login(username="nexb_user", password="secret")
        base_link = '<a href="{}#activity" target="_blank" class="grp-state-focus">Requests</a>'

        response = self.client.get(self.component1.get_admin_url())
        expected = base_link.format(self.component1.get_absolute_url())
        self.assertNotContains(response, expected)
        self.request1.content_object = self.component1
        self.request1.save()
        self.component1.refresh_from_db()
        self.assertEqual(1, self.component1.request_count)
        response = self.client.get(self.component1.get_admin_url())
        self.assertContains(response, expected)

        product_template = RequestTemplate.objects.create(
            name="t2",
            description="desc",
            dataspace=self.nexb_user.dataspace,
            content_type=self.product_ct,
        )
        Request.objects.create(
            title="product",
            request_template=product_template,
            requester=self.nexb_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.product_ct,
            content_object=self.product1,
        )
        from product_portfolio.tests.test_admin_guardian import refresh_product

        self.product1 = refresh_product(self.product1)
        self.assertEqual(1, self.product1.request_count)
        response = self.client.get(self.product1.get_admin_url())
        expected = base_link.format(self.product1.get_absolute_url())
        self.assertContains(response, expected)

    def test_admin_priority_changelist_changeform_views(self):
        self.client.login(username="nexb_user", password="secret")
        data = {
            "label": "Urgent",
            "_save": "Save",
        }
        response = self.client.post(
            reverse("admin:workflow_priority_add"), data)
        self.assertEqual(302, response.status_code)

        response = self.client.get(
            reverse("admin:workflow_priority_changelist"))
        self.assertContains(response, "Urgent")


class RequestTemplateAdminTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="other")
        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)
        self.some_user = create_superuser("some_user", self.nexb_dataspace)
        self.other_user = create_superuser("other_user", self.other_dataspace)

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.product_ct = ContentType.objects.get(
            app_label="product_portfolio", model="product")

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )
        self.request_template2 = RequestTemplate.objects.create(
            name="Template2",
            description="Header Desc2",
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

    def test_request_template_admin_delete_permissions(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:workflow_requesttemplate_delete",
                      args=[self.request_template1.id])

        response = self.client.get(url)
        self.assertContains(response, "<h1>Are you sure?</h1>")

        # Attaching a Request to our template.
        Request.objects.create(
            title="Title",
            request_template=self.request_template1,
            requester=self.nexb_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 403)

    def test_request_template_admin_changeform_view_existing_request(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_admin_url()
        delete_url = reverse(
            "admin:workflow_requesttemplate_delete", args=[self.request_template1.id]
        )
        warning_msg = "WARNING: Existing Requests are using this template."

        self.assertFalse(self.request_template1.requests.exists())
        response = self.client.get(url)

        self.assertContains(response, "_saveasnew")
        self.assertContains(response, "_save")
        self.assertContains(response, "_continue")
        self.assertContains(response, 'href="{}"'.format(delete_url))
        self.assertNotContains(response, warning_msg)

        # Attaching a Request to our template.
        Request.objects.create(
            title="Title",
            request_template=self.request_template1,
            requester=self.nexb_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

        response = self.client.get(url)
        self.assertContains(response, "_saveasnew")
        # We cannot rely on the 2 following as the buttons are remove by JS
        # self.assertNotContains(response, "_save")
        # self.assertNotContains(response, "_continue")
        self.assertNotContains(response, 'href="{}"'.format(delete_url))
        self.assertContains(response, warning_msg)

        data = {
            "name": self.request_template1.name,
            "description": "desc",
            "content_type": self.request_template1.content_type.id,
            "questions-TOTAL_FORMS": 0,
            "questions-INITIAL_FORMS": 0,
            "_save": "Save",
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

        del data["_save"]
        data["_saveasnew"] = "Save as new"
        response = self.client.post(url, data)
        self.assertContains(
            response, "<li>Request template with this Dataspace and Name already exists.</li>"
        )
        expected = {
            NON_FIELD_ERRORS: [
                "Request template with this Dataspace and Name already exists."]
        }
        self.assertEqual(
            expected, response.context_data["adminform"].form.errors)

        data["name"] = "New name"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_request_template_admin_changeform_duplicate_question_label(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:workflow_requesttemplate_add")

        data = {
            "name": "name",
            "description": "desc",
            "content_type": self.component_ct.id,
            "questions-TOTAL_FORMS": 2,
            "questions-INITIAL_FORMS": 0,
            "questions-0-label": "label1",
            "questions-0-position": 0,
            "questions-0-input_type": "CharField",
            "questions-1-label": "label1",
            "questions-1-position": 1,
            "questions-1-input_type": "CharField",
        }

        response = self.client.post(url, data)
        self.assertContains(
            response, "Question with this Label for this Template already exists.")

        data["questions-1-label"] = "label2"
        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)

    def test_request_template_admin_changeform_product_ct_force_include_product_to_false(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:workflow_requesttemplate_add")

        data = {
            "name": "name",
            "description": "desc",
            "content_type": self.product_ct.id,
            "include_product": True,
            "questions-TOTAL_FORMS": 1,
            "questions-INITIAL_FORMS": 0,
            "questions-0-label": "label1",
            "questions-0-position": 0,
            "questions-0-input_type": "CharField",
        }

        response = self.client.post(url, data)
        self.assertEqual(302, response.status_code)
        request_template = RequestTemplate.objects.latest("id")
        self.assertFalse(request_template.include_product)

    def test_request_template_admin_make_active_action(self):
        self.client.login(username="nexb_user", password="secret")

        self.assertFalse(self.request_template1.is_active)
        url = reverse("admin:workflow_requesttemplate_changelist")
        response = self.client.get(url)
        self.assertContains(response, '<option value="make_active">')

        data = {
            "post": "yes",
            "_selected_action": [self.request_template1.pk],
            "selected_across": 0,
            "action": "make_active",
        }

        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, "1 template was successfully marked as active")

        self.request_template1.refresh_from_db()
        self.assertTrue(self.request_template1.is_active)

        data["_selected_action"] = [
            self.request_template1.pk, self.request_template2.pk]
        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, "2 templates were successfully marked as active")

    def test_request_template_admin_make_inactive_action(self):
        self.client.login(username="nexb_user", password="secret")

        self.request_template1.is_active = True
        self.request_template1.save()
        self.request_template1.refresh_from_db()
        self.assertTrue(self.request_template1.is_active)

        url = reverse("admin:workflow_requesttemplate_changelist")
        response = self.client.get(url)
        self.assertContains(response, '<option value="make_inactive">')

        data = {
            "post": "yes",
            "_selected_action": [self.request_template1.pk],
            "selected_across": 0,
            "action": "make_inactive",
        }

        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, "1 template was successfully marked as inactive")
        self.request_template1.refresh_from_db()
        self.assertFalse(self.request_template1.is_active)

        data["_selected_action"] = [
            self.request_template1.pk, self.request_template2.pk]
        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, "2 templates were successfully marked as inactive")

    def test_request_template_admin_changeform_view_default_assignee_scope(self):
        self.client.login(username="nexb_user", password="secret")

        self.assertTrue(self.nexb_user.is_staff)
        self.some_user.is_staff = False
        self.some_user.save()
        self.assertTrue(self.other_user.is_staff)

        url = self.request_template1.get_admin_url()
        response = self.client.get(url)
        default_assignee_field = response.context_data["adminform"].form.fields["default_assignee"]
        self.assertIn(self.nexb_user, default_assignee_field.queryset)
        self.assertNotIn(self.some_user, default_assignee_field.queryset)
        self.assertNotIn(self.other_user, default_assignee_field.queryset)

    def test_request_template_admin_copy_view_compare_link(self):
        # RequestTemplate does not support compare view
        # Making sure the link is not displayed.
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:workflow_requesttemplate_copy")

        data = {
            "ct": str(ContentType.objects.get_for_model(RequestTemplate).pk),
            "ids": str(self.request_template1.id),
            "target": self.other_dataspace.pk,
        }
        response = self.client.get(url, data)

        self.assertContains(
            response, "<h2>The following Request templates will be copied.</h2>")
        self.assertNotContains(response, "compare")

    def test_request_template_activity_log_available(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:workflow_requesttemplate_changelist")
        response = self.client.get(url)
        self.assertContains(response, "activity_log_link")
        self.assertContains(response, "Activity Log")

    def test_request_template_dataspace_filter_available(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("admin:workflow_requesttemplate_changelist")
        response = self.client.get(url)
        self.assertContains(response, "<label>Dataspace</label>")
