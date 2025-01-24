#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

# Forked from https://github.com/saxix/django-adminactions/blob/
# 03f0deb545e09761d5ea7b5a6e348e15038d8189/adminactions/mass_update.py
# The mass_update action is the only piece that we require from django-adminactions

# * Copyright (c) 2010, Stefano Apostolico (s.apostolico@gmail.com)
# * Dual licensed under the MIT or GPL Version 2 licenses.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     1. Redistributions of source code must retain the above copyright notice,
#        this list of conditions and the following disclaimer.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from contextlib import suppress

from django import dispatch
from django import forms
from django.contrib import messages
from django.contrib.admin import widgets
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.helpers import AdminForm
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError
from django.forms.models import ModelForm
from django.forms.models import modelform_factory
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from dje.models import is_dataspace_related
from dje.permissions import get_protected_fields
from dje.utils import set_intermediate_explicit_m2m

action_end = dispatch.Signal()


class BaseMassUpdateForm(ModelForm):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    select_across = forms.BooleanField(
        label="",
        required=False,
        initial=0,
        widget=forms.HiddenInput({"class": "select-across"}),
    )
    action = forms.CharField(
        label="",
        required=True,
        initial="mass_update",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._errors = None

    def configured_fields(self):
        return [field for field in self if not field.is_hidden and field.name.startswith("_")]

    def model_fields(self):
        """Return a list of BoundField objects that aren't "private" fields."""
        return [
            field
            for field in self
            if not (field.name.startswith("_") or field.name in ["select_across", "action"])
        ]

    def _clean_fields(self):
        for name, field in self.fields.items():
            raw_value = field.widget.value_from_datadict(
                self.data, self.files, self.add_prefix(name)
            )
            try:
                enabler = f"chk_id_{name}"
                if self.data.get(enabler, False):
                    self.fields[name].enabled = True
                    self.cleaned_data[name] = field.clean(raw_value)
                    # Field attribute clean method, only if enabled
                    if hasattr(self, f"clean_{name}"):
                        self.cleaned_data[name] = getattr(self, f"clean_{name}")()
            except ValidationError as e:
                self._errors[name] = self.error_class(e.messages)
                if name in self.cleaned_data:
                    del self.cleaned_data[name]


class DejacodeMassUpdateForm(BaseMassUpdateForm):
    """
    Custom Form for the Mass Update feature, mostly use to limit the available
    fields and to restrict relational fields to the User Dataspace.
    """

    raw_id_fields = []

    def __init__(self, data=None, *args, **kwargs):
        self.dataspace = kwargs.pop("dataspace")
        super().__init__(data, *args, **kwargs)
        model_class = self._meta.model

        for field in model_class().local_foreign_fields:
            self.scope_queryset(field)
            if field.related_model.__name__ == "UsagePolicy":
                self.scope_content_type(field)

        for field in model_class._meta.many_to_many:
            self.scope_queryset(field)

        # Support for raw_id_fields, similar to ModelAdmin.raw_id_fields
        for field_name in self.raw_id_fields:
            db_field = model_class._meta.get_field(field_name)
            self.fields[field_name].widget = widgets.ForeignKeyRawIdWidget(
                db_field.remote_field, self.admin_site
            )

    def scope_queryset(self, field):
        """Scope the QuerySet of the given `field` to the Dataspace of selected object."""
        if field.name not in self.fields:
            return  # Skips fields excluded from the form

        if is_dataspace_related(field.related_model):
            form_field = self.fields[field.name]
            form_field.queryset = form_field.queryset.scope(self.dataspace)

    def scope_content_type(self, field):
        """Scope the QuerySet of the given `field` to the content type of the current object."""
        if field.name not in self.fields:
            return  # Skips fields excluded from the form

        form_field = self.fields[field.name]
        content_type = ContentType.objects.get_for_model(self._meta.model)
        form_field.queryset = form_field.queryset.filter(content_type=content_type)


def not_required(field, **kwargs):
    """Force all fields as not required."""
    kwargs["required"] = False
    return field.formfield(**kwargs)


def mass_update_action(modeladmin, request, queryset):
    if not queryset:
        return

    # Dataspace is required for scoping, we trust the queryset for security purpose
    # over the values provided in the request data.
    dataspace = queryset.first().dataspace
    opts = modeladmin.model._meta
    preserved_filters = modeladmin.get_preserved_filters(request)

    # Allows to specified a custom mass update Form in the ModelAdmin
    mass_update_form = getattr(modeladmin, "mass_update_form", BaseMassUpdateForm)
    MassUpdateForm = modelform_factory(
        modeladmin.model,
        form=mass_update_form,
        exclude=get_protected_fields(modeladmin.model, request.user),
        formfield_callback=not_required,
    )
    MassUpdateForm.admin_site = modeladmin.admin_site  # required by the ForeignKeyRawIdWidget

    if "apply" in request.POST:
        form = MassUpdateForm(request.POST, dataspace=dataspace)
        if form.is_valid():
            changelist_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            redirect_url = add_preserved_filters(
                {"preserved_filters": preserved_filters, "opts": opts}, changelist_url
            )

            updated = 0
            errors = []
            for record in queryset:
                for field_name, value in form.cleaned_data.items():
                    try:
                        field_object = record._meta.get_field(field_name)
                    except FieldDoesNotExist:
                        continue  # field_name is not part of the model

                    # auto_created is only True on implicit m2m model
                    if (
                        field_object.many_to_many
                        and not field_object.remote_field.through._meta.auto_created
                    ):
                        set_intermediate_explicit_m2m(record, field_object, value)
                    else:
                        setattr(record, field_name, value)
                # This have no impact if the model does not declare this field.
                record.last_modified_by = request.user
                # Some validation errors cannot be caught during the form validation as only
                # the "new" value of the selected fields are available.
                # We cannot validate those changes against the existing value of others fields on
                # the instance so the error can be raised at save() time.
                try:
                    record.save()
                except ValidationError as e:
                    errors.append(e.message)
                else:
                    updated += 1

            if updated:
                messages.info(request, _(f"Updated {updated} records"))

            if errors:
                messages.error(request, _(f"{len(errors)} error(s): {', '.join(errors)}"))

            action_end.send(
                sender=modeladmin.model,
                action="mass_update",
                request=request,
                queryset=queryset,
                modeladmin=modeladmin,
                form=form,
            )
            return redirect(redirect_url)
    else:
        initial = {
            ACTION_CHECKBOX_NAME: request.POST.getlist(ACTION_CHECKBOX_NAME),
            "select_across": request.POST.get("select_across") == "1",
        }
        form = MassUpdateForm(initial=initial, dataspace=dataspace)

    adminform = AdminForm(form, modeladmin.get_fieldsets(request), {}, [], model_admin=modeladmin)

    with suppress(AttributeError):
        form.extra_init(request, modeladmin)

    context = {
        "adminform": adminform,
        "form": form,
        "opts": opts,
        "queryset": queryset,
        "preserved_filters": preserved_filters,
        "media": modeladmin.media,
    }
    return render(request, "admin/mass_update.html", context)


mass_update_action.short_description = "Mass update"
