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

import clamd

from dje.fields import SmartFileField


@override_settings(ADMINS=["admin@dejacode.com"])
class SmartFileFieldTestCase(TestCase):
    @staticmethod
    def raise_broken_pipe(self, file):
        raise BrokenPipeError

    @staticmethod
    def raise_clamd_error(self, file):
        raise clamd.ClamdError

    def test_restricted_file_field_scan_file_for_virus(self):
        file = BytesIO(clamd.EICAR)
        clamd_socket = clamd.ClamdNetworkSocket
        scan_file_for_virus = SmartFileField.scan_file_for_virus

        with patch.object(clamd_socket, "instream", self.raise_broken_pipe):
            with self.assertRaises(ValidationError) as context:
                scan_file_for_virus(file)
            expected = "File size is too large."
            self.assertEqual(expected, context.exception.message)

        with patch.object(clamd_socket, "instream", self.raise_clamd_error):
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

        scan_response = {"stream": ("FOUND", "Eicar-Test-Signature")}
        with patch.object(clamd_socket, "instream", lambda *args: scan_response):
            with self.assertRaises(ValidationError) as context:
                scan_file_for_virus(file)
            expected = "This file is infected. Upload aborted."
            self.assertEqual(expected, context.exception.message)

        scan_response = {"stream": ("ERROR", "Error running scan")}
        with patch.object(clamd_socket, "instream", lambda *args: scan_response):
            with self.assertRaises(ValidationError) as context:
                scan_file_for_virus(file)
            expected = "File upload error."
            self.assertEqual(expected, context.exception.message)
