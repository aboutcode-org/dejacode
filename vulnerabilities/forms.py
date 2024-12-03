#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.core.exceptions import ValidationError

from crispy_forms.helper import FormHelper

from dje.forms import DataspacedModelForm
from product_portfolio.models import ProductPackage
from vulnerabilities.models import VulnerabilityAnalysis


class VulnerabilityAnalysisForm(DataspacedModelForm):
    responses = forms.MultipleChoiceField(
        choices=VulnerabilityAnalysis.Response.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = VulnerabilityAnalysis
        fields = [
            "product_package",
            "vulnerability",
            "state",
            "justification",
            "responses",
            "detail",
        ]
        widgets = {
            "product_package": forms.widgets.HiddenInput,
            "vulnerability": forms.widgets.HiddenInput,
            "detail": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)

        responses_model_field = self._meta.model._meta.get_field("responses")
        self.fields["responses"].help_text = responses_model_field.help_text

        product_package_field = self.fields["product_package"]
        perms = ["view_product", "change_product"]
        product_package_field.queryset = ProductPackage.objects.product_secured(user, perms=perms)

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_tag = False
        helper.modal_title = "Vulnerability analysis"
        helper.modal_id = "vulnerability-analysis-modal"
        return helper

    def clean(self):
        main_fields = ["state", "justification", "responses", "detail"]
        if not any(self.cleaned_data.get(field_name) for field_name in main_fields):
            raise ValidationError(
                "At least one of state, justification, responses or detail must be provided."
            )
