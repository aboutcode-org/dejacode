#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from os.path import dirname
from os.path import join

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from component_catalog.filters import ComponentFilterSet
from component_catalog.filters import PackageFilterSet
from component_catalog.models import Component
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentType
from component_catalog.tests import make_component
from component_catalog.tests import make_package
from dje.models import Dataspace
from dje.tests import create_superuser
from dje.tests import create_user
from license_library.models import License
from organization.models import Owner
from policy.models import UsagePolicy


class ComponentFilterSetTest(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Reference")
        self.other_dataspace = Dataspace.objects.create(name="Other")
        self.nexb_user = create_superuser("nexb_user", self.dataspace)
        self.basic_user = create_user("basic_user", self.dataspace)

        self.owner = Owner.objects.create(
            name="Owner", dataspace=self.dataspace)
        self.other_owner = Owner.objects.create(
            name="OtherOwner", dataspace=self.other_dataspace)

        self.license_ct = ContentType.objects.get_for_model(License)
        self.component_ct = ContentType.objects.get_for_model(Component)

        self.license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=self.license_ct,
            dataspace=self.dataspace,
        )
        self.component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.dataspace,
        )
        self.other_component_policy = UsagePolicy.objects.create(
            label="OtherComponentPolicy",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.other_dataspace,
        )

        self.component_type = ComponentType.objects.create(
            label="type1", dataspace=self.dataspace)
        self.other_type = ComponentType.objects.create(
            label="other_type", dataspace=self.other_dataspace
        )

        self.license1 = License.objects.create(
            key="license1",
            name="License1",
            short_name="L1",
            dataspace=self.dataspace,
            owner=self.owner,
        )
        self.license2 = License.objects.create(
            key="license2",
            name="License2",
            short_name="L2",
            dataspace=self.dataspace,
            owner=self.owner,
        )
        self.other_license = License.objects.create(
            key="license1",
            name="License1",
            short_name="L1",
            dataspace=self.other_dataspace,
            owner=self.other_owner,
        )

        self.keyword1 = ComponentKeyword.objects.create(
            label="Keyword", dataspace=self.dataspace)
        self.other_keyword = ComponentKeyword.objects.create(
            label="OtherKeyword", dataspace=self.other_dataspace
        )

    def test_component_filterset_no_dataspace(self):
        with self.assertRaises(AttributeError):
            ComponentFilterSet()
        self.assertTrue(ComponentFilterSet(dataspace=self.dataspace))

    def test_component_filterset_dataspace_scoping(self):
        # Removing the `related_only` as we need to test Dataspace scoping only
        class ComponentFilterSetScoping(ComponentFilterSet):
            related_only = []

        component_filterset = ComponentFilterSetScoping(
            dataspace=self.dataspace)

        qs = component_filterset.filters["usage_policy"].queryset
        self.assertTrue(self.component_policy in qs)
        self.assertFalse(self.other_component_policy in qs)
        self.assertFalse(self.license_policy in qs)

        qs = component_filterset.filters["type"].queryset
        self.assertTrue(self.component_type in qs)
        self.assertFalse(self.other_type in qs)

        qs = component_filterset.filters["licenses"].queryset
        self.assertTrue(self.license1 in qs)
        self.assertFalse(self.other_license in qs)

        qs = component_filterset.filters["keywords"].queryset
        self.assertTrue(self.keyword1 in qs)
        self.assertFalse(self.other_keyword in qs)

    def test_component_filterset_primary_language_filter(self):
        filterset = ComponentFilterSet(dataspace=self.dataspace)
        self.assertEqual(
            [], list(filterset.filters["primary_language"].field.choices))

        c1 = make_component(self.dataspace, name="c1",
                            primary_language="Python")
        c2 = make_component(self.dataspace, name="c2", primary_language="Java")

        filterset = ComponentFilterSet(dataspace=self.dataspace)
        self.assertEqual([c1, c2], list(filterset.qs))
        self.assertEqual(
            [("Java", "Java"), ("Python", "Python")],
            list(filterset.filters["primary_language"].field.choices),
        )

        filterset = ComponentFilterSet(
            dataspace=self.dataspace, data={"q": c1.name})
        self.assertEqual([c1], list(filterset.qs))
        self.assertEqual(
            [("Python", "Python")], list(
                filterset.filters["primary_language"].field.choices)
        )

    def test_component_filterset_related_only_values_filter(self):
        self.assertEqual(
            ["licenses", "primary_language",
                "usage_policy"], ComponentFilterSet.related_only
        )

        c1 = make_component(
            self.dataspace,
            name="c1",
            license_expression=self.license1.key,
            primary_language="Python",
        )
        c2 = make_component(self.dataspace, name="c2", primary_language="Java")

        filterset = ComponentFilterSet(dataspace=self.dataspace)
        self.assertEqual([c1, c2], list(filterset.qs))
        self.assertEqual([self.license1], list(
            filterset.filters["licenses"].queryset))
        self.assertEqual(
            [("Java", "Java"), ("Python", "Python")],
            list(filterset.filters["primary_language"].field.choices),
        )

        filterset = ComponentFilterSet(
            dataspace=self.dataspace, data={"q": c1.name})
        self.assertEqual([c1], list(filterset.qs))
        self.assertEqual([self.license1], list(
            filterset.filters["licenses"].queryset))
        self.assertEqual(
            [("Python", "Python")], list(
                filterset.filters["primary_language"].field.choices)
        )

        filterset = ComponentFilterSet(
            dataspace=self.dataspace, data={"q": c2.name})
        self.assertEqual([c2], list(filterset.qs))
        self.assertEqual([], list(filterset.filters["licenses"].queryset))
        self.assertEqual(
            [("Java", "Java")], list(
                filterset.filters["primary_language"].field.choices)
        )

        c2.license_expression = self.license2.key
        c2.save()
        filterset = ComponentFilterSet(dataspace=self.dataspace)
        self.assertEqual([c1, c2], list(filterset.qs))
        self.assertEqual(
            [self.license1, self.license2], list(
                filterset.filters["licenses"].queryset)
        )
        self.assertEqual(
            [("Java", "Java"), ("Python", "Python")],
            list(filterset.filters["primary_language"].field.choices),
        )

        # The current filter value does not apply to itself
        filterset = ComponentFilterSet(
            dataspace=self.dataspace, data={"licenses": [self.license1.key]}
        )
        self.assertEqual([c1], list(filterset.qs))
        self.assertEqual(
            [self.license1, self.license2], list(
                filterset.filters["licenses"].queryset)
        )
        self.assertEqual(
            [("Python", "Python")], list(
                filterset.filters["primary_language"].field.choices)
        )


class ComponentFilterSearchTestCase(TestCase):
    testfiles_location = join(dirname(__file__), "testfiles")

    # Extract Component data as json for a given list of PKs:
    # dejacode dumpdata component_catalog.component --indent 2 --natural-foreign
    #   --natural-primary --pks <comma-separated list of component pks>
    fixtures = [join(testfiles_location, "search", "component_dataset.json")]

    def test_component_filterset_search_filter(self):
        dataspace = Dataspace.objects.get(name="Reference")
        data = {"q": ""}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        expected = [
            "jblogbackup 1.0",
            "jblogbackup 1.1",
            "logback 0.9.9",
            "logback 1.0.0",
            "logback 1.0.1",
            "logback classic 1.0.0",
            "logback eclipse 1.0.0",
            "nagios-logback-appender 1.0",
            "zzz",
        ]
        self.assertEqual(expected, [str(component)
                         for component in component_filterset.qs])

        data = {"q": "logback"}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        expected = [
            "logback 0.9.9",
            "logback 1.0.0",
            "logback 1.0.1",
            "logback classic 1.0.0",
            "logback eclipse 1.0.0",
            "nagios-logback-appender 1.0",
            "jblogbackup 1.0",
            "jblogbackup 1.1",
        ]
        self.assertEqual(expected, [str(component)
                         for component in component_filterset.qs])

    def test_component_filterset_sort_keeps_default_ordering_from_model(self):
        dataspace = Dataspace.objects.get(name="Reference")
        data = {}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        self.assertEqual((), component_filterset.qs.query.order_by)

        data = {"sort": ""}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        self.assertEqual((), component_filterset.qs.query.order_by)

        data = {"sort": "invalid"}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        self.assertEqual((), component_filterset.qs.query.order_by)

        data = {"sort": "name"}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        self.assertEqual(("name", "version"),
                         component_filterset.qs.query.order_by)

        data = {"sort": "version"}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        self.assertEqual(("version", "name"),
                         component_filterset.qs.query.order_by)

        data = {"sort": "primary_language"}
        component_filterset = ComponentFilterSet(
            dataspace=dataspace, data=data)
        self.assertEqual(
            ("primary_language", "name",
             "version"), component_filterset.qs.query.order_by
        )


class PackageFilterSearchTestCase(TestCase):
    def sorted_results(self, qs):
        return sorted([str(package) for package in qs])

    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Reference")

        filename = {
            "filename": "setup.exe",
        }
        make_package(self.dataspace, **filename)

        simple_purl = {
            "type": "deb",
            "name": "curl",
        }
        make_package(self.dataspace, **simple_purl)

        simple_purl2 = {
            **simple_purl,
            "type": "git",
        }
        make_package(self.dataspace, **simple_purl2)

        complete_purl = {
            "type": "deb",
            "namespace": "debian",
            "name": "curl",
            "version": "7.50.3-1",
            "qualifiers": "arch=i386",
            "subpath": "googleapis/api/annotations",
        }
        make_package(self.dataspace, **complete_purl)

    def test_package_filterset_search_filter(self):
        data = {"q": ""}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        expected = [
            "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations",
            "pkg:git/curl",
            "pkg:deb/curl",
            "setup.exe",
        ]
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))

        data = {"q": "deb/curl"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        expected = [
            "pkg:deb/curl",
            "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations",
        ]
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))
        data = {"q": "pkg:deb/curl"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))

        data = {"q": "deb/debian/curl@7.50.3-1"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        expected = [
            "pkg:deb/debian/curl@7.50.3-1?arch=i386#googleapis/api/annotations",
        ]
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))
        data = {"q": "pkg:deb/debian/curl@7.50.3-1"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))

        data = {"q": "git/curl"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        expected = [
            "pkg:git/curl",
        ]
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))
        data = {"q": "pkg:git/curl"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))

        data = {"q": "setup.exe"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        expected = [
            "setup.exe",
        ]
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))

        data = {"q": "pkg:setup.exe"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        self.assertEqual([], self.sorted_results(filterset.qs))

    def test_package_filterset_search_match_order_on_purl_fields(self):
        make_package(self.dataspace, package_url="pkg:pypi/django@5.0")
        make_package(self.dataspace, package_url="pkg:pypi/django@4.0",
                     filename="Django-4.0.zip")

        data = {"q": "django"}
        filterset = PackageFilterSet(dataspace=self.dataspace, data=data)
        expected = ["pkg:pypi/django@4.0", "pkg:pypi/django@5.0"]
        self.assertEqual(sorted(expected), self.sorted_results(filterset.qs))
