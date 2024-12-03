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
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout

from dje.forms import DataspacedModelForm
from dje.forms import Group
from product_portfolio.models import ProductPackage
from vulnerabilities.models import VulnerabilityAnalysis


class VulnerabilityAnalysisForm(DataspacedModelForm):
    responses = forms.MultipleChoiceField(
        choices=VulnerabilityAnalysis.Response.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    affected_products = forms.MultipleChoiceField(
        label="Propagate analysis to products:",
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text=(
            "The listed products share the same vulnerable package. "
            "The analysis values will be applied to all selected products."
        )
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
            "affected_products",
        ]
        widgets = {
            "product_package": forms.widgets.HiddenInput,
            "vulnerability": forms.widgets.HiddenInput,
            "detail": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, user, *args, **kwargs):
        affected_products = kwargs.pop("affected_products", [])
        super().__init__(user, *args, **kwargs)

        affected_products_field = self.fields["affected_products"]
        affected_products_choices = [(product.uuid, str(product)) for product in affected_products]
        affected_products_field.choices = affected_products_choices
        if not affected_products_choices:
            affected_products_field.widget = forms.widgets.HiddenInput()

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
        helper.layout = Layout(
            Fieldset(
                "",
                Group("state", "justification"),
                "responses",
                "detail",
                "affected_products",
            ),
        )
        return helper

    def clean(self):
        main_fields = ["state", "justification", "responses", "detail"]
        if not any(self.cleaned_data.get(field_name) for field_name in main_fields):
            raise ValidationError(
                "At least one of state, justification, responses or detail must be provided."
            )
