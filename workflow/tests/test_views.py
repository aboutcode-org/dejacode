#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from guardian.shortcuts import assign_perm
from notifications.models import Notification

from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from dje.models import Dataspace
from dje.models import History
from dje.tests import add_perm
from dje.tests import create_superuser
from dje.tests import create_user
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from workflow.models import Priority
from workflow.models import Question
from workflow.models import Request
from workflow.models import RequestAttachment
from workflow.models import RequestComment
from workflow.models import RequestEvent
from workflow.models import RequestTemplate
from workflow.notification import request_comment_slack_payload
from workflow.notification import request_slack_payload


class RequestUserViewsTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.nexb_user = create_superuser(
            "nexb_user", self.nexb_dataspace, workflow_email_notification=True
        )
        self.basic_user = create_user(
            "basic_user",
            self.nexb_dataspace,
            email="basic_user@test.com",
            workflow_email_notification=True,
        )
        self.other_user = create_superuser(
            "other_user", self.other_dataspace, email="other_user@test.com"
        )
        self.requester_user = create_user(
            "requester_user", self.nexb_dataspace, email="orequester_user@test.com"
        )

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")

        self.component1 = self.component_ct.model_class().objects.create(
            name="c1", dataspace=self.nexb_dataspace
        )

        self.other_component = self.component_ct.model_class().objects.create(
            name="other_comp", dataspace=self.other_dataspace
        )

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

        self.other_template = RequestTemplate.objects.create(
            name="Template2",
            description="Header Desc1",
            dataspace=self.other_dataspace,
            content_type=self.component_ct,
        )

        self.question1 = Question.objects.create(
            template=self.request_template1,
            label="Organization",
            help_text="Your Organization (Department) name",
            input_type="TextField",
            is_required=False,
            position=0,
            dataspace=self.nexb_user.dataspace,
        )

        self.question2 = Question.objects.create(
            template=self.request_template1,
            label="Project",
            help_text="Product/Project Name",
            input_type="TextField",
            is_required=True,
            position=1,
            dataspace=self.nexb_user.dataspace,
        )

        self.priority1 = Priority.objects.create(label="Urgent", dataspace=self.nexb_dataspace)

        self.request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.nexb_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
            priority=self.priority1,
        )

        self.some_request = Request.objects.create(
            title="SomeTitle",
            request_template=self.request_template1,
            requester=self.basic_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )

        self.other_request = Request.objects.create(
            title="OtherTitle",
            request_template=self.other_template,
            requester=self.other_user,
            dataspace=self.other_dataspace,
            content_type=self.component_ct,
        )

    @override_settings(ANONYMOUS_USERS_DATASPACE="nexB", SHOW_TOOLS_IN_NAV=True)
    def test_workflow_request_link_availability_in_user_menu(self):
        url = reverse("workflow:request_list")
        response = self.client.get(reverse("license_library:license_list"))
        self.assertNotContains(response, url)

        self.client.login(username="nexb_user", password="secret")
        self.nexb_user.is_superuser = False
        self.nexb_user.save()
        response = self.client.get(reverse("license_library:license_list"))
        self.assertContains(response, url)

        self.nexb_user.is_superuser = True
        self.nexb_user.save()
        response = self.client.get(reverse("license_library:license_list"))
        self.assertContains(response, url)

    def test_workflow_request_list_view_listing(self):
        url = reverse("workflow:request_list")
        # As AnonymousUser first
        response = self.client.get(url)
        self.assertRedirects(response, "{}?next={}".format(reverse("login"), url))
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, "#{}".format(self.request1.id))

    def test_workflow_request_list_view_annotate_count(self):
        url = reverse("workflow:request_list")
        self.client.login(username="nexb_user", password="secret")

        RequestComment.objects.create(
            request=self.request1,
            user=self.basic_user,
            text="Comment1",
            dataspace=self.nexb_dataspace,
        )
        RequestComment.objects.create(
            request=self.request1,
            user=self.basic_user,
            text="Comment2",
            dataspace=self.nexb_dataspace,
        )

        RequestAttachment.objects.create(
            request=self.request1,
            uploader=self.basic_user,
            file="filename.ext",
            dataspace=self.nexb_dataspace,
        )
        RequestAttachment.objects.create(
            request=self.request1,
            uploader=self.basic_user,
            file="filename.ext",
            dataspace=self.nexb_dataspace,
        )
        RequestAttachment.objects.create(
            request=self.request1,
            uploader=self.basic_user,
            file="filename.ext",
            dataspace=self.nexb_dataspace,
        )

        response = self.client.get(url)

        self.assertContains(response, '<i class="fas fa-file"></i> 3')
        self.assertContains(response, '<i class="fas fa-comments"></i> 2')

    def test_workflow_request_details_view_add_comments(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request1.get_absolute_url()
        data = {"comment_content": "A comment content"}
        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, '<div class="alert alert-success alert-dismissible" role="alert">'
        )
        self.assertContains(response, "<strong>Success:</strong>")
        self.assertContains(response, "Comment for Request {} added.".format(self.request1))
        self.assertContains(response, "A comment content")

        # Again with a Request that does not belong to the user
        url = self.some_request.get_absolute_url()
        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, '<div class="alert alert-success alert-dismissible" role="alert">'
        )
        self.assertContains(response, "<strong>Success:</strong>")

        # Again with a Request in another dataspace
        url = self.other_request.get_absolute_url()
        response = self.client.post(url, data)
        self.assertEqual(404, response.status_code)

    def test_workflow_add_request_comment_notification(self):
        self.client.login(username="nexb_user", password="secret")

        requester = create_user(
            "requester",
            self.nexb_dataspace,
            email="requester@test.com",
            workflow_email_notification=True,
        )
        assignee = create_user(
            "assignee",
            self.nexb_dataspace,
            email="assignee@test.com",
            workflow_email_notification=True,
        )
        create_superuser(
            "admin", self.nexb_dataspace, email="admin@test.com", workflow_email_notification=True
        )
        commenter = create_user(
            "commenter",
            self.nexb_dataspace,
            email="commenter@test.com",
            workflow_email_notification=True,
        )

        self.request1.requester = requester
        self.request1.assignee = assignee
        self.request1.save()

        self.request1.comments.create(
            user=commenter, text="Comment1", dataspace=self.nexb_dataspace
        )

        url = self.request1.get_absolute_url()
        data = {"comment_content": "A comment content '&<"}
        self.client.post(url, data)

        self.assertEqual(1, len(mail.outbox))

        expected_subject = "Request {} commented by {} in {}".format(
            self.request1, self.nexb_user, self.nexb_user.dataspace
        )
        self.assertEqual(expected_subject, mail.outbox[0].subject)

        body = mail.outbox[0].body
        comment = self.request1.comments.latest("id")
        self.assertIn(str(self.request1), body)
        self.assertIn("Comment by nexb_user:", body)
        self.assertIn(comment.text, body)
        self.assertIn(self.request1.get_absolute_url(), body)
        self.assertIn("Request template: Template1", body)
        self.assertIn("Product context: (none)", body)
        self.assertIn("Applies to: (none)", body)
        self.assertIn("Submitted by: {}".format(requester), body)
        self.assertIn("A comment content '&<", body)

        # The creator of the comment `nexb_user` is not notified.
        expected_recipients = {
            self.request1.requester.email,
            self.request1.assignee.email,
            commenter.email,
        }
        self.assertEqual(expected_recipients, set(mail.outbox[0].recipients()))

    def test_workflow_request_details_view_serialized_data(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request1.get_absolute_url()

        question3 = Question.objects.create(
            template=self.request_template1,
            label="Date",
            input_type="DateField",
            is_required=True,
            position=2,
            dataspace=self.nexb_user.dataspace,
        )

        question4 = Question.objects.create(
            template=self.request_template1,
            label="Boolean",
            input_type="BooleanField",
            is_required=True,
            position=3,
            dataspace=self.nexb_user.dataspace,
        )

        self.request1.serialized_data = json.dumps(
            {
                self.question1.label: "char",
                self.question2.label: "text",
                question3.label: "2000-01-01",
                question4.label: "1",
            }
        )
        self.request1.save()

        response = self.client.get(url)
        expected = """
        <div class="mb-3">
          <label for="Organization" class="form-label fw-bold mb-1">Organization</label>
            <div class="clipboard">
              <button class="btn-clipboard" data-bs-toggle="tooltip" title="Copy to clipboard">
                <i class="fas fa-clipboard"></i>
              </button>
              <pre id="Organization" class="pre-bg-body-tertiary">char</pre>
            </div>
        </div>
        """
        self.assertContains(response, expected, html=True)

    def test_workflow_request_add_view_get_form(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        response = self.client.get(url)
        self.assertContains(
            response,
            '<textarea name="field_0" cols="40" rows="2" '
            'class="textarea form-control" '
            'aria-describedby="id_field_0_helptext" id="id_field_0">',
            html=True,
        )
        self.assertContains(
            response,
            '<textarea name="field_1" cols="40" rows="2" '
            'class="textarea form-control" required '
            'aria-describedby="id_field_1_helptext" id="id_field_1">',
            html=True,
        )
        expected = (
            '<select name="priority" class="select form-select" '
            'aria-describedby="id_priority_helptext" id="id_priority">'
        )
        self.assertContains(response, expected)
        expected = f'<option value="{self.priority1.id}">{self.priority1.label}</option>'
        self.assertContains(response, expected, html=True)

        self.assertContains(response, 'name="submit_as_private"')
        self.assertContains(response, 'name="save_draft"')
        self.assertContains(response, 'name="submit"')

    def test_workflow_request_add_view_include_applies_to(self):
        self.client.login(username="nexb_user", password="secret")
        url = "{}?content_object_id={}".format(
            self.request_template1.get_absolute_url(), self.component1.id
        )
        response = self.client.get(url)
        expected1 = "id_applies_to"
        expected2 = "applies_to_link"
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "object_id": self.component1.id,
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")
        self.assertEqual(Request.objects.latest("id").object_id, self.component1.id)
        self.component1.refresh_from_db()
        self.assertEqual(1, self.component1.request_count)

        # Now with include_applies_to = False
        self.request_template1.include_applies_to = False
        self.request_template1.save()
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")
        self.assertIsNone(Request.objects.latest("id").object_id)

    def test_workflow_request_add_view_add_object_to_product(self):
        self.client.login(username=self.nexb_user.username, password="secret")
        url = self.request_template1.get_absolute_url()

        self.assertEqual("component", self.request_template1.content_type.model)
        self.request_template1.include_product = True
        self.request_template1.save()
        product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )

        response = self.client.get(url)
        self.assertContains(response, "id_add_object_to_product")

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "object_id": self.component1.id,
            "assignee": self.nexb_user.id,
            "product_context": product1.id,
            "add_object_to_product": True,
        }

        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")
        self.assertEqual(Request.objects.latest("id").object_id, self.component1.id)
        self.component1.refresh_from_db()
        self.assertEqual(1, self.component1.request_count)

        self.assertEqual(1, product1.productcomponents.count())
        pc = product1.productcomponents.get(component=self.component1)

        self.assertEqual(self.nexb_user, pc.created_by)
        self.assertEqual(self.nexb_user, pc.last_modified_by)
        self.assertEqual(32, len(str(pc.created_date)))
        self.assertEqual(32, len(str(pc.last_modified_date)))

        product1.refresh_from_db()
        history_entries = History.objects.get_for_object(product1)
        expected_messages = sorted(
            [
                'Added component "c1"',
            ]
        )
        self.assertEqual(
            expected_messages, sorted([entry.change_message for entry in history_entries])
        )
        self.assertEqual(self.nexb_user, product1.last_modified_by)

    def test_workflow_request_add_view_invalid_uuid(self):
        self.client.login(username="nexb_user", password="secret")
        # Proper UUID but non existing
        url = reverse("workflow:request_add", args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

        # Badly formed UUID string
        url = "/requests/form/999999/"
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_workflow_request_add_view_id_from_other_dataspace(self):
        self.client.login(username="nexb_user", password="secret")
        self.request_template1.dataspace = self.other_dataspace
        self.request_template1.save()
        url = self.request_template1.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_workflow_request_add_view_product_context_dataspace_scope(self):
        # Testing the dataspace limitation for the product_context FK
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        self.request_template1.include_product = True
        self.request_template1.save()

        response = self.client.get(url)
        expected_html = (
            '<select name="product_context" class="select form-select" '
            'aria-describedby="id_product_context_helptext" id="id_product_context">'
        )
        self.assertContains(response, expected_html)

        product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )
        product2 = self.product_ct.model_class().objects.create(
            name="product2", dataspace=self.other_dataspace
        )
        response = self.client.get(url)
        expected = '<option value="{}">{}</option>'.format(product1.id, product1.name)
        not_expected = '<option value="{}">{}</option>'.format(product2.id, product2.name)

        self.assertContains(response, expected)
        self.assertNotContains(response, not_expected)

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.product_ct.id,
            "product_context": product1.id,
            "assignee": self.nexb_user.id,
        }
        self.client.post(url, data)
        created_request = Request.objects.all().latest("id")
        self.assertEqual(product1, created_request.product_context)

    def test_workflow_request_add_view_product_context_not_included(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        initial_request_count = Request.objects.count()

        self.request_template1.include_product = False
        self.request_template1.save()

        response = self.client.get(url)
        self.assertNotContains(response, 'id="id_product_context"')

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data)
        request_instance = Request.objects.latest("id")
        self.assertRedirects(response, request_instance.get_absolute_url())
        self.assertTrue(initial_request_count + 1, Request.objects.count())

    def test_workflow_request_add_view_assignee_field_is_required(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
        }
        response = self.client.post(url, data, follow=True)
        expected = {"assignee": ["This field is required."]}
        self.assertEqual(expected, response.context["form"].errors)

        data["assignee"] = self.nexb_user.id
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")

    def test_workflow_request_add_view_assignee_field_scope(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        self.requester_user.is_staff = True
        self.requester_user.is_active = False
        self.requester_user.save()

        response = self.client.get(url)
        assignee_qs = response.context["form"].fields["assignee"].queryset

        self.assertTrue(self.nexb_user.is_staff)
        self.assertTrue(self.nexb_user.is_active)
        self.assertEqual(self.nexb_dataspace, self.nexb_user.dataspace)
        self.assertIn(self.nexb_user, assignee_qs)

        # Exclude non is_staff
        self.assertFalse(self.basic_user.is_staff)
        self.assertTrue(self.basic_user.is_active)
        self.assertEqual(self.nexb_dataspace, self.basic_user.dataspace)
        self.assertNotIn(self.basic_user, assignee_qs)

        # Exclude non is_active
        self.assertTrue(self.requester_user.is_staff)
        self.assertFalse(self.requester_user.is_active)
        self.assertEqual(self.nexb_dataspace, self.requester_user.dataspace)
        self.assertNotIn(self.requester_user, assignee_qs)

        # Exclude other dataspace
        self.assertTrue(self.other_user.is_staff)
        self.assertTrue(self.other_user.is_active)
        self.assertNotEqual(self.nexb_dataspace, self.other_user.dataspace)
        self.assertNotIn(self.other_user, assignee_qs)

    def test_workflow_request_add_view_default_assignee(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        self.assertIsNone(self.request_template1.default_assignee)
        response = self.client.get(url)
        self.assertIsNone(response.context["form"].fields["assignee"].initial)

        self.request_template1.default_assignee = self.nexb_user
        self.request_template1.save()
        response = self.client.get(url)
        self.assertEqual(self.nexb_user, response.context["form"].fields["assignee"].initial)

    def test_workflow_request_add_view_assignee_has_product_context_object_permission(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        self.request_template1.include_product = True
        self.request_template1.save()

        product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )

        # Only staff user are available as assignee
        self.basic_user.is_staff = True
        self.basic_user.save()

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "product_context": product1.id,
            "assignee": self.basic_user.id,
        }
        response = self.client.post(url, data)
        self.assertFalse(self.basic_user.has_perm("view_product", product1))
        expected = {"assignee": ["basic_user does not have the permission to view product1"]}
        self.assertEqual(expected, response.context["form"].errors)

        self.assertTrue(self.nexb_user.has_perm("view_product", product1))
        data["assignee"] = self.nexb_user.id
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")

        data["assignee"] = self.basic_user.id
        data["product_context"] = ""
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")

    def test_workflow_request_add_view_assignee_has_assigned_to_product_object_permission(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        self.request_template1.content_type = self.product_ct
        self.request_template1.save()

        product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )

        # Only staff user are available as assignee
        self.basic_user.is_staff = True
        self.basic_user.save()

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.product_ct.id,
            "object_id": product1.id,
            "assignee": self.basic_user.id,
        }
        response = self.client.post(url, data)
        self.assertFalse(self.basic_user.has_perm("view_product", product1))
        expected = {"assignee": ["basic_user does not have the permission to view product1"]}
        self.assertEqual(expected, response.context["form"].errors)

        self.assertTrue(self.nexb_user.has_perm("view_product", product1))
        data["assignee"] = self.nexb_user.id
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")

        data["assignee"] = self.basic_user.id
        data["object_id"] = ""
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")

    def test_workflow_request_add_view_submit_form(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)

        self.assertContains(response, "request was successfully submitted as")
        self.assertContains(response, f'<a href="{url}">Add a new "Template1" Request</a>')
        request_instance = Request.objects.get(
            content_type=self.component_ct.id,
            serialized_data__icontains="Content1",
            dataspace=self.nexb_dataspace,
        )
        self.assertTrue(request_instance)
        self.assertFalse(request_instance.is_private)

    def test_workflow_request_add_view_submit_form_with_content_object(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "object_id": self.component1.id,
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")
        request_instance = Request.objects.get(
            content_type=self.component_ct.id,
            serialized_data__icontains="Content1",
            dataspace=self.nexb_dataspace,
        )
        self.assertTrue(request_instance)
        self.assertEqual(self.component1.id, request_instance.object_id)
        self.assertEqual(self.component1, request_instance.content_object)

    def test_workflow_request_add_view_submit_form_with_non_existing_content_object(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "object_id": 9999999,
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)
        form = response.context["form"]
        self.assertFalse(form.is_valid())
        expected = {"object_id": ["Invalid value."], "applies_to": ["Invalid value."]}
        self.assertEqual(expected, response.context["form"].errors)

    def test_workflow_request_add_view_submit_form_with_content_object_from_other_dataspace(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "object_id": self.other_component.id,
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)
        form = response.context["form"]
        self.assertFalse(form.is_valid())
        expected = {"object_id": ["Invalid value."], "applies_to": ["Invalid value."]}
        self.assertEqual(expected, response.context["form"].errors)

    def test_workflow_request_add_view_submit_form_with_junk_applies_to(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "applies_to": "junk",
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)
        self.assertFalse(response.context["form"].is_valid())
        expected = {"applies_to": ["Invalid value."]}
        self.assertEqual(expected, response.context["form"].errors)

        # Valid object_id but junk applies_to
        data["object_id"] = self.component1.id
        response = self.client.post(url, data, follow=True)
        self.assertFalse(response.context["form"].is_valid())
        self.assertEqual(expected, response.context["form"].errors)

    def test_workflow_request_add_view_submit_form_with_proper_content_object(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "applies_to": str(self.component1),
            "object_id": self.component1.id,
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully submitted as")
        self.component1.refresh_from_db()
        self.assertEqual(1, self.component1.request_count)

    def test_workflow_request_add_view_submit_as_private(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "submit_as_private": "Submit As Private",
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)

        self.assertContains(response, "request was successfully submitted as")
        request_instance = Request.objects.get(
            content_type=self.component_ct.id,
            serialized_data__icontains="Content1",
            dataspace=self.nexb_dataspace,
        )
        self.assertTrue(request_instance.is_private)

    def test_workflow_request_add_view_save_draft(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "object_id": self.component1.id,
            "save_draft": "Save Draft",
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Your request was saved as a draft and self-assigned to you.")
        self.assertContains(response, f'<a href="{url}">Add a new "Template1" Request</a>')
        request_instance = Request.objects.latest("id")
        self.assertTrue(request_instance.is_draft)
        self.assertEqual(self.nexb_user, request_instance.requester)

        self.component1.refresh_from_db()
        self.assertIsNone(self.component1.request_count)
        self.assertEqual(0, len(mail.outbox))

    def test_workflow_request_edit_view_save_draft(self):
        self.client.login(username="nexb_user", password="secret")
        url = reverse("workflow:request_edit", args=[self.request1.uuid])

        data = {
            "title": self.request1.title,
            "field_0": "Content1",
            "field_1": "Content2",
            "content_type": self.component_ct.id,
            "object_id": self.component1.id,
            "assignee": self.nexb_user.id,
            "status": Request.Status.DRAFT,
        }
        response = self.client.post(url, data, follow=True)

        self.assertContains(
            response, "Your request was updated as a draft and self-assigned to you."
        )
        template_url = self.request_template1.get_absolute_url()
        expected = f'<a href="{template_url}">Add a new "Template1" Request</a>'
        self.assertContains(response, expected)
        self.request1.refresh_from_db()
        self.assertTrue(self.request1.is_draft)
        self.assertEqual(1, self.request1.events.count())
        self.component1.refresh_from_db()
        self.assertIsNone(self.component1.request_count)
        self.assertEqual(0, len(mail.outbox))

        data["status"] = Request.Status.OPEN
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Your request was successfully edited")
        self.request1.refresh_from_db()
        self.assertFalse(self.request1.is_draft)
        self.assertEqual(2, self.request1.events.count())
        self.component1.refresh_from_db()
        self.assertEqual(1, self.component1.request_count)
        self.assertEqual(1, len(mail.outbox))

    def test_workflow_request_add_view_submit_notification(self):
        self.client.login(username=self.requester_user.username, password="secret")
        url = self.request_template1.get_absolute_url()

        self.requester_user.is_staff = True
        self.requester_user.workflow_email_notification = True
        self.requester_user.save()

        data = {
            "title": "Title",
            "field_0": "Value for field0",
            "field_1": "Value for field1",
            "content_type": self.component_ct.id,
            "assignee": self.nexb_user.id,
            "object_id": self.component1.id,
            "priority": self.priority1.id,
        }
        self.client.post(url, data)

        self.assertEqual(1, len(mail.outbox))
        # Email notification to the the requestor and assignee
        recipient_emails = [self.requester_user.email, self.nexb_user.email]
        self.assertEqual(sorted(recipient_emails), sorted(mail.outbox[0].to))

        # Internal notification to assignee only
        self.assertEqual(1, Notification.objects.count())
        internal_notif = Notification.objects.latest("id")
        self.assertEqual(self.nexb_user, internal_notif.recipient)

        request_instance = Request.objects.latest("id")
        self.assertEqual(self.component1, request_instance.content_object)

        expected_subject = "Request {} for {} submitted by {} in {}".format(
            request_instance, self.component1, self.requester_user, self.requester_user.dataspace
        )
        self.assertEqual(expected_subject, mail.outbox[0].subject)

        body = mail.outbox[0].body
        self.assertIn("Ref. #", body)
        self.assertIn("Title", body)
        self.assertIn("Request template: Template1", body)
        self.assertIn("Product context: (none)", body)
        self.assertIn("Applies to: {}".format(self.component1), body)
        self.assertIn(f"Submitted by: {self.requester_user}", body)
        self.assertIn(f"Assigned to: {self.nexb_user}", body)
        self.assertIn(f"Priority: {self.priority1}", body)
        self.assertIn(request_instance.get_absolute_url(), body)
        self.assertIn("* Project:\nValue for field1", body)
        self.assertIn("* Organization:\nValue for field0", body)

    def test_workflow_request_add_view_with_content_object(self):
        self.client.login(username="nexb_user", password="secret")
        url = "{}?content_object_id={}".format(
            self.request_template1.get_absolute_url(), self.component1.id
        )
        response = self.client.get(url)

        expected = f"""
        <a href="{self.component1.get_absolute_url()}" id="id_applies_to_link"
           target="_blank" style="" title="View object" data-bs-toggle="tooltip"
           aria-label="View object"><i class="fas fa-external-link-alt ms-1"></i>
        </a>
        """
        self.assertContains(response, expected, html=True)

        expected = f"""
        <input type="text" name="applies_to" value="{self.component1}"
               placeholder="Start typing for suggestions..."
               data-api_url="/api/v2/components/"
               class="autocompleteinput form-control"
               aria-describedby="id_applies_to_helptext"
               id="id_applies_to"
        >
        """
        self.assertContains(response, expected, html=True)

        expected = """
        <input id="id_object_id" name="object_id" type="hidden" value="{}" />
        """.format(self.component1.id)
        self.assertContains(response, expected, html=True)

        expected_js = """
        <script>
          AutocompleteWidget.init("input#id_applies_to.autocompleteinput",
            "#id_object_id", "#id_applies_to_link", "display_name");
        </script>
        """
        self.assertContains(response, expected_js, html=True)

    def test_workflow_request_add_view_with_non_existing_content_object(self):
        self.client.login(username="nexb_user", password="secret")
        url = "{}?content_object_id={}".format(self.request_template1.get_absolute_url(), 99999)

        response = self.client.get(url)
        expected = '<input id="id_object_id" name="object_id" type="hidden" />'
        self.assertContains(response, expected, html=True)

    def test_workflow_request_add_view_without_content_object(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        response = self.client.get(url)
        self.assertNotContains(response, "Applies to:")
        expected = '<input id="id_object_id" name="object_id" type="hidden">'
        self.assertContains(response, expected, html=True)

    def test_workflow_request_add_view_with_content_object_from_other_dataspace(self):
        self.client.login(username="nexb_user", password="secret")
        url = "{}?content_object_id={}".format(
            self.request_template1.get_absolute_url(), self.other_component.id
        )

        response = self.client.get(url)
        expected = '<input id="id_object_id" name="object_id" type="hidden" />'
        self.assertContains(response, expected, html=True)

    def test_workflow_request_add_view_boolean_field_to_serialized_data(self):
        self.client.login(username="basic_user", password="secret")
        url = self.request_template1.get_absolute_url()

        self.question2.label = "Bool"
        self.question2.input_type = "BooleanField"
        self.question2.is_required = False
        self.question2.save()

        response = self.client.get(url)
        expected = (
            '<select name="field_1" class="select form-select" '
            'aria-describedby="id_field_1_helptext" id="id_field_1">'
        )
        self.assertContains(response, expected)

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "1",
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)

        self.assertContains(response, "request was successfully submitted as")
        request_instance = Request.objects.get(
            content_type=self.component_ct.id,
            serialized_data__icontains="Content1",
            dataspace=self.nexb_dataspace,
        )

        expected = '{"Organization": "Content1", "Bool": "1"}'
        self.assertIn(expected, request_instance.serialized_data)
        self.assertIn("* Bool:\nYes", mail.outbox[0].body)

        # last_modified_by is not set on creation
        self.assertIsNone(request_instance.last_modified_by)

        response = self.client.get(request_instance.get_absolute_url())
        self.assertContains(
            response, '<pre id="Bool" class="pre-bg-body-tertiary">Yes</pre>', html=True
        )
        url = reverse("workflow:request_edit", args=[request_instance.uuid])
        response = self.client.get(url)
        expected = '<option value="1" selected="selected">Yes</option>'
        self.assertContains(response, expected, html=True)

        data["field_1"] = "0"
        data["status"] = Request.Status.OPEN
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully edited")
        request_instance.refresh_from_db()
        expected = '{"Organization": "Content1", "Bool": "0"}'
        self.assertIn(expected, request_instance.serialized_data)

        # last_modified_by is set on edition
        self.assertEqual(self.basic_user, request_instance.last_modified_by)

        response = self.client.get(request_instance.get_absolute_url())
        self.assertContains(
            response, '<pre id="Bool" class="pre-bg-body-tertiary">No</pre>', html=True
        )

        url = reverse("workflow:request_edit", args=[request_instance.uuid])
        response = self.client.get(url)
        expected = '<option value="0" selected="selected">No</option>'
        self.assertContains(response, expected, html=True)

    def test_workflow_request_add_view_date_field_to_serialized_data(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        self.question2.label = "Date"
        self.question2.input_type = "DateField"
        self.question2.is_required = False
        self.question2.save()

        data = {
            "title": "Title",
            "field_0": "Content1",
            "field_1": "",
            "assignee": self.nexb_user.id,
        }
        response = self.client.post(url, data, follow=True)

        self.assertContains(response, "request was successfully submitted as")
        request_instance = Request.objects.get(
            content_type=self.component_ct.id,
            serialized_data__icontains="Content1",
            dataspace=self.nexb_dataspace,
        )

        expected = '{"Organization": "Content1", "Date": ""}'
        self.assertEqual(expected, request_instance.serialized_data)

        url = reverse("workflow:request_edit", args=[request_instance.uuid])
        response = self.client.get(url)
        expected = (
            '<input type="text" name="field_1" placeholder="YYYY-MM-DD" '
            'class="datepicker form-control" aria-describedby="id_field_1_helptext" '
            'id="id_field_1">'
        )
        self.assertContains(response, expected, html=True)

        data["field_1"] = "2015-11-11"
        data["status"] = Request.Status.OPEN
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "request was successfully edited")
        request_instance.refresh_from_db()
        expected = '{"Organization": "Content1", "Date": "2015-11-11"}'
        self.assertEqual(expected, request_instance.serialized_data)

        response = self.client.get(url)
        expected = (
            '<input type="text" name="field_1" value="2015-11-11" '
            'placeholder="YYYY-MM-DD" class="datepicker form-control" '
            'aria-describedby="id_field_1_helptext" id="id_field_1">'
        )
        self.assertContains(response, expected, html=True)

    def test_workflow_request_edit_view_dataspace_scope(self):
        url = reverse("workflow:request_edit", args=[self.request1.uuid])
        self.assertTrue(self.request1.dataspace != self.other_user.dataspace)
        self.client.login(username="other_user", password="secret")
        self.assertEqual(404, self.client.get(url).status_code)
        self.client.login(username="nexb_user", password="secret")
        self.assertEqual(200, self.client.get(url).status_code)

    def test_workflow_request_edit_view_permission_access(self):
        url = reverse("workflow:request_edit", args=[self.request1.uuid])
        self.client.login(username="nexb_user", password="secret")

        self.assertTrue(self.nexb_user.has_perm("workflow.change_request"))
        self.assertTrue(self.request1.has_edit_permission(self.nexb_user))
        self.assertEqual(200, self.client.get(url).status_code)

        self.nexb_user.is_superuser = False
        self.nexb_user.save()
        self.assertFalse(self.nexb_user.has_perm("workflow.change_request"))
        self.assertTrue(self.request1.has_edit_permission(self.nexb_user))
        self.assertEqual(200, self.client.get(url).status_code)

        self.request1.status = Request.Status.CLOSED
        self.request1.requester = self.basic_user
        self.request1.save()
        self.nexb_user.is_staff = False
        self.nexb_user.is_superuser = True
        self.nexb_user.save()
        self.assertTrue(self.nexb_user.has_perm("workflow.change_request"))
        self.assertFalse(self.request1.has_edit_permission(self.nexb_user))
        self.assertEqual(200, self.client.get(url).status_code)

        self.nexb_user.is_superuser = False
        self.nexb_user.save()
        self.assertFalse(self.nexb_user.has_perm("workflow.change_request"))
        self.assertFalse(self.request1.has_edit_permission(self.nexb_user))
        self.assertEqual(404, self.client.get(url).status_code)

    def test_workflow_request_edit_view_content_object(self):
        url = reverse("workflow:request_edit", args=[self.request1.uuid])
        self.client.login(username="nexb_user", password="secret")
        component2 = self.component_ct.model_class().objects.create(
            name="c2", dataspace=self.nexb_dataspace
        )

        self.request1.content_object = component2
        self.request1.save()
        response = self.client.get(url)

        expected = f"""
        <a href="{component2.get_absolute_url()}" id="id_applies_to_link"
           target="_blank" style="" title="View object" data-bs-toggle="tooltip"
           aria-label="View object">
           <i class="fas fa-external-link-alt ms-1"></i>
        </a>
        """
        self.assertContains(response, expected, html=True)

        expected = f"""
        <input type="text" name="applies_to" value="{component2}"
               placeholder="Start typing for suggestions..."
               data-api_url="/api/v2/components/"
               class="autocompleteinput form-control"
               aria-describedby="id_applies_to_helptext"
               id="id_applies_to" />
        """
        self.assertContains(response, expected, html=True)

        expected = f"""
        <input id="id_object_id" name="object_id" type="hidden" value="{component2.id}" />
        """
        self.assertContains(response, expected, html=True)

    def test_workflow_request_edit_view_requester_readonly(self):
        url = reverse("workflow:request_edit", args=[self.request1.uuid])
        self.client.login(username="nexb_user", password="secret")

        response = self.client.get(url)
        expected = f"Created by <strong>{self.request1.requester}</strong>"
        self.assertContains(response, expected)

    def test_workflow_request_edit_view_no_save_draft_submit(self):
        url = reverse("workflow:request_edit", args=[self.request1.uuid])
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)

        self.assertContains(response, 'name="submit_as_private"')
        self.assertNotContains(response, 'name="save_draft"')
        self.assertContains(response, 'name="submit"')

    def test_workflow_request_details_view_dataspace_scope(self):
        url = self.request1.get_absolute_url()
        self.assertTrue(self.request1.dataspace != self.other_user.dataspace)
        self.client.login(username="other_user", password="secret")
        self.assertEqual(404, self.client.get(url).status_code)
        self.client.login(username="nexb_user", password="secret")
        self.assertEqual(200, self.client.get(url).status_code)

    def test_workflow_request_details_view_invalid_uuid(self):
        self.client.login(username="nexb_user", password="secret")
        # Proper UUID but non existing
        url = reverse("workflow:request_details", args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

        # Badly formed UUID string
        url = "/requests/99999/"
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_workflow_request_details_view_is_private_availability(self):
        url = self.request1.get_absolute_url()
        self.request1.requester = self.requester_user
        self.request1.save()

        # A basic user can access any non-private Request in his dataspace.
        self.assertFalse(self.request1.is_private)
        self.client.login(username="nexb_user", password="secret")
        self.assertEqual(200, self.client.get(url).status_code)
        self.client.login(username="basic_user", password="secret")
        self.assertEqual(200, self.client.get(url).status_code)

        self.request1.is_private = True
        self.request1.save()
        self.assertTrue(self.nexb_user.is_superuser)
        self.client.login(username="nexb_user", password="secret")
        self.assertEqual(200, self.client.get(url).status_code)
        self.assertFalse(self.basic_user.is_superuser)
        self.client.login(username="basic_user", password="secret")
        self.assertEqual(404, self.client.get(url).status_code)

        self.request1.requester = self.basic_user
        self.request1.save()
        self.assertTrue(self.nexb_user.is_superuser)
        self.client.login(username="nexb_user", password="secret")
        self.assertEqual(200, self.client.get(url).status_code)
        self.assertFalse(self.basic_user.is_superuser)
        self.client.login(username="basic_user", password="secret")
        self.assertEqual(200, self.client.get(url).status_code)

    def test_show_all_in_requests_list_view(self):
        self.assertFalse(self.basic_user.is_superuser)
        self.assertNotEqual(self.basic_user, self.request1.requester)

        self.client.login(username="basic_user", password="secret")
        url = reverse("workflow:request_list")

        response = self.client.get("{}?requester={}".format(url, self.basic_user.username))
        self.assertContains(response, "{}".format(self.some_request.uuid))
        self.assertNotContains(response, "{}".format(self.request1.uuid))

        response = self.client.get("{}?requester=".format(url))
        self.assertContains(response, "{}".format(self.some_request.uuid))
        self.assertContains(response, "{}".format(self.request1.uuid))

    def test_show_all_visibility_of_private_in_requests_list_view(self):
        self.assertFalse(self.basic_user.is_superuser)
        self.assertNotEqual(self.basic_user, self.request1.requester)

        self.client.login(username="basic_user", password="secret")
        url = reverse("workflow:request_list")

        product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )

        self.request1.object_id = self.component1.id
        self.request1.is_private = True
        self.request1.product_context = product1
        self.request1.save()
        assign_perm("view_product", self.basic_user, product1)

        RequestComment.objects.create(
            request=self.request1,
            user=self.basic_user,
            text="Comment1",
            dataspace=self.nexb_dataspace,
        )

        expected = '<a href="{}">#{} {}</a>'.format(
            self.request1.get_absolute_url(), self.request1.id, self.request1.title
        )
        expected2 = 'title="This request is private."'
        expected3 = "{}#comments".format(self.request1.get_absolute_url())

        response = self.client.get(url)
        self.assertNotContains(response, expected)
        self.assertContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, product1)

        self.request1.requester = self.basic_user
        self.request1.save()
        response = self.client.get(url)
        self.assertContains(response, expected)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, product1)

    def test_workflow_request_details_view_add_request_of_same_type(self):
        url = self.request1.get_absolute_url()
        self.client.login(username=self.requester_user.username, password="secret")
        response = self.client.get(url)

        new_request_url = self.request1.request_template.get_absolute_url()
        expected = (
            f'<a href="{new_request_url}" class="btn btn-success" '
            f'   data-bs-toggle="tooltip" title="Add a new Request of the same type">'
            f" New Request"
            f"</a>"
        )
        self.assertContains(response, expected, html=True)

    def test_workflow_request_details_view_close_request(self):
        self.request1.assignee = self.basic_user
        self.request1.save()

        url = self.request1.get_absolute_url()
        expected = "Close this Request"
        data = {"closed_reason": "REASON"}

        self.assertNotEqual(self.request1.requester, self.requester_user)
        self.client.login(username=self.requester_user.username, password="secret")
        response = self.client.get(url)
        self.assertNotContains(response, expected)

        self.client.post(url, data)
        self.request1.refresh_from_db()
        self.assertEqual(0, self.request1.comments.count())
        self.assertNotEqual(self.request1.status, Request.Status.CLOSED)
        self.assertEqual(0, len(mail.outbox))

        self.assertEqual(self.request1.requester, self.nexb_user)
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)

        response = self.client.post(url, data, follow=True)
        self.request1.refresh_from_db()
        self.assertEqual(1, self.request1.events.count())
        self.assertEqual(self.request1.status, Request.Status.CLOSED)
        self.assertEqual(self.request1.last_modified_by, self.nexb_user)
        self.assertContains(response, "Request {} closed".format(self.request1))
        self.assertEqual(1, len(mail.outbox))

        event = self.request1.events.latest("id")
        self.assertEqual(self.nexb_user, event.user)
        self.assertEqual("REASON", event.text)
        self.assertEqual(RequestEvent.CLOSED, event.event_type)

    def _post_file_data(self, url, file_location):
        with open(file_location, "rb") as fp:
            data = {
                "submit": "Upload",
                "file": fp,
            }
            return self.client.post(url, data, follow=True)

    def test_workflow_request_details_view_upload_attachment(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request1.get_absolute_url()
        filename = os.path.basename(__file__)
        response = self._post_file_data(url, __file__)

        self.assertContains(response, "Attachment &quot;{}&quot; added.".format(filename))
        expected = """
        <a href="#attachments" title="View attachments" data-scroll-to="#attachments_section">
            <i class="fas fa-file"></i>
            1 attachment
        </a>
        """
        self.assertContains(response, expected, html=True)
        self.assertEqual(1, self.request1.attachments.count())
        self.assertEqual(self.nexb_user, self.request1.attachments.latest("id").uploader)
        event = self.request1.events.latest("id")

        self.assertEqual(self.nexb_user, event.user)
        self.assertIn(filename, event.text)
        self.assertEqual(RequestEvent.ATTACHMENT, event.event_type)

        # Again with a Request in another dataspace
        url = self.other_request.get_absolute_url()
        response = self._post_file_data(url, __file__)
        self.assertEqual(404, response.status_code)

    def test_workflow_request_details_view_delete_attachment(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request1.get_absolute_url()
        self._post_file_data(url, __file__)
        attachment = self.request1.attachments.latest("id")
        self.assertTrue(attachment.has_delete_permission(self.nexb_user))
        response = self.client.get(url)
        self.assertContains(response, '"delete_attachment_link"')

        self.client.login(username="basic_user", password="secret")
        self.assertFalse(attachment.has_delete_permission(self.basic_user))
        response = self.client.get(url)
        self.assertNotContains(response, '"delete_attachment_link"')
        data = {
            "delete_attachment_uuid": attachment.uuid,
        }
        response = self.client.post(url, data, follow=True)
        expected = """
        <a href="#attachments" title="View attachments" data-scroll-to="#attachments_section">
            <i class="fas fa-file"></i>
            1 attachment
        </a>
        """
        self.assertContains(response, expected, html=True)
        self.assertEqual(1, self.request1.attachments.count())

        self.client.login(username="nexb_user", password="secret")
        self.assertTrue(attachment.has_delete_permission(self.nexb_user))
        response = self.client.get(url)
        self.assertContains(response, '"delete_attachment_link"')
        response = self.client.post(url, data, follow=True)
        expected = """
        <a href="#attachments" title="Add attachments" data-scroll-to="#attachments_section">
            <i class="far fa-file"></i>
            0 attachments
        </a>
        """
        self.assertContains(response, expected, html=True)
        self.assertEqual(0, self.request1.attachments.count())

    def test_workflow_request_details_view_attachment_missing_file(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.request1.get_absolute_url()
        RequestAttachment.objects.create(
            request=self.request1,
            uploader=self.basic_user,
            file="filename.ext",
            dataspace=self.nexb_dataspace,
        )
        response = self.client.get(url)
        expected = """
        <a href="#attachments" title="Add attachments" data-scroll-to="#attachments_section">
            <i class="far fa-file"></i>
            0 attachments
        </a>
        """
        self.assertContains(response, expected, html=True)

    def test_workflow_request_send_attachment_view(self):
        self.client.login(username="nexb_user", password="secret")
        # We do not serve file using the MEDIA_URL settings
        self.assertEqual(404, self.client.get("/media/").status_code)

        url = self.request1.get_absolute_url()
        attachment_file_path = Path(__file__)
        self._post_file_data(url, attachment_file_path)

        response = self.client.get(url)
        attachment = self.request1.attachments.latest("id")
        attachment_url = reverse("workflow:send_attachment", args=[attachment.uuid])
        self.assertContains(response, attachment_url)
        response = self.client.get(attachment_url)
        self.assertTrue(attachment.request.has_details_permission(self.nexb_user))
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/x-python", response.get("content-type"))
        expected = 'attachment; filename="test_views.py"'
        self.assertEqual(expected, response.get("content-disposition"))
        self.assertEqual(attachment_file_path.read_bytes(), response.getvalue())

        self.nexb_user.dataspace = self.other_dataspace
        self.nexb_user.save()
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(attachment_url)
        self.assertEqual(404, response.status_code)

        self.nexb_user.dataspace = self.nexb_dataspace
        self.nexb_user.save()

        attachment.request.is_private = True
        attachment.request.save()
        self.assertFalse(attachment.request.has_details_permission(self.basic_user))
        self.client.login(username=self.basic_user.username, password="secret")
        response = self.client.get(attachment_url)
        self.assertEqual(404, response.status_code)

        self.client.logout()
        response = self.client.get(attachment_url)
        self.assertRedirects(response, f'{reverse("login")}?next={attachment_url}')

    def test_workflow_request_details_view_product_context_links(self):
        self.client.login(username=self.nexb_user.username, password="secret")
        url = self.request1.get_absolute_url()

        product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )
        self.request1.product_context = product1
        self.request1.save()

        self.nexb_user.is_superuser = False
        self.nexb_user.save()

        assign_perm("view_product", self.nexb_user, product1)

        expected1 = '<a href="{}" target="_blank">product1</a>'.format(product1.get_absolute_url())
        expected2 = (
            f'<a href="{product1.get_absolute_url()}#inventory" target="_blank">View Inventory</a>'
        )

        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)
        self.assertFalse(self.nexb_user.has_perm("product_portfolio.change_productcomponent"))

        self.nexb_user = add_perm(self.nexb_user, "change_productcomponent")
        self.client.get(url)
        self.assertTrue(self.nexb_user.has_perm("product_portfolio.change_productcomponent"))

    def test_workflow_request_details_view_product_summary(self):
        self.client.login(username=self.nexb_user.username, password="secret")
        url = self.request1.get_absolute_url()
        product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )

        self.request_template1.content_type = self.product_ct
        self.request_template1.save()
        self.request1.content_object = product1
        self.request1.save()

        status1 = ProductRelationStatus.objects.create(label="s1", dataspace=self.nexb_dataspace)
        ProductComponent.objects.create(
            product=product1,
            component=self.component1,
            review_status=status1,
            dataspace=self.nexb_dataspace,
        )
        ProductComponent.objects.create(
            product=product1, name="c2", review_status=status1, dataspace=self.nexb_dataspace
        )
        package1 = Package.objects.create(filename="p1", dataspace=self.nexb_dataspace)
        ProductPackage.objects.create(
            product=product1, package=package1, review_status=status1, dataspace=self.nexb_dataspace
        )

        response = self.client.get(url)
        self.assertContains(response, "Product summary:")
        self.assertContains(response, "Catalogs:")
        expected = (
            f'<a href="{product1.get_absolute_url()}?inventory-review_status={status1}'
            f'&inventory-object_type=catalog#inventory">{status1.label} (1)</a>'
        )
        self.assertContains(response, expected, html=True)

        self.assertContains(response, "Custom Components:")
        expected = (
            f'<a href="{product1.get_absolute_url()}?inventory-review_status={status1}'
            f'&inventory-object_type=custom#inventory">{status1.label} (1)</a>'
        )
        self.assertContains(response, expected, html=True)

        self.assertContains(response, "Packages:")
        expected = (
            f'<a href="{product1.get_absolute_url()}?inventory-review_status={status1}'
            f'&inventory-object_type=package#inventory">{status1.label} (1)</a>'
        )
        self.assertContains(response, expected, html=True)

    def test_workflow_notification_request_slack_payload(self):
        site_url = settings.SITE_URL.rstrip("/")
        expected = {
            "attachments": [
                {
                    "fallback": f"#{self.request1.id} Title1 created by nexb_user",
                    "pretext": "[DejaCode/nexB] Request created by nexb_user",
                    "color": "#5bb75b",
                    "title": f"#{self.request1.id} Title1",
                    "title_link": f"{site_url}/requests/{self.request1.uuid}/",
                    "text": "Template1",
                    "fields": [
                        {"title": "Assigned to", "value": "None", "short": True},
                        {"title": "Status", "value": "Open", "short": True},
                        {"title": "Priority", "value": "Urgent", "short": True},
                    ],
                    "ts": f"{self.request1.last_modified_date.timestamp()}",
                }
            ]
        }
        payload = request_slack_payload(self.request1, created=True)
        self.assertEqual(expected, payload)

    def test_workflow_notification_request_comment_slack_payload(self):
        site_url = settings.SITE_URL.rstrip("/")
        self.request1.assignee = self.nexb_user
        self.request1.save()
        comment = self.request1.comments.create(
            user=self.basic_user, text="Comment1", dataspace=self.nexb_dataspace
        )

        pretext = (
            f"[DejaCode/{self.nexb_dataspace.name}] "
            f"New comment by {comment.user.username} on Request "
            f"<{site_url}/requests/{self.request1.uuid}/|#{self.request1.id} Title1> "
            f"(assigned to {self.request1.assignee.username})"
        )
        expected = {
            "attachments": [
                {
                    "fallback": pretext,
                    "pretext": pretext,
                    "text": "Comment1",
                    "color": "#ff9d2e",
                    "ts": f"{comment.last_modified_date.timestamp()}",
                }
            ]
        }
        payload = request_comment_slack_payload(comment)
        self.assertEqual(expected, payload)


class RequestInComponentCatalogTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.user = create_superuser("nexb_user", self.nexb_dataspace)
        self.super_user = create_superuser("super_user", self.nexb_dataspace)
        self.basic_user = create_user("basic_user", self.nexb_dataspace)

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")

        self.component1 = Component.objects.create(
            dataspace=self.nexb_dataspace,
            name="Component1",
            version="1.0BETA",
        )

        self.component2 = Component.objects.create(
            dataspace=self.nexb_dataspace,
            name="Component2",
            version="2.0BETA",
        )

        self.product1 = self.product_ct.model_class().objects.create(
            name="product1", dataspace=self.nexb_dataspace
        )

        self.sub_comp1 = Subcomponent.objects.create(
            parent=self.component2,
            child=self.component1,
            dataspace=self.nexb_dataspace,
        )

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            is_active=True,
            dataspace=self.nexb_dataspace,
            content_type=self.component_ct,
        )

        self.request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.user,
            dataspace=self.nexb_dataspace,
            content_type=self.component_ct,
            content_object=self.component1,
        )

    def test_visibility_of_non_private_request_in_subcomponent_tab(self):
        self.assertTrue(self.super_user.is_superuser)
        self.assertFalse(self.basic_user.is_superuser)

        self.request1.object_id = self.component1.id
        self.request1.is_private = False
        self.request1.save()

        url = self.component1.get_absolute_url()

        expected = '<a href="{}">#{} {}</a>'.format(
            self.request1.get_absolute_url(), self.request1.id, self.request1.title
        )

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)

        self.client.login(username="basic_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)

    def test_visibility_of_private_request_in_subcomponent_tab(self):
        self.assertTrue(self.super_user.is_superuser)
        self.assertFalse(self.basic_user.is_superuser)
        self.assertNotEqual(self.request1.requester, self.basic_user)

        self.request1.object_id = self.component1.id
        self.request1.is_private = True
        self.request1.product_context = self.product1
        self.request1.save()

        RequestComment.objects.create(
            request=self.request1,
            user=self.basic_user,
            text="Comment1",
            dataspace=self.nexb_dataspace,
        )

        url = self.component1.get_absolute_url()

        expected = '<a href="{}">#{} {}</a>'.format(
            self.request1.get_absolute_url(), self.request1.id, self.request1.title
        )
        expected2 = 'title="This request is private."'
        expected3 = "{}#comments".format(self.request1.get_absolute_url())

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, self.product1)

        assign_perm("view_product", self.basic_user, self.product1)
        self.client.login(username="basic_user", password="secret")
        response = self.client.get(url)
        self.assertNotContains(response, expected)
        self.assertContains(response, expected2)
        self.assertNotContains(response, expected3)
        self.assertNotContains(response, self.product1)

        self.request1.requester = self.basic_user
        self.request1.save()

        self.client.login(username="basic_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)
        self.assertContains(response, expected2)
        self.assertContains(response, expected3)
        self.assertContains(response, self.product1)

    def test_component_catalog_details_view_with_requests_num_queries(self):
        self.client.login(username="nexb_user", password="secret")
        url = self.component1.get_absolute_url()

        self.request1.object_id = self.component1.id
        self.request1.save()

        RequestComment.objects.create(
            request=self.request1,
            user=self.basic_user,
            text="Comment1",
            dataspace=self.nexb_dataspace,
        )
        RequestComment.objects.create(
            request=self.request1,
            user=self.basic_user,
            text="Comment2",
            dataspace=self.nexb_dataspace,
        )

        RequestAttachment.objects.create(
            request=self.request1,
            uploader=self.basic_user,
            file="filename.ext",
            dataspace=self.nexb_dataspace,
        )
        RequestAttachment.objects.create(
            request=self.request1,
            uploader=self.basic_user,
            file="filename.ext",
            dataspace=self.nexb_dataspace,
        )

        # Creating more Request to check for duplicate Queries
        self.request1.id = None
        self.request1.uuid = uuid.uuid4()
        self.request1.save()

        self.request1.id = None
        self.request1.uuid = uuid.uuid4()
        self.request1.save()

        self.assertEqual(3, self.component1.get_requests(self.user).count())

        with self.assertNumQueries(28):
            self.client.get(url)

    @override_settings(ANONYMOUS_USERS_DATASPACE="nexB")
    def test_request_link_icon_displayed_in_component_list_view(self):
        url = reverse("component_catalog:component_list")
        expected = '"{}#activity"'.format(self.component1.get_absolute_url())

        response = self.client.get(url)
        self.assertNotContains(response, expected)

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)

    @override_settings(ANONYMOUS_USERS_DATASPACE="nexB")
    def test_request_link_icon_displayed_in_subcomponent_tab_view(self):
        url = self.component2.get_absolute_url()
        expected = '"{}#activity"'.format(self.component1.get_absolute_url())

        response = self.client.get(url)
        self.assertNotContains(response, expected)

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)

    @override_settings(ANONYMOUS_USERS_DATASPACE="nexB")
    def test_request_link_icon_displayed_in_hierarchy_tab_view(self):
        url = self.component1.get_absolute_url()
        expected = '<a href="#activity" data-bs-toggle="tooltip" title="Requests">'
        response = self.client.get(url)
        self.assertNotContains(response, expected)

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected)

    @override_settings(ANONYMOUS_USERS_DATASPACE="nexB")
    def test_requests_button_with_choice_from_component_details_view(self):
        url = self.component1.get_absolute_url()
        expected1 = (
            '<a class="btn btn-request dropdown-toggle" data-bs-toggle="dropdown" '
            'role="button" href="#">Requests</a>'
        )
        expected2 = '<a class="dropdown-item" href="{}?content_object_id={}">{}</a>'.format(
            self.request_template1.get_absolute_url(),
            self.component1.id,
            self.request_template1.name,
        )

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertContains(response, expected1)
        self.assertContains(response, expected2)

        self.request_template1.is_active = False
        self.request_template1.save()
        self.assertFalse(
            RequestTemplate.objects.scope(self.nexb_dataspace)
            .actives()
            .for_content_type(self.component_ct)
            .exists()
        )

        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)

        self.request_template1.is_active = True
        self.request_template1.include_applies_to = False
        self.request_template1.save()
        self.client.login(username="nexb_user", password="secret")
        response = self.client.get(url)
        self.assertNotContains(response, expected1)
        self.assertNotContains(response, expected2)
