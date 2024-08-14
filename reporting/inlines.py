#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib import admin

from reporting.forms import ColumnTemplateAssignedFieldFormSet
from reporting.forms import FilterForm
from reporting.forms import OrderFieldForm
from reporting.models import ColumnTemplateAssignedField
from reporting.models import Filter
from reporting.models import OrderField


class FilterInline(admin.TabularInline):
    model = Filter
    fk_name = "query"
    # Delegate to the Ember-based inline UI the responsibility of rendering, so
    # instantiate 0 extra forms
    extra = 0
    form = FilterForm


class OrderFieldInline(admin.TabularInline):
    model = OrderField
    fk_name = "query"
    # Delegate to the Ember-based inline UI the responsibility of rendering, so
    # instantiate 0 extra forms
    extra = 0
    form = OrderFieldForm


class ColumnTemplateAssignedFieldInline(admin.TabularInline):
    model = ColumnTemplateAssignedField
    # Delegate to the Ember-based inline UI the responsibility of rendering, so
    # instantiate 0 extra forms
    extra = 0
    formset = ColumnTemplateAssignedFieldFormSet

    def get_formset(self, request, obj=None, **kwargs):
        """
        Injecting the request in the FormSets, required for the validation in
        ColumnTemplateAssignedFieldFormSet.clean()
        """
        FormSet = super().get_formset(request, obj, **kwargs)
        FormSet._request = request
        return FormSet
