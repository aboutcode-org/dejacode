#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms

from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout
from crispy_forms.layout import Submit

from dje.forms import DataspacedModelForm
from dje.forms import Group
from organization.models import Owner


class OwnerForm(DataspacedModelForm):
    save_as = True

    class Meta:
        model = Owner
        fields = [
            "name",
            "homepage_url",
            "contact_info",
            "notes",
            "alias",
            "type",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    @property
    def helper(self):
        helper = super().helper

        helper.layout = Layout(
            Fieldset(
                None,
                Group("name", "alias", "contact_info"),
                Group("homepage_url", "type"),
                "notes",
                Submit("submit", self.submit_label, css_class="btn-success"),
                self.save_as_new_submit,
            ),
        )

        return helper
