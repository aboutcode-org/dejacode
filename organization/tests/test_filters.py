#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import datetime
from unittest.mock import Mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from dje.filters import CreatedByListFilter
from dje.filters import DataspaceFilter
from dje.filters import HistoryCreatedActionTimeListFilter
from dje.filters import HistoryModifiedActionTimeListFilter
from dje.models import Dataspace
from dje.models import History
from organization.models import Owner

# WARNING: Do not import from local DJE apps except 'dje' and 'organization'


class HistoryActionTimeListFilterTestCaseMixin:
    class_under_test = None

    def add_history_entry(self, owner, action_flag, days_back):
        history_entry = History.objects.log_action(self.nexb_user, owner, action_flag)
        (
            History.objects.filter(pk=history_entry.pk).update(
                action_time=self.fake_now - datetime.timedelta(days=days_back)
            )
        )

    def setUp(self):
        # filter setup
        request = Mock()
        model_admin = Mock()
        self.filter = self.class_under_test(request, self.get_lookup_params(), Owner, model_admin)

        # test data
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )

        self.owner1 = Owner.objects.create(
            name="org1",
            dataspace=self.nexb_dataspace,
        )
        self.owner2 = Owner.objects.create(
            name="org2",
            dataspace=self.nexb_dataspace,
        )

        # History.action_time is automatically set to the current
        # time *anytime* the model is saved, so to set a custom value for
        # action_time we use QuerySet.update()
        fake_now = datetime.datetime(year=2012, month=8, day=1)
        self.fake_now = fake_now.astimezone(datetime.timezone.utc)

        # create LogEntry objects for the owners

        # owner1 was added 20 days ago
        self.add_history_entry(self.owner1, History.ADDITION, days_back=20)
        self.add_history_entry(self.owner1, History.CHANGE, days_back=7)

        # owner2 was added 100 days ago
        self.add_history_entry(self.owner2, History.ADDITION, days_back=100)
        self.add_history_entry(self.owner2, History.CHANGE, days_back=30)

    def get_lookup_params(self):
        raise NotImplementedError

    def test_lookups(self):
        request = Mock()
        model_admin = Mock()
        lookups = self.filter.lookups(request, model_admin)
        expected_lookups = (
            ("any_date", _("Any Date")),
            ("today", _("Today")),
            ("past_7_days", _("Past 7 days")),
            ("past_30_days", _("Past 30 days")),
            ("this_year", _("This year")),
        )
        self.assertEqual(expected_lookups, lookups)

    def test_get_history_objects_returns_None_for_any_date(self):
        # Setup
        request = Mock()
        model_admin = Mock()
        filter = self.class_under_test(request, {"created_date": "any_date"}, Owner, model_admin)

        self.assertEqual(None, filter.get_history_objects())

    def test_queryset_returns_None_for_any_date(self):
        # Setup
        request = Mock()
        model_admin = Mock()
        filter = self.class_under_test(request, {"created_date": "any_date"}, Owner, model_admin)
        qs = Owner.objects.all()

        self.assertEqual(None, filter.queryset(request, qs))


class HistoryCreatedActionTimeListFilterTestCase(
    HistoryActionTimeListFilterTestCaseMixin, TestCase
):
    class_under_test = HistoryCreatedActionTimeListFilter

    def get_lookup_params(self):
        return {"created_date": ["past_7_days"]}

    def test_get_history_objects(self):
        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            self.assertEqual(0, self.filter.get_history_objects().count())

    def test_get_history_objects_with_invalid_input(self):
        # filter setup
        request = Mock()
        model_admin = Mock()
        filter = self.class_under_test(
            request, {"created_date": "invalid_value"}, Owner, model_admin
        )

        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            self.assertEqual(None, filter.get_history_objects())

    def test_queryset(self):
        request = Mock()
        qs = Owner.objects.all()

        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            qs2 = self.filter.queryset(request, qs)
            self.assertEqual(0, qs2.count())

    def test_queryset_with_invalid_input(self):
        # filter setup
        request = Mock()
        model_admin = Mock()
        filter = self.class_under_test(
            request, {"created_date": "invalid_value"}, Owner, model_admin
        )
        qs = Owner.objects.all()

        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            self.assertEqual(None, filter.queryset(request, qs))

    def test_choices(self):
        # setup
        cl = Mock()

        def get_query_string(new_params=None, remove=None):
            return urlencode(new_params)

        cl.get_query_string = get_query_string

        # test
        expected_choices = [
            {"display": "Any Date", "query_string": "created_date=any_date", "selected": False},
            {"display": "Today", "query_string": "created_date=today", "selected": False},
            {
                "display": "Past 7 days",
                "query_string": "created_date=past_7_days",
                "selected": True,
            },
            {
                "display": "Past 30 days",
                "query_string": "created_date=past_30_days",
                "selected": False,
            },
            {"display": "This year", "query_string": "created_date=this_year", "selected": False},
        ]
        self.assertEqual(expected_choices, list(self.filter.choices(cl)))


class HistoryModifiedActionTimeListFilterTestCase(
    HistoryActionTimeListFilterTestCaseMixin, TestCase
):
    class_under_test = HistoryModifiedActionTimeListFilter

    def get_lookup_params(self):
        return {"modified_date": ["past_7_days"]}

    def test_get_history_objects(self):
        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            self.assertEqual(1, self.filter.get_history_objects().count())

    def test_get_history_objects_with_invalid_input(self):
        # filter setup
        request = Mock()
        model_admin = Mock()
        filter = self.class_under_test(
            request, {"modified_date": "invalid_value"}, Owner, model_admin
        )

        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            self.assertEqual(None, filter.get_history_objects())

    def test_queryset(self):
        request = Mock()
        qs = Owner.objects.all()

        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            qs2 = self.filter.queryset(request, qs)
            self.assertEqual(1, qs2.count())

    def test_queryset_with_invalid_input(self):
        # filter setup
        request = Mock()
        model_admin = Mock()
        filter = self.class_under_test(
            request, {"modified_date": "invalid_value"}, Owner, model_admin
        )
        qs = Owner.objects.all()

        with patch("dje.filters.timezone.now") as mock_timezone:
            # patch timezone.now() so that it Return a consistent date
            mock_timezone.return_value = self.fake_now
            self.assertEqual(None, filter.queryset(request, qs))

    def test_choices(self):
        # setup
        cl = Mock()

        def get_query_string(new_params=None, remove=None):
            return urlencode(new_params)

        cl.get_query_string = get_query_string

        # test
        expected_choices = [
            {"display": "Any Date", "query_string": "modified_date=any_date", "selected": False},
            {"display": "Today", "query_string": "modified_date=today", "selected": False},
            {
                "display": "Past 7 days",
                "query_string": "modified_date=past_7_days",
                "selected": True,
            },
            {
                "display": "Past 30 days",
                "query_string": "modified_date=past_30_days",
                "selected": False,
            },
            {"display": "This year", "query_string": "modified_date=this_year", "selected": False},
        ]
        self.assertEqual(expected_choices, list(self.filter.choices(cl)))


class CreatedByListFilterTestCase(TestCase):
    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.create(name="nexB")
        self.other_dataspace = Dataspace.objects.create(name="Other Dataspace")

        self.nexb_user = get_user_model().objects.create_superuser(
            "nexb_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.nexb_user.first_name = "George"
        self.nexb_user.last_name = "Bush"
        self.nexb_user.save()

        self.other_user = get_user_model().objects.create_superuser(
            "other_user", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.other_user.first_name = "Bill"
        self.other_user.last_name = "Clinton"
        self.other_user.save()

        self.user3 = get_user_model().objects.create_superuser(
            "user3", "test@test.com", "t3st", self.other_dataspace
        )
        self.user3.first_name = "Barack"
        self.user3.last_name = "Obama"
        self.user3.save()

        self.user4 = get_user_model().objects.create_superuser(
            "user4", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.user4.first_name = "George"
        self.user4.last_name = "Washington"
        self.user4.save()

        self.user5 = get_user_model().objects.create_superuser(
            "user5", "test@test.com", "t3st", self.nexb_dataspace
        )
        self.user5.first_name = "Thomas"
        self.user5.last_name = "Jefferson"
        self.user5.save()

        self.owner1 = Owner.objects.create(name="org1", dataspace=self.nexb_dataspace)
        self.owner2 = Owner.objects.create(name="org2", dataspace=self.nexb_dataspace)
        self.owner3 = Owner.objects.create(name="org3", dataspace=self.other_dataspace)
        self.owner4 = Owner.objects.create(name="org4", dataspace=self.nexb_dataspace)
        self.owner5 = Owner.objects.create(name="org5", dataspace=self.other_dataspace)

        # nexb_user created owner1
        History.objects.log_action(self.nexb_user, self.owner1, History.ADDITION)

        # nexb_user created owner4
        History.objects.log_action(self.nexb_user, self.owner4, History.ADDITION)

        # other_user created owner2
        History.objects.log_action(self.other_user, self.owner2, History.ADDITION)

        # user3 created owner3
        History.objects.log_action(self.user3, self.owner3, History.ADDITION)

        # user5 created owner5
        History.objects.log_action(self.user5, self.owner5, History.ADDITION)

    def test_lookups(self):
        # Setup
        request = Mock()
        request.GET = {}
        request.user = self.nexb_user
        model_admin = Mock()
        filter = CreatedByListFilter(request, {}, Owner, model_admin)

        expected = [(self.nexb_user.pk, "George Bush"), (self.other_user.pk, "Bill Clinton")]
        self.assertEqual(expected, filter.lookup_choices)

    def test_lookups_does_not_return_users_who_have_not_created_an_object(self):
        # Setup
        request = Mock()
        request.GET = {}
        request.user = self.nexb_user
        model_admin = Mock()
        filter = CreatedByListFilter(request, {}, Owner, model_admin)

        self.assertEqual(0, History.objects.filter(user=self.user4).count())
        self.assertTrue((self.user4.pk, "George Washington") not in filter.lookup_choices)

    def test_lookups_does_not_return_duplicate_users(self):
        # Setup
        request = Mock()
        request.GET = {}
        request.user = self.nexb_user
        model_admin = Mock()
        filter = CreatedByListFilter(request, {}, Owner, model_admin)

        # nexb_user created 2 Owners
        self.assertEqual(
            2,
            History.objects.filter(
                user=self.nexb_user, content_type=ContentType.objects.get_for_model(Owner)
            ).count(),
        )
        self.assertEqual(
            1, len([c for c in filter.lookup_choices if c == (self.nexb_user.pk, "George Bush")])
        )

    def test_lookups_respects_dataspace_filter(self):
        request = Mock()
        params = {DataspaceFilter.parameter_name: self.other_dataspace.pk}
        request.GET = params
        request.user = self.nexb_user
        model_admin = Mock()
        filter = CreatedByListFilter(request, params, Owner, model_admin)

        expected = [(self.user3.pk, "Barack Obama")]
        self.assertEqual(expected, filter.lookup_choices)

    def test_lookups_orders_by_last_name(self):
        request = Mock()
        request.GET = {}
        request.user = self.nexb_user
        model_admin = Mock()
        filter = CreatedByListFilter(request, {}, Owner, model_admin)

        self.assertEqual(0, filter.lookup_choices.index((self.nexb_user.pk, "George Bush")))
        self.assertEqual(1, filter.lookup_choices.index((self.other_user.pk, "Bill Clinton")))

    def test_lookups_checks_objects_were_created_in_the_same_dataspace_as_the_one_being_viewed(
        self,
    ):
        # Setup
        request = Mock()
        request.GET = {}
        request.user = self.user5
        model_admin = Mock()
        filter = CreatedByListFilter(request, {}, Owner, model_admin)

        # The Dataspace to which user5 belongs is different from the one in which he created owner5
        self.assertEqual(self.user5.dataspace, self.nexb_dataspace)
        self.assertEqual(self.other_dataspace, self.owner5.dataspace)

        # The Dataspace being viewed is nexb_organization.
        # The Dataspace in which owner5 was created is other_dataspace.
        self.assertTrue((self.user5.pk, "Thomas Jefferson") not in filter.lookup_choices)

    def test_queryset_for_nexb_user(self):
        # Setup
        request = Mock()
        request.GET = {}
        request.user = self.nexb_user
        model_admin = Mock()
        filter = CreatedByListFilter(
            request, {"created_by": [self.nexb_user.pk]}, Owner, model_admin
        )
        qs = Owner.objects.scope(self.nexb_dataspace)

        expected = [self.owner1, self.owner4]
        self.assertEqual(expected, list(filter.queryset(request, qs)))

    def test_queryset_for_other_user(self):
        # Setup
        request = Mock()
        request.GET = {}
        request.user = self.other_user
        model_admin = Mock()
        filter = CreatedByListFilter(
            request, {"created_by": [self.other_user.pk]}, Owner, model_admin
        )
        qs = Owner.objects.scope(self.nexb_dataspace)

        expected = [self.owner2]
        self.assertEqual(expected, list(filter.queryset(request, qs)))
