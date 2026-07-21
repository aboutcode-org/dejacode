#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dje.models import Dataspace
from dje.tests import create_superuser
from notification.models import WebhookSubscription
from notification.tasks import deliver_webhook_task
from product_portfolio.tests import make_product
from workflow.models import Priority
from workflow.models import Question
from workflow.models import Request
from workflow.models import RequestComment
from workflow.models import RequestTemplate


class DeliverWebhookTaskTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.webhook = WebhookSubscription.objects.create(
            dataspace=self.dataspace,
            target_url="http://127.0.0.1:8000/",
            event="policy.violation_detected",
        )

    @patch("notification.models.WebhookSubscription.deliver")
    def test_deliver_webhook_task_resolves_secured_model_instance(self, mock_deliver):
        product = make_product(self.dataspace)
        deliver_webhook_task(
            webhook_subscription_uuid=self.webhook.uuid,
            payload_override={"text": "test"},
            instance_app_label="product_portfolio",
            instance_model_name="product",
            instance_pk=product.pk,
        )
        mock_deliver.assert_called_once()
        delivered_instance = mock_deliver.call_args[0][0]
        self.assertEqual(product, delivered_instance)

    def test_deliver_webhook_task_missing_subscription_logs_error(self):
        with self.assertLogs("dje", level="ERROR") as captured:
            deliver_webhook_task(webhook_subscription_uuid=uuid.uuid4())
        self.assertTrue(any("not found" in line for line in captured.output))

    def test_deliver_webhook_task_missing_instance_logs_error(self):
        with self.assertLogs("dje", level="ERROR") as captured:
            deliver_webhook_task(
                webhook_subscription_uuid=self.webhook.uuid,
                instance_app_label="product_portfolio",
                instance_model_name="product",
                instance_pk=99999999,
            )
        self.assertTrue(any("not found" in line for line in captured.output))


class NotificationTasksTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)

        self.component_ct = ContentType.objects.get(
            app_label="component_catalog", model="component"
        )

        self.request_template1 = RequestTemplate.objects.create(
            name="Template1",
            description="Header Desc1",
            dataspace=self.nexb_user.dataspace,
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

        self.priority1 = Priority.objects.create(label="Urgent", dataspace=self.nexb_dataspace)

    @patch("requests.post")
    def test_notification_task_on_workflow_request_creation_generic_url(self, method_mock):
        method_mock.return_value = None

        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        target_url = "http://127.0.0.1:8000/"
        webhook = WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url=target_url,
            event="request.added",
        )

        data = {
            "title": "Title",
            "field_0": "Value for field_0",
            "content_type": self.component_ct.id,
            "assignee": self.nexb_user.id,
        }
        self.client.post(url, data)
        request1 = Request.objects.latest("id")
        self.assertTrue(request1)

        results = json.loads(method_mock.call_args_list[0][1]["data"])
        expected = {
            "uuid": str(webhook.uuid),
            "event": "request.added",
            "target": target_url,
        }
        self.assertEqual(expected, results["hook"])
        data = results["data"]
        self.assertEqual(str(request1.uuid), data["uuid"])
        self.assertEqual(request1.title, data["title"])
        self.assertEqual(self.request_template1.name, data["request_template_name"])
        self.assertEqual("open", data["status"])
        self.assertEqual(self.nexb_user.username, data["assignee"])

    @patch("requests.post")
    def test_notification_task_on_workflow_request_creation_slack_url(self, method_mock):
        method_mock.return_value = None

        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()
        site_url = settings.SITE_URL.rstrip("/")

        target_url = "https://hooks.slack.com"
        WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url=target_url,
            event="request.added",
        )

        data = {
            "title": "Title",
            "field_0": "Value for field_0",
            "content_type": self.component_ct.id,
            "assignee": self.nexb_user.id,
        }
        self.client.post(url, data)
        request1 = Request.objects.latest("id")
        self.assertTrue(request1)

        results = json.loads(method_mock.call_args_list[0][1]["data"])
        expected = [
            {
                "fallback": f"#{request1.id} {request1.title} created by nexb_user",
                "pretext": "[DejaCode/nexB] Request created by nexb_user",
                "color": "#5bb75b",
                "title": f"#{request1.id} {request1.title}",
                "title_link": f"{site_url}{request1.get_absolute_url()}",
                "text": "Template1",
                "fields": [
                    {"title": "Assigned to", "value": "nexb_user", "short": True},
                    {"title": "Status", "value": "Open", "short": True},
                ],
                "ts": f"{request1.last_modified_date.timestamp()}",
            }
        ]

        self.assertEqual(expected, results["attachments"])

    @patch("requests.post")
    def test_notification_task_on_workflow_request_edition_generic_url(self, method_mock):
        method_mock.return_value = None

        self.client.login(username="nexb_user", password="secret")

        target_url = "http://127.0.0.1:8000/"
        webhook = WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url=target_url,
            event="request.updated",
        )

        request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.nexb_user,
            assignee=self.nexb_user,
            dataspace=self.nexb_dataspace,
            content_type=self.component_ct,
        )
        # No webhook set for event 'request.added'
        self.assertFalse(method_mock.call_args_list)

        request1.title = "New title"
        request1.save()
        results = json.loads(method_mock.call_args_list[0][1]["data"])
        expected = {
            "uuid": str(webhook.uuid),
            "event": "request.updated",
            "target": target_url,
        }
        self.assertEqual(expected, results["hook"])
        data = results["data"]
        self.assertEqual(str(request1.uuid), data["uuid"])
        self.assertEqual(request1.title, data["title"])
        self.assertEqual(self.request_template1.name, data["request_template_name"])
        self.assertEqual("open", data["status"])
        self.assertEqual(self.nexb_user.username, data["assignee"])

    @patch("requests.post")
    def test_notification_task_on_workflow_request_edition_slack_url(self, method_mock):
        method_mock.return_value = None

        self.client.login(username="nexb_user", password="secret")
        site_url = settings.SITE_URL.rstrip("/")

        target_url = "https://hooks.slack.com"
        WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url=target_url,
            event="request.updated",
        )

        request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.nexb_user,
            assignee=self.nexb_user,
            dataspace=self.nexb_dataspace,
            content_type=self.component_ct,
        )
        # No webhook set for event 'request.added'
        self.assertFalse(method_mock.call_args_list)

        request1.title = "New title"
        request1.save()
        results = json.loads(method_mock.call_args_list[0][1]["data"])

        expected = [
            {
                "fallback": f"#{request1.id} {request1.title} updated by None",
                "pretext": "[DejaCode/nexB] Request updated by None",
                "color": "#ff9d2e",
                "title": f"#{request1.id} {request1.title}",
                "title_link": f"{site_url}{request1.get_absolute_url()}",
                "text": "Template1",
                "fields": [
                    {"title": "Assigned to", "value": "nexb_user", "short": True},
                    {"title": "Status", "value": "Open", "short": True},
                ],
                "ts": f"{request1.last_modified_date.timestamp()}",
            }
        ]

        self.assertEqual(expected, results["attachments"])

    @patch("requests.post")
    def test_notification_task_on_workflow_request_add_comment_generic_url(self, method_mock):
        method_mock.return_value = None

        self.client.login(username="nexb_user", password="secret")
        request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.nexb_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )
        url = request1.get_absolute_url()

        target_url = "http://127.0.0.1:8000/"
        webhook = WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url=target_url,
            event="request_comment.added",
        )

        data = {"comment_content": "A comment content"}
        self.client.post(url, data, follow=True)
        comment = RequestComment.objects.latest("id")
        self.assertTrue(comment)

        results = json.loads(method_mock.call_args_list[0][1]["data"])
        expected = {
            "uuid": str(webhook.uuid),
            "event": "request_comment.added",
            "target": target_url,
        }
        self.assertEqual(expected, results["hook"])
        data = results["data"]
        self.assertEqual(str(comment.uuid), data["uuid"])
        self.assertEqual("nexb_user", data["user"])
        self.assertEqual("A comment content", data["text"])

    @patch("requests.post")
    def test_notification_task_on_workflow_request_add_comment_slack_url(self, method_mock):
        method_mock.return_value = None

        self.client.login(username="nexb_user", password="secret")
        request1 = Request.objects.create(
            title="Title1",
            request_template=self.request_template1,
            requester=self.nexb_user,
            dataspace=self.nexb_user.dataspace,
            content_type=self.component_ct,
        )
        url = request1.get_absolute_url()
        site_url = settings.SITE_URL.rstrip("/")

        target_url = "https://hooks.slack.com"
        WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url=target_url,
            event="request_comment.added",
        )

        data = {"comment_content": "A comment content"}
        self.client.post(url, data, follow=True)
        comment = RequestComment.objects.latest("id")
        self.assertTrue(comment)
        req = comment.request

        results = json.loads(method_mock.call_args_list[0][1]["data"])
        pretext = (
            f"[DejaCode/{req.dataspace.name}] New comment by {comment.user} on Request "
            f"<{site_url}{req.get_absolute_url()}|#{req.id} {req.title}> "
            f"(assigned to {req.assignee})"
        )
        expected = [
            {
                "fallback": pretext,
                "pretext": pretext,
                "color": "#ff9d2e",
                "text": "A comment content",
                "ts": f"{comment.last_modified_date.timestamp()}",
            }
        ]

        self.assertEqual(expected, results["attachments"])

    @patch("requests.post")
    def test_notification_webhook_extra_payload_merged_into_payload(self, method_mock):
        method_mock.return_value = None

        self.client.login(username="nexb_user", password="secret")
        url = self.request_template1.get_absolute_url()

        extra_payload = {"custom_key": "custom_value", "title": "overridden_title"}
        WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url="https://localhost",
            event="request.added",
            extra_payload=extra_payload,
        )

        data = {
            "title": "Title",
            "field_0": "Value for field_0",
            "content_type": self.component_ct.id,
            "assignee": self.nexb_user.id,
        }
        self.client.post(url, data)

        results = json.loads(method_mock.call_args_list[0][1]["data"])
        self.assertEqual("custom_value", results["data"]["custom_key"])
        self.assertEqual("overridden_title", results["data"]["title"])
