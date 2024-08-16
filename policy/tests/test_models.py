#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from component_catalog.models import Component
from dje.models import Dataspace
from license_library.models import License
from organization.models import Owner
from policy.models import AssociatedPolicy
from policy.models import UsagePolicy


class UsagePolicyModelsTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="Dataspace")
        self.alternate = Dataspace.objects.create(name="Alternate")

        self.license_ct = ContentType.objects.get_for_model(License)
        self.component_ct = ContentType.objects.get_for_model(Component)

        self.license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=self.license_ct,
            dataspace=self.dataspace,
        )

        self.license_policy2 = UsagePolicy.objects.create(
            label="LicensePolicy2",
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

        self.component_policy2 = UsagePolicy.objects.create(
            label="ComponentPolicy2",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.dataspace,
        )

        self.component = Component.objects.create(
            name="c1", dataspace=self.dataspace, usage_policy=self.component_policy
        )

    def test_usage_policy_get_by_natural_key(self):
        policy = UsagePolicy.objects.get_by_natural_key(
            self.dataspace.name, self.component_policy.uuid
        )
        self.assertEqual(policy, self.component_policy)

    def test_usage_policy_natural_key(self):
        expected = (self.dataspace.name, self.component_policy.uuid)
        self.assertEqual(expected, self.component_policy.natural_key())

    def test_get_usage_policy_color_on_related_object(self):
        self.assertEqual("#000000", self.component.get_usage_policy_color())
        self.component_policy.color_code = "FFFFFF"
        self.assertEqual("#FFFFFF", self.component.get_usage_policy_color())

    def test_usage_policy_get_object_set(self):
        self.assertEqual(
            list(self.component_policy.get_object_set()), [self.component])

    def test_usage_policy_get_icon_as_html(self):
        self.assertEqual(
            '<i class="icon" style="color: #000000;"></i>', self.component_policy.get_icon_as_html()
        )

    def test_get_usage_policy_display_with_icon(self):
        self.assertEqual(
            '<i class="icon" style="color: #000000;"></i><span class="ms-1">ComponentPolicy</span>',
            self.component.get_usage_policy_display_with_icon(),
        )

    def test_get_usage_policy_display_as_dict(self):
        expected = {
            "label": "ComponentPolicy",
            "color_code": "#000000",
            "compliance_alert": "",
            "icon": "icon",
        }
        self.assertEqual(expected, self.component_policy.as_dict())

    def test_usage_policy_get_associated_policy_to_model(self):
        # No associated with same content_type
        self.assertIsNone(
            self.license_policy.get_associated_policy_to_model(License))

        # None when no associated policy
        self.assertFalse(self.license_policy.to_policies.exists())
        self.assertIsNone(
            self.license_policy.get_associated_policy_to_model(Component))

        # 1 proper association from License to Component
        AssociatedPolicy.objects.create(
            from_policy=self.license_policy,
            to_policy=self.component_policy,
            dataspace=self.dataspace,
        )
        self.assertEqual(1, self.license_policy.to_policies.count())
        self.assertEqual(1, self.component_policy.from_policies.count())
        self.assertEqual(
            self.component_policy, self.license_policy.get_associated_policy_to_model(
                Component)
        )

        # Associating a second License policy to Component
        # Note that we enforce only 2 associations per content type in AssociatedPolicyForm
        # but not in the AssociatedPolicy.save()
        AssociatedPolicy.objects.create(
            from_policy=self.license_policy,
            to_policy=self.component_policy2,
            dataspace=self.dataspace,
        )
        self.assertEqual(2, self.license_policy.to_policies.count())
        self.assertEqual(1, self.component_policy2.from_policies.count())
        self.assertIsNone(
            self.component_policy.get_associated_policy_to_model(License))

    def test_associated_policy_model_save(self):
        with self.assertRaises(AssertionError):
            AssociatedPolicy.objects.create(
                from_policy=self.license_policy,
                to_policy=self.license_policy,
                dataspace=self.dataspace,
            )

        with self.assertRaises(AssertionError):
            AssociatedPolicy.objects.create(
                from_policy=self.license_policy,
                to_policy=self.license_policy2,
                dataspace=self.dataspace,
            )

        self.assertTrue(
            AssociatedPolicy.objects.create(
                from_policy=self.license_policy,
                to_policy=self.component_policy,
                dataspace=self.dataspace,
            )
        )

        alternate_license_policy = UsagePolicy.objects.create(
            label="LicensePolicy",
            icon="icon",
            content_type=self.license_ct,
            dataspace=self.alternate,
        )

        with self.assertRaises(ValueError):
            AssociatedPolicy.objects.create(
                from_policy=alternate_license_policy,
                to_policy=self.component_policy,
                dataspace=self.dataspace,
            )

        alternate_component_policy = UsagePolicy.objects.create(
            label="ComponentPolicy",
            icon="icon",
            content_type=self.component_ct,
            dataspace=self.alternate,
        )

        with self.assertRaises(ValueError):
            AssociatedPolicy.objects.create(
                from_policy=self.license_policy,
                to_policy=alternate_component_policy,
                dataspace=self.dataspace,
            )

    def test_license_expression_mixin_usage_policy_compliance_alerts(self):
        self.assertEqual([], self.component.compliance_alerts)
        self.assertIsNone(self.component.compliance_table_class())

        self.license_policy.compliance_alert = UsagePolicy.Compliance.ERROR
        self.license_policy.save()

        owner1 = Owner.objects.create(name="Owner1", dataspace=self.dataspace)
        license1 = License.objects.create(
            key="l1",
            name="L1",
            short_name="L1",
            owner=owner1,
            usage_policy=self.license_policy,
            dataspace=self.dataspace,
        )
        self.component.license_expression = license1.key
        self.component.save()

        self.component = Component.objects.get(id=self.component.id)
        self.assertEqual(["error"], self.component.compliance_alerts)
        self.assertEqual(
            "table-danger", self.component.compliance_table_class())
