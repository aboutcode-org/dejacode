#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.exceptions import FieldDoesNotExist


def rename_field_in_reporting_models(apps, to_replace, replace_by):
    """Suitable for a data migration following a field rename migrations.RenameField()"""
    ColumnTemplateAssignedField = apps.get_model(
        "reporting", "ColumnTemplateAssignedField")
    Filter = apps.get_model("reporting", "Filter")
    OrderField = apps.get_model("reporting", "OrderField")

    for model in [ColumnTemplateAssignedField, Filter, OrderField]:
        for obj in model.objects.filter(field_name__icontains=to_replace):
            obj.field_name = obj.field_name.replace(to_replace, replace_by)
            obj.save()


def get_changelist_list_display(request, model_admin):
    """
    Return the list_display value.
    Copy of `ModelAdmin.changelist_view()`.
    """
    list_display = model_admin.get_list_display(request)
    # Check actions to see if any are available on this changelist
    actions = model_admin.get_actions(request)
    if actions:
        # Add the action checkboxes if there are any actions available.
        list_display = ["action_checkbox"] + list(list_display)
    return list_display


def get_ordering_field(model_admin, field_name):
    """
    Return the admin_order_field value.
    Copy of `ChangeList.get_ordering_field()`.
    """
    model = model_admin.model
    try:
        field = model._meta.get_field(field_name)
        return field.name
    except FieldDoesNotExist:
        # See whether field_name is a name of a non-field that allows sorting.
        if callable(field_name):
            attr = field_name
        elif hasattr(model_admin, field_name):
            attr = getattr(model_admin, field_name)
        else:
            attr = getattr(model, field_name)
        return getattr(attr, "admin_order_field", None)
