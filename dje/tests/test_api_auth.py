#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.db.utils import IntegrityError
from django.test import TestCase

from rest_framework.exceptions import AuthenticationFailed

from aboutcode.api_auth import APITokenAuthentication
from dje.models import APIToken
from dje.models import Dataspace
from dje.tests import create_user


class AboutCodeAPIAuthTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.base_user = create_user("base_user", self.dataspace)

    def test_api_auth_api_token_model_generate_key(self):
        self.assertEqual(64, len(APIToken.generate_key()))

    def test_api_auth_api_token_model_create_token(self):
        self.assertEqual(0, APIToken.objects.count())

        plain_key = APIToken.create_token(user=self.base_user)
        self.assertEqual(1, APIToken.objects.count())
        self.assertEqual(64, len(plain_key))
        api_token = self.base_user.api_token
        self.assertEqual(59, len(api_token.key_hash))
        self.assertEqual(8, len(api_token.prefix))
        self.assertEqual(api_token.prefix, plain_key[: APIToken.PREFIX_LENGTH])

        with self.assertRaises(IntegrityError):
            APIToken.create_token(user=self.base_user)

    def test_api_auth_api_token_model_verify(self):
        self.assertIsNone(APIToken.verify(plain_key=None))
        self.assertIsNone(APIToken.verify(plain_key=""))
        self.assertIsNone(APIToken.verify(plain_key="a_key"))

        plain_key = APIToken.create_token(user=self.base_user)
        token = APIToken.verify(plain_key=plain_key)
        self.assertIsInstance(token, APIToken)
        self.assertEqual(self.base_user, token.user)

    def test_api_auth_api_token_model_regenerate(self):
        self.assertEqual(0, APIToken.objects.count())
        APIToken.regenerate(user=self.base_user)
        self.assertEqual(1, APIToken.objects.count())
        APIToken.regenerate(user=self.base_user)
        self.assertEqual(1, APIToken.objects.count())

    def test_api_auth_api_token_authentication_get_model(self):
        self.assertEqual(APIToken, APITokenAuthentication().get_model())

    def test_api_auth_api_token_authentication_authenticate_credentials(self):
        api_token_auth = APITokenAuthentication()

        with self.assertRaisesMessage(AuthenticationFailed, "Invalid token."):
            api_token_auth.authenticate_credentials(plain_key=None)

        plain_key = APIToken.create_token(user=self.base_user)
        expected = (self.base_user, self.base_user.api_token)
        self.assertEqual(expected, api_token_auth.authenticate_credentials(plain_key=plain_key))

        self.base_user.is_active = False
        self.base_user.save()
        with self.assertRaisesMessage(AuthenticationFailed, "User inactive or deleted."):
            api_token_auth.authenticate_credentials(plain_key=plain_key)
