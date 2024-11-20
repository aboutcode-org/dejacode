#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.test import TestCase

from dje.models import Dataspace
from vulnerabilities.filters import VulnerabilityFilterSet
from vulnerabilities.tests import make_vulnerability


class VulnerabilityFilterSetTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Reference")
        self.vulnerability1 = make_vulnerability(self.dataspace, risk_score=10.0)
        self.vulnerability2 = make_vulnerability(
            self.dataspace, risk_score=5.5, aliases=["ALIAS-V2"]
        )
        self.vulnerability3 = make_vulnerability(self.dataspace, risk_score=2.0)
        self.vulnerability4 = make_vulnerability(self.dataspace, risk_score=None)

    def test_vulnerability_filterset_search(self):
        data = {"q": self.vulnerability1.vulnerability_id}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.vulnerability1])

        data = {"q": "ALIAS-V2"}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.vulnerability2])

    def test_vulnerability_filterset_sort_nulls_last_ordering(self):
        data = {"sort": "risk_score"}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        expected = [
            self.vulnerability3,
            self.vulnerability2,
            self.vulnerability1,
            self.vulnerability4,  # The risk_score=None are always last
        ]
        self.assertQuerySetEqual(filterset.qs, expected)

        data = {"sort": "-risk_score"}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        expected = [
            self.vulnerability1,
            self.vulnerability2,
            self.vulnerability3,
            self.vulnerability4,  # The risk_score=None are always last
        ]
        self.assertQuerySetEqual(filterset.qs, expected)

    def test_vulnerability_filterset_risk_score(self):
        data = {"risk_score": "critical"}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.vulnerability1])
        data = {"risk_score": "high"}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [])
        data = {"risk_score": "medium"}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.vulnerability2])
        data = {"risk_score": "low"}
        filterset = VulnerabilityFilterSet(dataspace=self.dataspace, data=data)
        self.assertQuerySetEqual(filterset.qs, [self.vulnerability3])
