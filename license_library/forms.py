#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms

from component_catalog.license_expression_dje import LicenseExpressionFormMixin
from dje.forms import DataspacedAdminForm
from dje.mass_update import DejacodeMassUpdateForm


class LicenseAdminForm(DataspacedAdminForm):
    def __init__(self, *args, **kwargs):
        """Add the language code in the choice label."""
        super().__init__(*args, **kwargs)
        language_field = self.fields["language"]
        language_field.choices = [
            (code, f"{name} [{code}]" if code else name) for code, name in language_field.choices
        ]

    def clean_full_text(self):
        """Prevent from changing the License.full_text when annotations exist."""
        full_text = self.cleaned_data["full_text"]

        if not self.instance.pk:  # change only
            return full_text

        conditions = [
            self.instance.full_text != full_text,
            self.instance.annotations.exists(),
        ]
        if all(conditions):
            raise forms.ValidationError(
                "Existing Annotations are defined on this license text. "
                "You need to manually delete all those Annotations first "
                "to be able to update the license text."
            )

        return full_text


class LicenseMassUpdateForm(DejacodeMassUpdateForm):
    raw_id_fields = ["owner"]

    class Meta:
        # We are not including the 'license_profile' field on purpose. It's not
        # appropriate for mass update. Also there's some specific data changes
        # on cascade when updating its value from the change form, see
        # LicenseAdmin.save_model()
        fields = [
            "reviewed",
            "owner",
            "category",
            "license_style",
            "license_status",
            "is_active",
            "usage_policy",
            "is_component_license",
            "is_exception",
            "curation_level",
            "popularity",
            "language",
            "reference_notes",
            "guidance",
            "special_obligations",
            "admin_notes",
        ]


class LicenseChoiceAdminForm(LicenseExpressionFormMixin, DataspacedAdminForm):
    expression_field_names = ["from_expression", "to_expression"]

    def clean_from_expression(self):
        expression = self.cleaned_data.get("from_expression")
        return self.clean_expression_base(expression)

    def clean_to_expression(self):
        expression = self.cleaned_data.get("to_expression")
        return self.clean_expression_base(expression)
