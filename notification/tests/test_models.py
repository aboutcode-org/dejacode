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
from notification.models import Webhook


class NotificationModelsTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.nexb_user = create_superuser("nexb_user", self.nexb_dataspace)

        self.webhook1 = Webhook.objects.create(
            dataspace=self.nexb_dataspace,
            target="http://1.2.3.4/",
            user=self.nexb_user,
            event="request.added",
        )

    def test_notification_webhook_model_str(self):
        self.assertEqual("request.added => http://1.2.3.4/", str(self.webhook1))

    def test_notification_webhook_model_dict(self):
        expected = {
            "uuid": str(self.webhook1.uuid),
            "event": self.webhook1.event,
            "target": self.webhook1.target,
        }
        self.assertEqual(expected, self.webhook1.dict())

    def test_notification_webhook_model_get_extra_headers(self):
        self.webhook1.extra_headers = {"Header": "{{ENV_VALUE}}"}
        self.webhook1.save()

        expected = {"Header": "{{ENV_VALUE}}"}
        self.assertEqual(expected, self.webhook1.get_extra_headers())

        expected = {"Header": "some_value"}
        with override_settings(HOOK_ENV={"ENV_VALUE": "some_value"}):
            self.assertEqual(expected, self.webhook1.get_extra_headers())
