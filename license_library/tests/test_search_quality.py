#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import os
import re
from unittest.case import expectedFailure
from unittest.mock import Mock

from django.test import TestCase

from dje.models import Dataspace
from license_library.views import LicenseListView


def regen_fixtures():
    """
    To re-create the fixture used in the LicenseSearchQualityTestCase,
    go to enterprise.dejacode.com and run this function in manage.py shell::
    $ ./manage.py shell
    >>> from license_library.tests.test_search_quality import regen_fixtures
    >>> regen_fixtures()
    Then commit the updated zipped json.
    """
    from django.core.serializers.json import Serializer

    from dje.management import LICENSE_LIBRARY_MODELS
    from dje.models import Dataspace
    from license_library.models import LicenseAnnotation
    from license_library.models import LicenseAssignedTag
    from organization.models import Owner

    LICENSE_LIBRARY_MODELS = LICENSE_LIBRARY_MODELS[:]
    # Exclude some models that have too many rows and are not needed
    LICENSE_LIBRARY_MODELS.remove(LicenseAnnotation)
    LICENSE_LIBRARY_MODELS.remove(LicenseAssignedTag)

    def get_models():
        models = [Dataspace] + Owner + LICENSE_LIBRARY_MODELS
        return models

    class NullPKSerializer(Serializer):
        """
        Extension of the django.core.serializers.json.Serializer to ensure objects
        PK are set to 'null' in the dump.
        """

        def end_object(self, obj):
            obj.pk = None
            super().end_object(obj)

    def get_objects():
        for model in get_models():
            qs = model._default_manager.order_by(model._meta.pk.name)
            if model == Dataspace:
                qs = qs.filter(name="nexB")
            else:
                qs = qs.scope_by_name("nexB")
            for obj in qs.iterator():
                yield obj

    serializer = NullPKSerializer()
    data = serializer.serialize(
        get_objects(), indent=0, use_natural_foreign_keys=True, use_natural_primary_keys=True
    )
    fout = os.path.join(os.path.dirname(__file__), "fixtures", "test_license_library_fixture.json")
    with open(fout, "w") as f:
        f.write(data)
    import zipfile

    foutz = zipfile.ZipFile(fout + ".zip", "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True)
    foutz.write(fout, "test_license_library_fixture.json")
    foutz.close()
    os.remove(fout)


class SearchQualityTestCase(TestCase):
    maxDiff = None

    def get_initial_sqs(self):
        raise NotImplementedError

    def get_default_field(self):
        raise NotImplementedError

    def get_results(self, query, sqs):
        raise NotImplementedError

    def do_search(self, query, expected_results, ordered=True, exact=False, field=None):
        """
        Run a search with the 'query' string, expecting the 'expected_results'
        list of 'field' values to be found in the search results.
        The 'field' defaults to return value of ``get_default_field()``.

        If 'ordered' is True, results order matters and results should be in
        the same order as the 'expected_results'.

        If 'exact' is True, the whole results set must be the same as the
        'expected_results'.

        If an expected item is a '*' , then it can be anything.
        This is helpful to test thing such as:
         - gps-1.0 is in the top 5 results at any position:
         use this: expected_results=['gps-1.0','*','*','*','*'],
            field='key', ordered=False, exact=False
         - artistic-1.0 is top result and we have exactly 3 results returned:
         use this: expected_results=['artistic-1.0','*','*'],
            field='key', ordered=False, exact=False
        """
        if field is None:
            field = self.get_default_field()

        sqs = self.get_initial_sqs()
        results = self.get_results(query, sqs)

        # this address the exact case
        test_results = results if exact else results[: len(expected_results)]
        test_values = [getattr(r, field) for r in test_results]

        expected_results = [str(e) for e in expected_results]

        # A '*' in expected results can be any value
        if ordered:
            for i, er in enumerate(expected_results):
                # for ordered expectations, just replace the results with a *
                if er == "*":
                    test_values[i] = "*"
            self.assertEqual(expected_results, test_values)
        else:
            self.assertEqual(
                len(expected_results),
                len(test_values),
                'Unordered expected items "%r" differ in length with results items :"%r"'
                % (expected_results, test_values),
            )
            msgs = []
            for i, er in enumerate(expected_results):
                if er != "*":
                    if er not in test_values:
                        msgs.append(
                            'Unordered expected item "%s" missing in results: "%r"'
                            % (er, test_values)
                        )
            if msgs:
                self.fail("\n".join(msgs))


class LicenseSearchQualityTestCase(SearchQualityTestCase):
    fixtures = [
        os.path.join(os.path.dirname(__file__), "fixtures", "test_license_library_fixture.json.zip")
    ]

    def setUp(self):
        self.nexb_dataspace = Dataspace.objects.get(name="nexB")

    def get_initial_sqs(self):
        mock_request = Mock()
        mock_request.user.dataspace = self.nexb_dataspace
        view = LicenseListView()
        view.request = mock_request
        return view.get_initial_searchqueryset()

    def get_default_field(self):
        return "key"

    def get_results(self, query, sqs):
        mock_request = Mock()
        mock_request.user.dataspace = self.nexb_dataspace
        view = LicenseListView()
        view.request = mock_request
        form = Mock()
        form.cleaned_data = {"q": query}
        return view.apply_search(sqs, form)


# #######################################################################
# # Build tests from CSV data sets
# #######################################################################
safe_chars = re.compile(r"[\W_]", re.MULTILINE)


def python_safe(s):
    """Return a name safe to use as a python function name"""
    s = s.strip().lower()
    s = [x for x in safe_chars.split(s) if x]
    return "_".join(s)


def search_tst(query, expected_results, ordered, exact, field, rownum, notes):
    """Return a search test function closed on arguments"""

    def search_test_func(self):
        self.do_search(query, expected_results, ordered=ordered, exact=exact, field=field)

    # build a reasonably unique and valid function name
    # based on the up to 50 chars from the query and a row number
    test_func_name = "test_search_%04d_" % rownum + python_safe(
        query[:50] + "_%s" % notes if notes else ""
    )
    # these are needed to ensure we can use the tests name for selection in discovery
    search_test_func.__name__ = str(test_func_name)
    search_test_func.funcname = str(test_func_name)
    return search_test_func


def build_tsts_from_csv(csv_path, test_class):
    """
    Build search test functions for each row in a CSV csv_path
    and attach them to the test_class test Class
    The CSV must have this format:
    The first row contains labels, and is ignored.
    The columns for each row can be:
     - 1: Test Query to search: mandatory, the string to test search
     - 2: Notes: optional, they become part of the test function name and help documenting the test
     - 3: ordered? Should the sequence of expected results match?  Use an x if yes, leave empty
         if not
     - 4: exact? Should the expected results match exactly (same results, same number of results,
         ordered or not?) Use an x if yes, leave empty if not
     - 5: field name: What is the field name used for the expected Results? One of key, name,
          short_name or others available fields. Default to key if empty
     - 6: expected Failure? Is this test expected to fail for now? Use an x if yes, leave
          empty if not
     - 7 and other columns: Expected results: Each column contains a license: use * if this
          can be any license.
    """
    with open(csv_path, "rU") as fin:
        import csv

        reader = csv.reader(fin)
        # skip first header row
        next(reader)
        # the first CSV row is #2, this help searching which row has an error
        rownum = 2
        for i, row in enumerate(reader):
            if len(row) == 0:
                continue
            query = row[0]
            if not query:
                raise RuntimeError(
                    "Missing test query for row: %d of CSV file:%r" % (i + 1, csv_path)
                )
            notes = row[1] if len(row) >= 2 else False
            ordered = row[2] if len(row) >= 3 else False
            exact = row[3] if len(row) >= 4 else False
            field = row[4] if len(row) >= 5 else "key"
            expectToFail = row[5] if len(row) >= 6 else False
            expectation = [r for r in row[6:] if r] if len(row) >= 7 else []

            fun = search_tst(query, expectation, ordered, exact, field, rownum, notes)

            if expectToFail:
                fun = expectedFailure(fun)
            setattr(test_class, fun.__name__, fun)
            rownum += 1


# SKIPPED FOR NOW, takes too much time for no value
# csv_path = os.path.join(os.path.dirname(__file__), 'testfiles', 'search_tests.csv')
# build_tsts_from_csv(csv_path, LicenseSearchQualityTestCase)
