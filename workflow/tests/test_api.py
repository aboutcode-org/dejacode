#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient

from dje.api_custom import TabPermission
from dje.models import Dataspace
from dje.models import History
from dje.tests import create_admin
from dje.tests import create_superuser
from dje.tests import create_user
from workflow.api import RequestTemplateViewSet
from workflow.api import RequestViewSet
from workflow.models import Priority
from workflow.models import Question
from workflow.models import Request
from workflow.models import RequestEvent
from workflow.models import RequestTemplate

Product = apps.get_model("product_portfolio", "Product")


@override_settings(
    EMAIL_HOST_USER="user",
    EMAIL_HOST_PASSWORD="password",
    EMAIL_HOST="localhost",
    EMAIL_PORT=25,
    DEFAULT_FROM_EMAIL="webmaster@localhost",
)
class RequestAPITestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.alternate_dataspace = Dataspace.objects.create(name="Alternate")
        self.base_user = create_user("base_user", self.dataspace, workflow_email_notification=True)
        self.admin_user = create_admin("admin_user", self.dataspace)
        self.super_user = create_superuser("super_user", self.dataspace)

        self.request_list_url = reverse("api_v2:request-list")

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )
        self.component1 = self.component_ct.model_class().objects.create(
            name="component1", dataspace=self.dataspace
        )

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.dataspace,
            content_type=self.component_ct,
        )
        self.request_template1_detail_url = reverse(
            "api_v2:requesttemplate-detail", args=[self.request_template1.uuid]
        )

        self.question1 = Question.objects.create(
            template=self.request_template1,
            label="Organization",
            help_text="Your Organization (Department) name",
            input_type="TextField",
            is_required=True,
            position=0,
            dataspace=self.dataspace,
        )

        self.question2 = Question.objects.create(
            template=self.request_template1,
            label="Project",
            help_text="",
            input_type="TextField",
            is_required=False,
            position=1,
            dataspace=self.dataspace,
        )

        self.question3 = Question.objects.create(
            template=self.request_template1,
            label="Modifications Planned?",
            help_text="",
            input_type="BooleanField",
            is_required=False,
            position=2,
            dataspace=self.dataspace,
        )

        self.priority1 = Priority.objects.create(label="Urgent", dataspace=self.dataspace)

        self.request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.base_user,
            dataspace=self.dataspace,
            content_object=self.component1,
            priority=self.priority1,
        )
        self.request1_detail_url = reverse("api_v2:request-detail", args=[self.request1.uuid])

        self.request2 = Request.objects.create(
            title="Title2",
            request_template=self.request_template1,
            requester=self.base_user,
            dataspace=self.dataspace,
            content_type=self.component_ct,
            assignee=self.super_user,
            status=Request.Status.CLOSED,
            serialized_data='[{"input_type": "CharField", "value": "string_for_search", '
            '"label": "Organization"}]',
        )
        self.request2_detail_url = reverse("api_v2:request-detail", args=[self.request2.uuid])

    def test_api_request_list_endpoint_results(self):
        self.client.login(username="super_user", password="secret")
        # Turned-off until stable
        # with self.assertNumQueries(6):
        response = self.client.get(self.request_list_url)

        self.assertContains(response, '"count":2,')
        self.assertContains(response, self.request1_detail_url)
        self.assertContains(response, self.request2_detail_url)
        self.assertEqual(2, response.data["count"])

    def test_api_request_secured_product_context_list_endpoint_results(self):
        product1 = Product.objects.create(name="p1", dataspace=self.dataspace)

        self.request1.product_context = product1
        self.request1.save()

        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.request_list_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, '"count":1,')
        self.assertNotContains(response, self.request1_detail_url)
        self.assertContains(response, self.request2_detail_url)
        self.assertEqual(1, response.data["count"])

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.request_list_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, '"count":1,')
        self.assertNotContains(response, self.request1_detail_url)
        self.assertContains(response, self.request2_detail_url)
        self.assertEqual(1, response.data["count"])

        assign_perm("view_product", self.admin_user, product1)
        response = self.client.get(self.request_list_url)
        self.assertContains(response, '"count":2,')
        self.assertContains(response, self.request1_detail_url)
        self.assertContains(response, self.request2_detail_url)
        self.assertEqual(2, response.data["count"])

    def test_api_request_secured_assigned_to_product_list_endpoint_results(self):
        product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")
        product1 = Product.objects.create(name="p1", dataspace=self.dataspace)

        # Force the product1 as content_object
        Request.objects.filter(pk=self.request1.pk).update(
            content_type=product_ct, object_id=product1.id
        )

        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.request_list_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, '"count":1,')
        self.assertNotContains(response, self.request1_detail_url)
        self.assertContains(response, self.request2_detail_url)
        self.assertEqual(1, response.data["count"])

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.request_list_url)
        self.assertEqual(200, response.status_code)
        self.assertContains(response, '"count":1,')
        self.assertNotContains(response, self.request1_detail_url)
        self.assertContains(response, self.request2_detail_url)
        self.assertEqual(1, response.data["count"])

        assign_perm("view_product", self.admin_user, product1)
        response = self.client.get(self.request_list_url)
        self.assertContains(response, '"count":2,')
        self.assertContains(response, self.request1_detail_url)
        self.assertContains(response, self.request2_detail_url)
        self.assertEqual(2, response.data["count"])

    def test_api_request_list_endpoint_options(self):
        client = APIClient()
        client.login(username="super_user", password="secret")
        response = client.options(self.request_list_url, format="json")
        actions_post = response.data["actions"]["POST"]

        # Tests the Dataspace scoping
        Priority.objects.create(label="Alternate", dataspace=self.alternate_dataspace)
        create_user("alternate_user", self.alternate_dataspace)

        expected = ["Open", "Closed", "Draft"]
        display_names = [
            choice.get("display_name") for choice in actions_post["status"].get("choices")
        ]
        self.assertEqual(expected, display_names)

        self.assertFalse(bool(actions_post["product_context"].get("choices")))
        self.assertEqual("field", actions_post["product_context"].get("type"))

        self.assertFalse(bool(actions_post["request_template"].get("choices")))
        self.assertFalse(bool(actions_post["priority"].get("choices")))
        self.assertFalse(bool(actions_post["assignee"].get("choices")))

    def test_api_request_list_endpoint_search(self):
        self.client.login(username="super_user", password="secret")
        data = {"search": "string_for_search"}
        response = self.client.get(self.request_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.request2_detail_url)
        self.assertNotContains(response, self.request1_detail_url)

        data = {"search": self.request1.title}
        response = self.client.get(self.request_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertNotContains(response, self.request2_detail_url)
        self.assertContains(response, self.request1_detail_url)

    def test_api_request_list_endpoint_filters(self):
        self.client.login(username="super_user", password="secret")
        data = {"assignee": self.super_user.username}
        response = self.client.get(self.request_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.request2_detail_url)

        data = {"requester": self.base_user.username}
        response = self.client.get(self.request_list_url, data)
        self.assertEqual(2, response.data["count"])

        data = {"content_type": self.component_ct.model}
        response = self.client.get(self.request_list_url, data)
        self.assertEqual(2, response.data["count"])

        data = {"status": Request.Status.CLOSED}
        response = self.client.get(self.request_list_url, data)
        self.assertEqual(1, response.data["count"])
        self.assertContains(response, self.request2_detail_url)

        data = {"request_template": self.request_template1}
        response = self.client.get(self.request_list_url, data)
        self.assertEqual(2, response.data["count"])

    def test_api_request_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        comment1 = self.request1.comments.create(
            user=self.request1.requester,
            text="Comment text",
            dataspace=self.request1.dataspace,
        )
        # Turned-off until stable
        # with self.assertNumQueries(5):
        response = self.client.get(self.request1_detail_url)

        self.assertContains(response, self.request1_detail_url)
        self.assertIn(self.request1_detail_url, response.data["api_url"])
        expected_url = f"http://testserver{self.request1.get_absolute_url()}"
        self.assertEqual(expected_url, response.data["absolute_url"])
        self.assertEqual(self.request1.status, response.data["status"])
        self.assertEqual(str(self.request1.uuid), response.data["uuid"])
        self.assertEqual(self.request1.title, response.data["title"])
        self.assertEqual(str(self.component1), response.data["content_object_display_name"])
        self.assertIn(
            reverse("api_v2:component-detail", args=[self.component1.uuid]),
            response.data["content_object"],
        )
        self.assertIn(self.request_template1_detail_url, response.data["request_template"])
        self.assertEqual(self.request_template1.name, response.data["request_template_name"])
        self.assertEqual({}, response.data["serialized_data"])
        self.assertEqual(str(self.request1.requester), response.data["requester"])
        self.assertEqual(self.request1.is_private, response.data["is_private"])
        self.assertEqual(self.request1.priority.label, response.data["priority"])
        self.assertIsNone(response.data["last_modified_by"])

        comment = response.data["comments"][0]
        self.assertEqual(str(comment1.uuid), comment["uuid"])
        self.assertEqual("base_user", comment["user"])
        self.assertEqual("Comment text", comment["text"])

    def test_api_secured_product_context_request_detail_endpoint(self):
        product1 = Product.objects.create(name="p1", dataspace=self.dataspace)
        product1_url = reverse("api_v2:product-detail", args=[product1.uuid])

        self.request1.product_context = product1
        self.request1.save()

        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.request1_detail_url)
        self.assertEqual(404, response.status_code)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.request1_detail_url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.admin_user, product1)
        response = self.client.get(self.request1_detail_url)
        self.assertIn(product1_url, response.data["product_context"])
        self.assertIn(self.request1_detail_url, response.data["api_url"])
        self.assertEqual(self.request1.status, response.data["status"])
        self.assertEqual(str(self.request1.uuid), response.data["uuid"])

    def test_api_secured_assigned_to_product_request_detail_endpoint(self):
        product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")
        product1 = product_ct.model_class().objects.create(name="p1", dataspace=self.dataspace)

        # Force the product1 as content_object
        Request.objects.filter(pk=self.request1.pk).update(
            content_type=product_ct, object_id=product1.id
        )

        self.client.login(username="base_user", password="secret")
        response = self.client.get(self.request1_detail_url)
        self.assertEqual(404, response.status_code)

        self.client.login(username="admin_user", password="secret")
        response = self.client.get(self.request1_detail_url)
        self.assertEqual(404, response.status_code)

        assign_perm("view_product", self.admin_user, product1)
        response = self.client.get(self.request1_detail_url)
        self.assertEqual(str(product_ct.model), response.data["content_type"])
        self.assertIn(
            reverse("api_v2:product-detail", args=[product1.uuid]), response.data["content_object"]
        )
        self.assertEqual(str(product1), response.data["content_object_display_name"])
        self.assertIn(self.request1_detail_url, response.data["api_url"])
        self.assertEqual(self.request1.status, response.data["status"])
        self.assertEqual(str(self.request1.uuid), response.data["uuid"])

    def test_api_request_endpoint_create(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "request_template": "",
            "status": "",
            "priority": "",
            "assignee": "",
            "product_context": "",
            "notes": "",
            "is_private": False,
        }
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "title": ["This field is required."],
            "request_template": ["This field may not be null."],
        }
        self.assertEqual(expected, response.json())

        data = {
            "title": "Title",
            "request_template": self.request_template1_detail_url,
        }
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        data = {
            "title": "Title",
            "request_template": self.request_template1_detail_url,
            "status": Request.Status.OPEN,
            "assignee": self.base_user.username,
            "notes": "some notes",
            "is_private": True,
            "product_context": "",
            "priority": "",
        }
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        request = Request.objects.latest("id")
        # last_modified_by is not set on creation
        self.assertIsNone(request.last_modified_by)

        history = History.objects.get_for_object(request).get()
        self.assertEqual("Added.", history.get_change_message())

        expected = "Request {} submitted by super_user in nexB".format(request)
        self.assertEqual(expected, mail.outbox[0].subject)
        body = mail.outbox[0].body
        expected = "super_user has submitted a new private request in the nexB dataspace"
        self.assertIn(expected, body)
        self.assertIn("- Request template: Template1", body)
        self.assertIn("- Product context: (none)", body)
        self.assertIn("- Applies to: (none)", body)
        self.assertIn("- Submitted by: super_user", body)
        self.assertIn("- Assigned to: base_user", body)
        self.assertIn("- Priority: (none)", body)
        self.assertIn(request.get_absolute_url(), body)

        product1 = Product.objects.create(name="p1", dataspace=self.dataspace)

        data.update(
            {
                "product_context": reverse("api_v2:product-detail", args=[product1.uuid]),
                "priority": self.priority1.label,
            }
        )

        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        # Reference by name instead of URI supports
        data["request_template"] = self.request_template1.name
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

    def test_api_request_endpoint_create_with_content_object(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "title": "Title",
            "request_template": self.request_template1_detail_url,
            "status": Request.Status.OPEN,
            "assignee": self.base_user.username,
            "content_object": "INVALID",
        }
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"content_object": ["Invalid hyperlink - No URL match."]}
        self.assertEqual(expected, response.data)

        data["content_object"] = self.request_template1_detail_url
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"content_object": ["Invalid Object type."]}
        self.assertEqual(expected, response.data)

        product_ct = ContentType.objects.get(app_label="product_portfolio", model="product")
        self.request_template1.content_type = product_ct
        self.request_template1.save()

        data["content_object"] = reverse("api_v2:component-detail", args=[self.component1.uuid])
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"content_object": ["Invalid Object type."]}
        self.assertEqual(expected, response.data)

        product1 = Product.objects.create(name="p1", dataspace=self.dataspace)
        data["content_object"] = reverse("api_v2:product-detail", args=[product1.uuid])
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        self.request_template1.include_applies_to = False
        self.request_template1.save()
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"content_object": ["Content object not available on this RequestTemplate."]}
        self.assertEqual(expected, response.data)

    def test_api_request_endpoint_create_with_cc_emails(self):
        self.client.login(username="super_user", password="secret")
        data = {
            "title": "Title",
            "request_template": self.request_template1_detail_url,
            "status": Request.Status.OPEN,
            "assignee": self.base_user.username,
            "cc_emails": ["a", "b"],
        }
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "cc_emails": {
                0: [ErrorDetail(string="Enter a valid email address.", code="invalid")],
                1: [ErrorDetail(string="Enter a valid email address.", code="invalid")],
            }
        }
        self.assertEqual(expected, response.data)

        data["cc_emails"] = "a@a.com,b@b.com"
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "cc_emails": {
                0: [ErrorDetail(string="Enter a valid email address.", code="invalid")],
            }
        }
        self.assertEqual(expected, response.data)

        data["cc_emails"] = ["a@a.com", "b@b.com"]
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)

        req = Request.objects.latest("id")
        self.assertEqual(data["cc_emails"], req.cc_emails)

    def test_api_request_endpoint_update_put(self):
        self.client.login(username="super_user", password="secret")
        self.assertEqual(0, self.request1.comments.count())

        self.assertEqual(self.request1.priority, self.priority1)
        put_data = json.dumps(
            {
                "priority": self.priority1.label,
                "status": Request.Status.CLOSED,
                "assignee": self.base_user.username,
            }
        )
        response = self.client.patch(
            self.request1_detail_url, data=put_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

        history = History.objects.get_for_object(self.request1, action_flag=History.CHANGE).latest(
            "id"
        )
        self.assertEqual("Changed status and assignee.", history.get_change_message())

        self.assertEqual(1, self.request1.events.count())
        self.assertEqual(RequestEvent.EDIT, self.request1.events.get().event_type)

        expected = f"Request {self.request1} for component1 updated by {self.super_user} in nexB"
        self.assertEqual(expected, mail.outbox[0].subject)
        body = mail.outbox[0].body
        expected = "The request {} has been updated in the nexB dataspace".format(self.request1)
        self.assertIn(expected, body)
        self.assertIn("- Request template: Template1", body)
        self.assertIn("- Product context: (none)", body)
        self.assertIn("- Applies to: component1", body)
        self.assertIn("- Submitted by: base_user", body)
        self.assertIn("- Assigned to: base_user", body)
        self.assertIn("- Priority: Urgent", body)
        self.assertIn("- Status: Closed", body)
        self.assertIn(self.request1.get_absolute_url(), body)

        # last_modified_by is set on edition
        self.request1.refresh_from_db()
        self.assertEqual(self.super_user, self.request1.last_modified_by)

    def test_api_request_endpoint_request_template_only_on_post(self):
        self.client.login(username="super_user", password="secret")
        request_template2 = RequestTemplate.objects.create(
            name="Template2", dataspace=self.dataspace, content_type=self.component_ct
        )

        patch_data = json.dumps({"request_template": request_template2.name})
        response = self.client.patch(
            self.request1_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        # The 'request_template' value is ignored on update
        self.assertEqual(self.request_template1, self.request1.request_template)

    def test_api_request_endpoint_dataspaced_slug_related_fields_scoping(self):
        self.client.login(username="super_user", password="secret")
        alternate_priority = Priority.objects.create(
            label="Alternate", dataspace=self.alternate_dataspace
        )
        alternate_user = create_user("alternate_user", self.alternate_dataspace)

        data = {
            "title": "Title",
            "request_template": reverse(
                "api_v2:requesttemplate-detail", args=[self.request_template1.uuid]
            ),
            "priority": alternate_priority.label,
            "assignee": alternate_user.username,
            "status": Request.Status.OPEN,
            "notes": "",
            "is_private": False,
            "product_context": "",
        }
        response = self.client.post(self.request_list_url, data)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {
            "priority": ["Object with label=Alternate does not exist."],
            "assignee": ["Object with username=alternate_user does not exist."],
        }
        self.assertEqual(expected, response.data)

    def test_api_request_endpoint_product_context_field(self):
        self.client.login(username="super_user", password="secret")

        self.assertIsNone(self.request1.product_context)
        product1 = Product.objects.create(name="p1", dataspace=self.dataspace)
        product_api_url = reverse("api_v2:product-detail", args=[product1.uuid])
        patch_data = json.dumps({"product_context": product_api_url})
        response = self.client.patch(
            self.request1_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.request1.refresh_from_db()
        self.assertEqual(product1, self.request1.product_context)

        alternate_product = Product.objects.create(name="p2", dataspace=self.alternate_dataspace)
        alternate_product_url = reverse("api_v2:product-detail", args=[alternate_product.uuid])
        patch_data = json.dumps({"product_context": alternate_product_url})
        response = self.client.patch(
            self.request1_detail_url, data=patch_data, content_type="application/json"
        )
        self.assertContains(response, "Invalid hyperlink - Object does not exist.", status_code=400)

    def test_api_request_template_detail_endpoint(self):
        self.client.login(username="super_user", password="secret")
        response = self.client.get(self.request_template1_detail_url)
        self.assertContains(response, self.request_template1_detail_url)

        questions = [
            {
                "label": "Organization",
                "help_text": "Your Organization (Department) name",
                "input_type": "TextField",
                "is_required": True,
                "position": 0,
            },
            {
                "label": "Project",
                "help_text": "",
                "input_type": "TextField",
                "is_required": False,
                "position": 1,
            },
            {
                "label": "Modifications Planned?",
                "help_text": "",
                "input_type": "BooleanField",
                "is_required": False,
                "position": 2,
            },
        ]

        expected = {
            "default_assignee": None,
            "description": "Header Desc1",
            "questions": questions,
            "is_active": False,
            "uuid": str(self.request_template1.uuid),
            "name": self.request_template1.name,
            "content_type": self.component_ct.model,
            "include_applies_to": True,
            "include_product": False,
            "form_data_layout": {
                "Project": "",
                "Organization": "",
                "Modifications Planned?": "",
            },
            "api_url": "http://testserver{}".format(self.request_template1_detail_url),
        }

        for key, value in expected.items():
            self.assertEqual(value, response.data.get(key))

    def test_api_request_endpoint_create_serialized_data(self):
        client = APIClient()
        client.login(username="super_user", password="secret")

        data = {
            "title": "Title",
            "request_template": self.request_template1_detail_url,
            "status": Request.Status.OPEN,
            "assignee": self.base_user.username,
            "notes": "some notes",
            "is_private": True,
            "include_applies_to": False,
            "product_context": "",
            "priority": "",
            "serialized_data": {},
        }

        # Empty possible
        response = client.post(self.request_list_url, data=data, format="json")
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        request = Request.objects.latest("id")
        self.assertEqual("{}", request.serialized_data)
        self.assertEqual({}, request.get_serialized_data())

        # Only dict value accepted
        data["serialized_data"] = "text"
        response = client.post(self.request_list_url, data=data, format="json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"serialized_data": ["Invalid data content."]}
        self.assertEqual(expected, response.data)

        # Only dict value accepted
        data["serialized_data"] = ["list"]
        response = client.post(self.request_list_url, data=data, format="json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

        # Wrong label
        data["serialized_data"] = {"Label1": "Value1", "Label2": "Value2"}
        response = client.post(self.request_list_url, data=data, format="json")
        expected = {"serialized_data": ['"Label1" is not a valid label.']}
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(expected, response.data)

        # Missing required label
        self.assertTrue(self.question1.is_required)
        data["serialized_data"] = {self.question2.label: "value"}
        response = client.post(self.request_list_url, data=data, format="json")
        expected = {"serialized_data": ['"Organization" is required.']}
        self.assertEqual(expected, response.data)

        # Missing value for required label
        data["serialized_data"] = {
            self.question1.label: "",
            self.question2.label: "value",
        }
        response = client.post(self.request_list_url, data=data, format="json")
        self.assertEqual(expected, response.data)

        # DateField input_type validation
        self.question2.label = "Date"
        self.question2.input_type = "DateField"
        self.question2.is_required = False
        self.question2.save()
        data["serialized_data"] = {
            self.question1.label: "Value1",
            self.question2.label: "not a date",
        }
        response = client.post(self.request_list_url, data=data, format="json")
        expected = {"serialized_data": ['Invalid date for "Date", use: YYYY-MM-DD.']}
        self.assertEqual(expected, response.data)

        # BooleanField input_type validation
        data["serialized_data"] = {
            self.question1.label: "Value1",
            self.question3.label: "not a boolean",
        }
        response = client.post(self.request_list_url, data=data, format="json")
        expected = {
            "serialized_data": ['"Modifications Planned?" only accept: true, false, "1", "0".'],
        }
        self.assertEqual(expected, response.data)

        # Proper data
        data["serialized_data"] = {
            self.question1.label: "Value1",
            self.question2.label: "1984-10-10",
            self.question3.label: "0",
        }
        response = client.post(self.request_list_url, data=data, format="json")
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        request = Request.objects.latest("id")
        self.assertEqual(json.dumps(data["serialized_data"]), request.serialized_data)
        self.assertEqual(data["serialized_data"], request.get_serialized_data())

        request_url = reverse("api_v2:request-detail", args=[request.uuid])
        response = client.get(request_url, format="json")
        self.assertEqual(data["serialized_data"], response.data["serialized_data"])

    def test_api_request_endpoint_edit_serialized_data(self):
        # See test_api_request_endpoint_create_serialized_data for full validation logic
        # This only make sure the validation are trigger as well for PUT and PATCH
        client = APIClient()
        client.login(username="super_user", password="secret")

        data = {
            "title": self.request1.title,
            "status": Request.Status.OPEN,
            "assignee": self.base_user.username,
            "serialized_data": "text",
        }

        # Only dict value accepted
        response = client.patch(self.request1_detail_url, data=data, format="json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"serialized_data": ["Invalid data content."]}
        self.assertEqual(expected, response.data)

        response = client.put(self.request1_detail_url, data=data, format="json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"serialized_data": ["Invalid data content."]}
        self.assertEqual(expected, response.data)

        # Missing required label
        self.assertTrue(self.question1.is_required)
        data["serialized_data"] = {self.question2.label: "value"}
        response = client.patch(self.request1_detail_url, data=data, format="json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        expected = {"serialized_data": ['"Organization" is required.']}
        self.assertEqual(expected, response.data)

    def test_api_request_and_request_template_endpoints_tab_permission(self):
        self.assertEqual((TabPermission,), RequestViewSet.extra_permissions)
        self.assertEqual((TabPermission,), RequestTemplateViewSet.extra_permissions)
