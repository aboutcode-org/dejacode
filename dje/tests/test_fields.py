#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from io import BytesIO
from unittest.mock import patch

from django.core import mail
from django.forms import ValidationError
from django.test import TestCase
from django.test import override_settings

from dejacode_toolkit import clamav
from dje.fields import SmartFileField


@override_settings(ADMINS=["admin@dejacode.com"])
class SmartFileFieldTestCase(TestCase):
    @patch("dejacode_toolkit.clamav.scan_stream")
    def test_restricted_file_field_scan_file_for_virus(self, mock_scan_stream):
        file = BytesIO(b"content")
        scan_file_for_virus = SmartFileField.scan_file_for_virus

        mock_scan_stream.side_effect = clamav.StreamTooLargeError
        with self.assertRaises(ValidationError) as context:
            scan_file_for_virus(file)
        expected = "File size is too large."
        self.assertEqual(expected, context.exception.message)
        self.assertEqual(0, len(mail.outbox))

        mock_scan_stream.side_effect = clamav.ClamdError
        with self.assertRaises(ValidationError) as context:
            scan_file_for_virus(file)
        expected = "File upload disabled at the moment. Please contact your administrator."
        self.assertEqual(expected, context.exception.message)

        self.assertEqual(len(mail.outbox), 1)
        sent_mail = mail.outbox[0]
        self.assertEqual("[DejaCode] Clamd Error", sent_mail.subject)
        expected_body = "Error with the ClamAV setup. Make sure the service is properly running."
        self.assertEqual(expected_body, sent_mail.body)
        self.assertEqual(["admin@dejacode.com"], sent_mail.to)

        mock_scan_stream.side_effect = None
        mock_scan_stream.return_value = ("FOUND", "Eicar-Test-Signature")
        with self.assertRaises(ValidationError) as context:
            scan_file_for_virus(file)
        expected = "This file is infected. Upload aborted."
        self.assertEqual(expected, context.exception.message)

        mock_scan_stream.return_value = ("ERROR", "Error running scan")
        with self.assertRaises(ValidationError) as context:
            scan_file_for_virus(file)
        expected = "File upload error."
        self.assertEqual(expected, context.exception.message)

        mock_scan_stream.return_value = ("OK", None)
        scan_file_for_virus(file)

    @patch("dejacode_toolkit.clamav.scan_stream")
    def test_restricted_file_field_scan_file_for_virus_clamd_address(self, mock_scan_stream):
        mock_scan_stream.return_value = ("OK", None)
        file = BytesIO(b"content")

        with override_settings(CLAMD_USE_TCP=True, CLAMD_TCP_ADDR="clamav"):
            SmartFileField.scan_file_for_virus(file)
        mock_scan_stream.assert_called_with(file, ("clamav", 3310))

        with override_settings(CLAMD_USE_TCP=False):
            SmartFileField.scan_file_for_virus(file)
        mock_scan_stream.assert_called_with(file, "/var/run/clamav/clamd.ctl")
