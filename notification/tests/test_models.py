#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings

import requests as req

from dje.models import Dataspace
from dje.tests import create_superuser
from notification.models import WebhookDelivery
from notification.models import WebhookSubscription
from notification.models import fire_webhooks


class WebhookSubscriptionQuerySetTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.active_webhook = WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url="http://1.2.3.4/",
            event="request.added",
            is_active=True,
        )
        self.inactive_webhook = WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url="http://1.2.3.5/",
            event="request.added",
            is_active=False,
        )

    def test_active_returns_only_active_subscriptions(self):
        active = list(WebhookSubscription.objects.active())
        self.assertIn(self.active_webhook, active)
        self.assertNotIn(self.inactive_webhook, active)


class WebhookSubscriptionModelTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)

        self.webhook = WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url="http://1.2.3.4/",
            event="request.added",
        )

    def test_webhook_subscription_str(self):
        self.assertEqual("request.added => http://1.2.3.4/", str(self.webhook))

    def test_webhook_subscription_dict(self):
        expected = {
            "uuid": str(self.webhook.uuid),
            "event": self.webhook.event,
            "target": self.webhook.target_url,
        }
        self.assertEqual(expected, self.webhook.dict())

    def test_webhook_subscription_get_headers_default(self):
        self.assertEqual({"Content-Type": "application/json"}, self.webhook.get_headers())

    def test_webhook_subscription_get_headers_with_extra(self):
        self.webhook.extra_headers = {"X-Token": "abc"}
        self.webhook.save()
        expected = {"Content-Type": "application/json", "X-Token": "abc"}
        self.assertEqual(expected, self.webhook.get_headers())

    def test_webhook_subscription_get_extra_headers(self):
        self.webhook.extra_headers = {"Header": "{{ENV_VALUE}}"}
        self.webhook.save()

        expected = {"Header": "{{ENV_VALUE}}"}
        self.assertEqual(expected, self.webhook.get_extra_headers())

        expected = {"Header": "some_value"}
        with override_settings(DEJACODE_WEBHOOK_ENV={"ENV_VALUE": "some_value"}):
            self.assertEqual(expected, self.webhook.get_extra_headers())

    @patch("requests.post")
    def test_webhook_subscription_deliver_inactive_returns_false(self, mock_post):
        self.webhook.is_active = False
        self.webhook.save()
        result = self.webhook.deliver(None, payload_override={"key": "val"})
        self.assertFalse(result)
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_webhook_subscription_deliver_request_exception_saves_error(self, mock_post):
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")
        delivery = self.webhook.deliver(None, payload_override={"key": "val"})
        self.assertIsNotNone(delivery)
        self.assertFalse(delivery.delivered)
        self.assertIn("Connection refused", delivery.delivery_error)

    @patch("requests.post")
    def test_webhook_subscription_deliver_payload_override_merges_extra_payload(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_post.return_value = mock_response
        self.webhook.extra_payload = {"env": "prod"}
        self.webhook.save()
        self.webhook.deliver(None, payload_override={"key": "val"})
        call_data = json.loads(mock_post.call_args[1]["data"])
        self.assertEqual("prod", call_data["env"])
        self.assertEqual("val", call_data["key"])

    @patch("requests.post")
    def test_webhook_subscription_deliver_payload_override_without_extra_payload(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_post.return_value = mock_response
        self.webhook.deliver(None, payload_override={"key": "val"})
        call_data = json.loads(mock_post.call_args[1]["data"])
        self.assertEqual({"key": "val"}, call_data)


class WebhookDeliveryModelTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.webhook = WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url="http://1.2.3.4/",
            event="request.added",
        )
        self.delivery = WebhookDelivery.objects.create(
            dataspace=self.nexb_dataspace,
            webhook_subscription=self.webhook,
            target_url=self.webhook.target_url,
            payload={"key": "value"},
        )

    def test_webhook_delivery_str(self):
        self.assertIn(f"uuid={self.delivery.uuid}", str(self.delivery))

    def test_webhook_delivery_delivered_false_when_no_status_code(self):
        self.assertFalse(self.delivery.delivered)

    def test_webhook_delivery_delivered_true_when_status_code_set(self):
        self.delivery.response_status_code = 200
        self.assertTrue(self.delivery.delivered)

    def test_webhook_delivery_success_on_2xx(self):
        for status_code in (200, 201, 202):
            self.delivery.response_status_code = status_code
            self.assertTrue(self.delivery.success, f"Expected success for {status_code}")

    def test_webhook_delivery_success_false_on_non_2xx(self):
        for status_code in (400, 404, 500):
            self.delivery.response_status_code = status_code
            self.assertFalse(self.delivery.success, f"Expected failure for {status_code}")


class FireWebhooksTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")

    def test_fire_webhooks_requires_dataspace_or_instance(self):
        with self.assertRaises(AttributeError):
            fire_webhooks("request.added", None)

    @patch("requests.post")
    def test_fire_webhooks_no_matching_event_makes_no_request(self, mock_post):
        fire_webhooks("no.such.event", None, dataspace=self.nexb_dataspace)
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_fire_webhooks_skips_inactive_subscriptions(self, mock_post):
        WebhookSubscription.objects.create(
            dataspace=self.nexb_dataspace,
            target_url="http://1.2.3.4/",
            event="request.added",
            is_active=False,
        )
        fire_webhooks("request.added", None, dataspace=self.nexb_dataspace)
        mock_post.assert_not_called()
