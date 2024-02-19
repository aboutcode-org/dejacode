#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import uuid

from django import forms
from django.conf import settings
from django.contrib.admin.utils import construct_change_message
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import SuspiciousOperation
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.forms import BoundField
from django.forms.utils import ErrorDict
from django.forms.utils import ErrorList
from django.utils.html import conditional_escape
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML
from crispy_forms.layout import BaseInput
from crispy_forms.layout import Div
from crispy_forms.layout import Field
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout

from dje.copier import copy_object
from dje.copier import get_copy_defaults
from dje.copier import get_object_in
from dje.models import Dataspace
from dje.models import DataspaceConfiguration
from dje.models import History
from dje.models import is_content_type_related
from dje.models import is_dataspace_related
from dje.permissions import get_all_tabsets
from dje.permissions import get_protected_fields
from dje.utils import has_permission

UserModel = get_user_model()


def Group(*fields):
    return Div(
        *[Div(Field(field), css_class="col") for index, field in enumerate(fields)],
        css_class="row",
    )


class StrictSubmit(BaseInput):
    """Submit button without the "btn-primary" class."""

    input_type = "submit"
    field_classes = "btn"


autocomplete_placeholder = {"placeholder": "Start typing for suggestions..."}


class DejaCodeAuthenticationForm(AuthenticationForm):
    """Login form."""

    use_required_attribute = False

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_id = "sign-in"
        helper.form_action = "login"
        helper.form_method = "post"
        helper.form_tag = False

        fields = [
            Field("username", css_class="input-block-level mb-3", placeholder=_("Username")),
            Field("password", css_class="input-block-level mb-3", placeholder=_("Password")),
            Div(
                StrictSubmit("submit", _("Sign in"), css_class="btn-warning"),
                css_class="d-grid",
            ),
        ]

        helper.add_layout(Layout(Fieldset("", *fields)))
        return helper

    def get_invalid_login_error(self):
        username = self.cleaned_data.get("username")
        if "@" in username:
            return ValidationError(
                "Be sure to enter your DejaCode username rather than your email "
                "address to sign in to DejaCode."
            )
        return super().get_invalid_login_error()


class ScopeAndProtectRelationships:
    """Apply Dataspace scoping and field protection on relational fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        protected_fields = get_protected_fields(self._meta.model, self.user)
        self.protected_fields = protected_fields

        for name, field in self.fields.items():
            has_queryset = hasattr(field, "queryset")

            if name in protected_fields:
                field.disabled = True
                if has_queryset:
                    field.queryset = field.queryset.none()

            elif has_queryset and is_dataspace_related(field.queryset.model):
                field.queryset = field.queryset.scope(self.user.dataspace)

                related_model = field.queryset.model
                if is_content_type_related(related_model):
                    content_type = ContentType.objects.get_for_model(self._meta.model)
                    field.queryset = field.queryset.filter(content_type=content_type)


class DataspacedModelForm(ScopeAndProtectRelationships, forms.ModelForm):
    """Base ModelForm for every Model declared as DataspacedModel."""

    save_as = False
    clone_m2m_classes = []
    color_initial = False

    def __init__(self, user, *args, **kwargs):
        self.user = user
        self.dataspace = user.dataspace  # LicenseExpressionFormMixin compat

        super().__init__(*args, **kwargs)

        self.is_addition = not self.instance.id
        if self.is_addition:
            # Set the dataspace early as it may be required during the validation steps.
            self.instance.dataspace = user.dataspace

        if self.color_initial and self.initial and self.is_addition:
            for field_name, value in self.initial.items():
                field = self.fields.get(field_name)
                if field:
                    field.widget.attrs.update({"class": "bg-primary-subtle"})

        self.save_as_new = self.save_as and (self.data or {}).get("save_as_new")

    def _get_validation_exclusions(self):
        """
        Remove the `dataspace` and `uuid` fields from the exclusion,
        meaning those field will be validated.
        Required to enforce the unique_together validation with the dataspace.
        """
        exclude = super()._get_validation_exclusions()
        return {field for field in exclude if field not in ("dataspace", "uuid")}

    def save(self, *args, **kwargs):
        user = self.user

        if self.save_as_new:
            original_instance_id = self.instance.id
            self.is_addition = True
            self.instance.id = None
            self.instance.uuid = uuid.uuid4()
            if hasattr(self.instance, "request_count"):
                self.instance.request_count = None

        if self.is_addition:
            self.instance.created_by = user
        else:
            serialized_data = self.instance.as_json()
            self.instance.last_modified_by = user

        instance = super().save(*args, **kwargs)

        if self.save_as_new:
            self._clone_m2m(original_instance_id, instance)

        if self.is_addition:
            self.assign_object_perms(user)
            History.log_addition(user, instance)
        else:
            message = construct_change_message(self, formsets=None, add=False)
            History.log_change(user, instance, message, serialized_data)

        return instance

    def assign_object_perms(self, user):
        """Assign permissions on added instance."""
        pass

    def _clone_m2m(self, original_instance_id, cloned_instance):
        """
        Clone each defined m2m relations in `self.clone_m2m_classes` during
        the `save_as_new` process.
        """
        field_name = self.instance._meta.model_name
        for model_class in self.clone_m2m_classes:
            if model_class.__name__ == "Subcomponent":
                field_name = "parent"

            related_instances = model_class.objects.filter(
                **{
                    f"{field_name}__id": original_instance_id,
                }
            )

            for relation in related_instances:
                relation.id = None
                relation.uuid = uuid.uuid4()
                setattr(relation, field_name, cloned_instance)
                relation.save()

    @property
    def save_as_new_submit(self):
        conditions = [
            self.save_as,
            not self.is_addition,
            has_permission(self._meta.model, self.user, "add"),
        ]

        if all(conditions):
            return StrictSubmit(
                "save_as_new",
                _("Save as new"),
                css_class="btn btn-outline-success disabled",
            )

    @property
    def submit_label(self):
        verbose_name = self._meta.model._meta.verbose_name
        action = "Add" if self.is_addition else "Update"
        return _(f"{action} {verbose_name.title()}")

    @property
    def helper(self):
        helper = FormHelper()
        model_name = self._meta.model._meta.verbose_name
        helper.form_id = f"{model_name}-form"
        helper.form_method = "post"
        helper.attrs = {"autocomplete": "off"}
        return helper

    @property
    def identifier_fields(self):
        return self._meta.model.get_identifier_fields()


class AccountProfileForm(ScopeAndProtectRelationships, forms.ModelForm):
    username = forms.CharField(disabled=True, required=False)
    email = forms.CharField(disabled=True, required=False)

    class Meta:
        model = UserModel
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "data_email_notification",
            "workflow_email_notification",
            "updates_email_notification",
            "homepage_layout",
        ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.get("instance")
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit)
        changed_fields = ", ".join(self.changed_data)
        History.log_change(instance, instance, f"Profile updated: {changed_fields}.")
        return instance

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_id = "account-profile"
        helper.form_method = "post"
        helper.form_tag = False

        homepage_layout_field = None
        if self.fields["homepage_layout"].queryset:
            homepage_layout_field = Field("homepage_layout", wrapper_class="col-md-6 mt-3")

        # Using a pure HTML so the `dataspace` field is not really part
        # of the form, for security purposes.
        dataspace_field = HTML(
            f"""
        <div id="div_id_dataspace" class="col-md-4">
            <label for="id_dataspace" class="form-label">Dataspace</label>
            <input type="text" value="{self.instance.dataspace}" class="form-control" disabled=""
                   id="id_dataspace">
        </div>
        """
        )

        email_notification_fields = [
            "data_email_notification",
            "workflow_email_notification",
        ]

        if settings.ENABLE_SELF_REGISTRATION:
            email_notification_fields.append("updates_email_notification")

        fields = [
            Div(
                Field("username", wrapper_class="col-md-4"),
                Field("email", wrapper_class="col-md-4"),
                dataspace_field,
                css_class="row",
            ),
            Div(
                Field("first_name", wrapper_class="col-md-6"),
                Field("last_name", wrapper_class="col-md-6"),
                css_class="row",
            ),
            HTML("<hr>"),
            Group(*email_notification_fields),
            homepage_layout_field,
            StrictSubmit(
                "update",
                _("Update profile"),
                css_class="btn-outline-dark mt-3",
            ),
        ]

        helper.add_layout(Layout(*fields))
        return helper


class DataspaceAdminForm(forms.ModelForm):
    def clean(self):
        """Add validation for `update_packages_from_scan` field."""
        cleaned_data = super().clean()
        enable_package_scanning = cleaned_data.get("enable_package_scanning")
        update_packages_from_scan = cleaned_data.get("update_packages_from_scan")

        if update_packages_from_scan and not enable_package_scanning:
            msg = "Package scanning needs to be enabled to use the automatic updates."
            self.add_error("update_packages_from_scan", msg)


class DataspacedAdminForm(forms.ModelForm):
    """
    Use as the base ModelForm for every Model declared as DataspacedModel.
    This is usually not required for inline Forms.
    """

    def __init__(self, *args, **kwargs):
        """
        Injects the dataspace in the instance right after the form
        initialization as a value for dataspace is required for the
        built-in unique_together validation.
        """
        super().__init__(*args, **kwargs)
        # request is not injected in inline forms
        request = getattr(self, "request", None)

        add = not kwargs.get("instance")
        if add and request:
            self.instance.dataspace = request.user.dataspace

    def _get_validation_exclusions(self):
        """
        Remove the `dataspace` and `uuid` fields from the exclusion (ie: validate on those)
        so the unique_together validation within dataspace is enforced.
        """
        exclude = super()._get_validation_exclusions()
        return {field for field in exclude if field not in ("dataspace", "uuid")}


class DataspaceChoiceForm(forms.Form):
    """Offer a choice of target Dataspace for the copy."""

    target = forms.ModelChoiceField(
        queryset=Dataspace.objects.none(),
        label="To Dataspace",
        required=True,
    )
    ids = forms.CharField(
        widget=forms.widgets.HiddenInput,
        required=False,
    )
    _changelist_filters = forms.CharField(
        widget=forms.widgets.HiddenInput,
        required=False,
    )
    _popup = forms.CharField(
        widget=forms.widgets.HiddenInput,
        required=False,
    )

    def __init__(self, source, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not user.dataspace.is_reference:
            raise SuspiciousOperation
        self.fields["target"].queryset = Dataspace.objects.exclude(id=source.id)


class MultiDataspaceChoiceForm(DataspaceChoiceForm):
    target = forms.ModelMultipleChoiceField(
        queryset=Dataspace.objects.none(),
        label="",
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )


class BaseCopyConfigurationForm(forms.Form):
    """Base Form of the copy process, handle the copy configuration (excludes)."""

    ct = forms.CharField(required=True, widget=forms.widgets.HiddenInput)
    exclude_copy = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple())
    exclude_update = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple()
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        ct_from_data = self.fields["ct"].widget.value_from_datadict(
            self.data, self.files, self.add_prefix("ct")
        )
        ct = ct_from_data or self.initial.get("ct")

        self.model_class = ContentType.objects.get(pk=ct).model_class()

        exclude_choices = self.model_class.get_exclude_choices()
        self.fields["exclude_copy"].choices = exclude_choices
        self.fields["exclude_update"].choices = exclude_choices

        if self.initial:  # Set default exclude on initialization
            exclude_copy = get_copy_defaults(user.dataspace, self.model_class)
            self.fields["exclude_copy"].initial = exclude_copy
            self.fields["exclude_update"].initial = exclude_copy


class M2MCopyConfigurationForm(BaseCopyConfigurationForm):
    skip_on_copy = forms.BooleanField(
        label="Exclude this relationship entirely",
        required=False,
    )
    skip_on_update = forms.BooleanField(
        label="Exclude this relationship entirely",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This is used in the object_copy.html
        self.model_verbose_name = self.model_class._meta.verbose_name


class CopyConfigurationForm(BaseCopyConfigurationForm):
    source = forms.ModelChoiceField(
        queryset=Dataspace.objects.none(),
        required=True,
        widget=forms.widgets.HiddenInput,
    )
    targets = forms.ModelMultipleChoiceField(
        queryset=Dataspace.objects.none(),
        required=True,
        widget=forms.widgets.MultipleHiddenInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        reference_dataspace = Dataspace.objects.get_reference()
        if not reference_dataspace:
            return

        if self.user.dataspace == reference_dataspace:
            all_dataspaces = Dataspace.objects.all()
            self.fields["source"].queryset = all_dataspaces
            self.fields["targets"].queryset = all_dataspaces
        else:
            self.fields["source"].queryset = Dataspace.objects.filter(pk=reference_dataspace.pk)
            self.fields["targets"].queryset = Dataspace.objects.filter(pk=self.user.dataspace.pk)

    def submit(self, copy_candidates, selected_for_update, exclude_copy, exclude_update):
        copied, updated, errors = [], [], []
        source = self.cleaned_data.get("source")
        targets = self.cleaned_data.get("targets")

        if copy_candidates:
            copy_qs = self.model_class.objects.scope(source).filter(
                id__in=copy_candidates.split(",")
            )

            for target_dataspace in targets:
                for source_obj in copy_qs:
                    if get_object_in(source_obj, target_dataspace):
                        continue

                    try:
                        copied_obj = copy_object(
                            source_obj,
                            target_dataspace,
                            self.user,
                            update=False,
                            exclude=exclude_copy,
                        )
                    except (IntegrityError, ValidationError) as e:
                        errors.append((source_obj, str(e)))
                    else:
                        copied.append((source_obj, copied_obj))

        if selected_for_update:
            update_qs = self.model_class.objects.filter(dataspace__in=targets).filter(
                id__in=selected_for_update
            )

            for target_obj in update_qs:
                source_obj = get_object_in(target_obj, source)

                try:
                    obj = copy_object(
                        source_obj,
                        target_obj.dataspace,
                        self.user,
                        update=True,
                        exclude=exclude_update,
                    )
                except IntegrityError as e:
                    errors.append((source_obj, str(e)))
                else:
                    updated.append((source_obj, obj))

        return source, copied, updated, errors


class DataspaceConfigurationFormSetMixin:
    dataspace_configuration_field = None
    field_key = None

    def load(self, dataspace, default=None):
        if not self.initial:
            return

        configuration = dataspace.get_configuration(self.dataspace_configuration_field)
        if not configuration:
            if default:
                configuration = default
            else:
                return

        for field_dict in self.initial:
            something = configuration.get(field_dict.get(self.field_key))
            if something:
                field_dict.update(something)

    def serialize(self):
        serialized_data = {}

        for form in self:
            cleaned_data = form.cleaned_data
            field_data = cleaned_data.pop(self.field_key)
            data = {key: value for key, value in cleaned_data.items() if value}
            if data:
                serialized_data[field_data] = data

        return serialized_data

    def save(self, dataspace):
        DataspaceConfiguration.objects.update_or_create(
            dataspace=dataspace,
            defaults={self.dataspace_configuration_field: self.serialize()},
        )

    @staticmethod
    def log_change(request, instance, message):
        """Log that the configuration have been successfully changed."""
        return History.log_change(request.user, instance, message)


class CopyDefaultsForm(forms.Form):
    app_name = forms.CharField(
        widget=forms.widgets.HiddenInput,
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        app_name = self.initial.get("app_name", "")
        if not app_name:
            app_name = self.data.get(self.add_prefix("app_name"))

        dataspaced_models = self.get_all_dataspaced_models()
        models = dataspaced_models.get(app_name, [])

        for model_class in models:
            model_name = str(model_class._meta.verbose_name)
            self.fields[model_name] = forms.MultipleChoiceField(
                label=format_html("{}", model_name.title()),
                required=False,
                choices=model_class.get_exclude_choices(),
                widget=forms.CheckboxSelectMultiple(attrs={"class": "inline"}),
            )

    @staticmethod
    def get_all_dataspaced_models():
        from dje.models import DataspacedModel

        all_subclasses = []
        for model_class in DataspacedModel.__subclasses__():
            all_subclasses.extend([model_class] + model_class.__subclasses__())

        models = {}
        for model_class in all_subclasses:
            if not model_class._meta.abstract and model_class.get_exclude_choices():
                app_verbose_name = model_class._meta.app_config.verbose_name
                models.setdefault(app_verbose_name, []).append(model_class)

        return models


class CopyDefaultsFormSet(
    DataspaceConfigurationFormSetMixin,
    forms.formset_factory(CopyDefaultsForm, extra=0),
):
    dataspace_configuration_field = "copy_defaults"
    field_key = "app_name"


class WarningDict(ErrorDict):
    """
    A collection of warnings that knows how to display itself in various
    formats.

    The dictionary keys are the field names, and the values are the warnings.
    """

    def as_ul(self):
        if not self:
            return ""
        list_items = "".join(["<li>{}{}</li>".format(k, str(v)) for k, v in self.items()])
        return format_html(f'<ul class="warninglist">{list_items}</ul>')


class WarningList(ErrorList):
    """
    A collection of warnings that knows how to display itself in various
    formats.
    """

    def as_ul(self):
        if not self:
            return ""
        list_items = "".join(["<li>{}</li>".format(conditional_escape(str(e))) for e in self])
        return format_html(f'<ul class="warninglist">{list_items}</ul>')


class BoundFieldWithWarnings(BoundField):
    """Extend BoundField class to add 'Warnings'."""

    def _warnings(self):
        return self.form.warnings.get(self.name, self.form.warning_class())

    warnings = property(_warnings)


class ModelFormWithWarnings(forms.ModelForm):
    """
    Extend ModelForm class to add 'Warnings' validation.
    Based on this unmerged patch and heavily modified:
    https://code.djangoproject.com/attachment/ticket/23/form-warnings.2.diff
    SPDX-License-Identifier: BSD-3-Clause
    Copyright (c) django project contributors and Alex Gaynor
    """

    def __init__(self, *args, **kwargs):
        self.warning_class = WarningList
        # Setup here rather than at he begin of full_clean() for early access
        self._warnings = WarningDict()

        super().__init__(*args, **kwargs)

    def __getitem__(self, name):
        """Replace original by BoundFieldWithWarnings."""
        try:
            field = self.fields[name]
        except KeyError:
            raise KeyError(f"Key {name} not found in Form")
        return BoundFieldWithWarnings(self, field, name)

    def _get_warnings(self):
        return self._warnings

    warnings = property(_get_warnings)

    def add_warning(self, field_name, message):
        if field_name in self._warnings:
            self._warnings[field_name].append(message)
        else:
            self._warnings[field_name] = self.warning_class([message])

    def _clean_fields(self):
        super()._clean_fields()
        # Re-iterate for warnings, not optimal...
        for name, field in self.fields.items():
            # This is the Form Field, not the BoundedField.
            warning = getattr(field, "_warnings", None)
            if warning:
                self.add_warning(name, warning)


class CleanStartEndDateFormMixin:
    start_date_field_name = "start_date"
    end_date_field_name = "end_date"

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get(self.start_date_field_name)
        end_date = cleaned_data.get(self.end_date_field_name)

        if start_date and end_date and end_date < start_date:
            msg = "The Start date must be older than the End date."
            self.add_error(self.start_date_field_name, msg)
            self.add_error(self.end_date_field_name, msg)


class ColorCodeFormMixin:
    def clean_color_code(self):
        color_code = self.cleaned_data.get("color_code", "")
        if not color_code.startswith("#"):
            color_code = f"#{color_code}"
        return color_code

    class Meta:
        widgets = {
            "color_code": forms.TextInput(attrs={"type": "color"}),
        }


class TabPermissionsForm(forms.Form):
    group_name = forms.CharField(
        widget=forms.widgets.HiddenInput,
        required=True,
    )

    @staticmethod
    def get_choice_label(tab_name, tab_fields):
        tab_title = tab_name.title().replace("_", " ")

        if not tab_fields:
            return tab_title

        hint = ", ".join(tab_fields)
        css_class = "hint--bottom-right underline-dotted"
        if len(hint) > 60:
            css_class += " hint--large"
        return format_html('<span class="{}" aria-label="{}">{}</span>', css_class, hint, tab_title)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for model_name, tabset in get_all_tabsets().items():
            check_all = '<input type="checkbox" class="float-end" style="margin-left: 15px;">'
            label = format_html(f"{model_name.title()} {check_all}")
            self.fields[model_name] = forms.MultipleChoiceField(
                label=label,
                required=False,
                choices=[
                    (tab_name, self.get_choice_label(tab_name, tab_fields.get("fields")))
                    for tab_name, tab_fields in tabset.items()
                ],
                widget=forms.CheckboxSelectMultiple(attrs={"class": "inline"}),
            )


class TabPermissionsFormSet(
    DataspaceConfigurationFormSetMixin,
    forms.formset_factory(TabPermissionsForm, extra=0),
):
    dataspace_configuration_field = "tab_permissions"
    field_key = "group_name"


class DefaultOnAdditionLabelMixin:
    default_on_addition_fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in self.default_on_addition_fields:
            field = self.fields.get(field_name)
            if not field:
                continue
            field.queryset = field.queryset.scope(self.dataspace)
            field.label_from_instance = self.label_from_instance

            protected_fields = getattr(self, "protected_fields", [])
            if field_name not in protected_fields:
                for instance in field.queryset:
                    if instance.default_on_addition:
                        field.initial = instance
                        break

    @staticmethod
    def label_from_instance(obj):
        """Add the "(default)" in the label of the `default_on_addition` instance."""
        if obj.default_on_addition:
            return f"{obj} (default)"
        return str(obj)


class OwnerChoiceField(forms.ModelChoiceField):
    def to_python(self, value):
        try:
            return self.queryset.get(name=value)
        except ObjectDoesNotExist:
            return super().to_python(value)

    def prepare_value(self, value):
        try:
            return self.queryset.get(id=value)
        except (ObjectDoesNotExist, ValueError):
            return super().prepare_value(value)


class JSONListField(forms.CharField):
    def prepare_value(self, value):
        if isinstance(value, list):
            value = ", ".join(value)
        return super().prepare_value(value)

    def to_python(self, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return super().to_python(value)

    def has_changed(self, initial, data):
        if isinstance(data, str):
            data = [item.strip() for item in data.split(",") if item.strip()]
        return super().has_changed(initial, data)
