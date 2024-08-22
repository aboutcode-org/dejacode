#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib.contenttypes.models import ContentType

from dje.forms import ColorCodeFormMixin
from dje.forms import DataspacedAdminForm


class UsagePolicyForm(ColorCodeFormMixin, DataspacedAdminForm):
    def clean_content_type(self):
        """
        Prevent from changing the content_type of the instance if already assigned
        to at least 1 object.
        """
        content_type = self.cleaned_data.get("content_type")

        if self.instance.pk and self.instance.get_object_set().exists():
            if self.instance.content_type != content_type:
                raise forms.ValidationError(
                    "The content type cannot be modified since this object "
                    "is assigned to a least one instance."
                )

        return content_type

    def clean_associated_product_relation_status(self):
        """
        Do not allow to set ``associated_product_relation_status`` on non supported
        model content type.
        """
        relation_status = self.cleaned_data.get("associated_product_relation_status")
        content_type = self.cleaned_data.get("content_type")

        if relation_status and content_type.model not in ["component", "package"]:
            raise forms.ValidationError(
                "This field is only supported for Component and Package Usage Policy."
            )

        return relation_status


class AssociatedPolicyForm(DataspacedAdminForm):
    def __init__(self, *args, **kwargs):
        """Remove choices related to current UsagePolicy instance on edition."""
        super().__init__(*args, **kwargs)
        if self.request._object:
            content_type = self.request._object.content_type
            self.fields["to_policy"].queryset = self.fields["to_policy"].queryset.exclude(
                content_type=content_type
            )

        self.fields["to_policy"].label_from_instance = lambda obj: obj.str_with_content_type()

    def clean(self):
        cleaned_data = super().clean()

        from_policy = cleaned_data.get("from_policy")
        to_policy = cleaned_data.get("to_policy")
        if not from_policy or not to_policy:
            return

        if from_policy.content_type == to_policy.content_type:
            self.add_error("to_policy", "Cannot associate with same object type")

        def get_ct(app_label, model):
            return ContentType.objects.get(app_label=app_label, model=model)

        license_ct = get_ct("license_library", "license")
        component_ct = get_ct("component_catalog", "component")
        subcomponent_ct = get_ct("component_catalog", "subcomponent")
        package_ct = get_ct("component_catalog", "package")

        allowed_associations = [
            from_policy.content_type == license_ct and to_policy.content_type == component_ct,
            from_policy.content_type == component_ct and to_policy.content_type == subcomponent_ct,
            from_policy.content_type == license_ct and to_policy.content_type == package_ct,
        ]
        if not any(allowed_associations):
            msg = (
                "Association only available "
                "from License to Component, "
                "from License to Package, "
                "and from Component to Subcomponent"
            )
            self.add_error("to_policy", msg)

        return cleaned_data
