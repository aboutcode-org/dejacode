#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib import admin
from django.db.models import PositiveSmallIntegerField
from django.forms import HiddenInput
from django.forms.models import BaseInlineFormSet

from workflow.models import Question


class QuestionInlineFormset(BaseInlineFormSet):
    def clean(self):
        """
        Check that each Question.label is unique for the RequestTemplate to
        avoid issues when de-serializing the data into a dict using label as
        keys.
        """
        super().clean()

        # Don't bother validating formset unless each form is valid on its own
        if any(self.errors):
            return

        # Note that we could instead add "('template', 'label')" in the
        # unique_together meta of the Question model.
        # It seems overkill to enforce this one at the database level for now.
        all_labels = [
            form.cleaned_data.get("label")
            for form in self.forms
            if not form.cleaned_data.get("DELETE")
        ]

        if len(all_labels) != len(set(all_labels)):
            raise forms.ValidationError(
                "Question with this Label for this Template already exists."
            )


class QuestionInline(admin.TabularInline):
    model = Question
    formset = QuestionInlineFormset
    extra = 1
    sortable_field_name = "position"
    formfield_overrides = {
        PositiveSmallIntegerField: {"widget": HiddenInput},
    }
