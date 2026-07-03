#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase
from django.test.utils import override_settings

from dje.models import Dataspace
from dje.tests import create_superuser
from notification.models import WebhookSubscription


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

    def test_webhook_subscription_get_extra_headers(self):
        self.webhook.extra_headers = {"Header": "{{ENV_VALUE}}"}
        self.webhook.save()

        expected = {"Header": "{{ENV_VALUE}}"}
        self.assertEqual(expected, self.webhook.get_extra_headers())

        expected = {"Header": "some_value"}
        with override_settings(HOOK_ENV={"ENV_VALUE": "some_value"}):
            self.assertEqual(expected, self.webhook.get_extra_headers())
