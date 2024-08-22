#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import csv
import json

from django import forms
from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.forms import BooleanField
from django.forms import ModelChoiceField
from django.forms import TypedChoiceField
from django.forms.formsets import DEFAULT_MAX_NUM
from django.forms.models import BaseModelFormSet
from django.forms.models import modelformset_factory
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils.encoding import smart_str

from component_catalog.forms import AddToProductMultipleForm
from dje.fields import ExtendedBooleanCheckboxInput
from dje.fields import ExtendedNullBooleanSelect
from dje.fields import SmartFileField
from dje.forms import ModelFormWithWarnings
from dje.models import History
from dje.models import is_content_type_related
from dje.permissions import get_protected_fields
from dje.utils import extract_name_version


def get_object_pk(obj_value, obj_class, dataspace, extra_filters=None):
    if not obj_value:
        return

    # This does not support unique_together with ore than 2 fields.
    # See also UsagePolicy.get_identifier_fields
    identifier = obj_class.get_identifier_fields()[0]
    filters = {identifier: obj_value}

    if extra_filters:
        filters.update(extra_filters)

    try:
        return int(obj_value)
    except ValueError:
        pass

    # If we got some string, let's try to see if there's a match
    try:
        instance = obj_class.objects.get(dataspace=dataspace, **filters)
    except obj_class.DoesNotExist:
        pass
    else:
        return instance.pk


class ModelChoiceFieldForImport(ModelChoiceField):
    def __init__(self, *args, **kwargs):
        # Custom value provided on the ModelForm
        self.identifier_field = kwargs.pop("identifier_field", None)
        super().__init__(*args, **kwargs)

    def clean(self, value):
        # Skip if value is None, the usual Required error will be raised.
        # If we got a value, try to match the object.
        if value:
            try:
                pk = int(value)
            except ValueError:
                pk = None

            if pk:
                try:
                    object = self.queryset.get(pk=pk)
                except ObjectDoesNotExist:
                    pass
                else:
                    # Injecting a special value for display in UI
                    self.value_for_display = object.get_admin_link(target="_blank")

        return super().clean(value)


class BaseImportModelForm(ModelFormWithWarnings):
    """Base ModelForm class extension to be used in an Importer."""

    def __init__(self, data=None, *args, **kwargs):
        # Needs to be pop before the super() but only if provided
        if kwargs:
            self.dataspace = kwargs.pop("dataspace")
            self.user = kwargs.pop("user")
            self.prefix = kwargs.get("prefix")

        if not data:  # Unbounded Form
            super().__init__(*args, **kwargs)
            # We still want to run the post_process to set the proper QuerySets on the FKs.
            self.post_process_form()
            return

        # Convert the given value into the instance pk in the data dict
        for name, field in self.declared_fields.items():
            if issubclass(field.__class__, ModelChoiceFieldForImport):
                prefix = self.add_prefix(name)
                value = field.widget.value_from_datadict(data, None, prefix)
                model = field.queryset.model
                extra_filters = {}
                if is_content_type_related(model):
                    content_type = ContentType.objects.get_for_model(self._meta.model)
                    extra_filters["content_type"] = content_type
                pk = get_object_pk(value, field.queryset.model, self.dataspace, extra_filters)
                if pk:
                    data[prefix] = pk

        data, instance = self.pre_process_form(data, **kwargs)
        if instance:
            kwargs.update({"instance": instance})

        super().__init__(data, *args, **kwargs)

        self.post_process_form()

        if not self.instance.pk:
            self.instance.dataspace = self.dataspace

    def pre_process_form(self, data, **kwargs):
        """
        Use the given `data` for the row to match an already existing instance
        based on the unique_together fields of the Model.
        The matching is skipped if the instance was already set in the kwargs.
        Pre-init custom code should be executed here.
        """
        instance = kwargs.pop("instance", None)

        if not instance:
            model_class = self._meta.model
            prefix = kwargs.get("prefix", "")
            if prefix:
                prefix += "-"

            filters = {"dataspace": self.dataspace}
            identifier_fields = model_class.get_identifier_fields()
            # Crafting the list of unique filters to match the instance
            for field_name in identifier_fields:
                value = data.get(prefix + field_name, "")
                if value:
                    value = value.strip()
                filters.update({field_name: value})

            try:
                instance = model_class.objects.get(**filters)
            except (model_class.DoesNotExist, MultipleObjectsReturned):
                instance = None

        return data, instance

    def post_process_form(self):
        """
        Scope the QuerySets of FK fields.
        Use this method to manipulate the Form after it was created.
        self.data is available as this is called after the super()
        Remove the `protected_fields` from the `fields` dict.

        Possible enhancements:
         * We may need to do the same for M2M fields
         * This is executed for each row, not efficient, we should somehow
           store the value in a cache.
        """
        protected_fields = get_protected_fields(self._meta.model, self.user)
        for field_name in protected_fields:
            if field_name in self.fields:
                del self.fields[field_name]

        for fk_field in self._meta.model().local_foreign_fields:
            # Relying on the fields exposed on the form, excluded field will
            # not be processed, also the dataspace field will be skipped as
            # not a field on the form.
            if fk_field.name not in self.fields.keys():
                continue

            form_field = self.fields[fk_field.name]
            form_field.queryset = fk_field.related_model.objects.scope(self.dataspace)

            if is_content_type_related(fk_field.related_model):
                form_field.queryset = form_field.queryset.filter(
                    content_type=ContentType.objects.get_for_model(self._meta.model)
                )

            identifier_field = getattr(form_field, "identifier_field", None)
            if not identifier_field:
                continue

            choices = [str(getattr(choice, identifier_field, "")) for choice in form_field.queryset]
            form_field.error_messages["invalid_choice"] = (
                'That choice is not one of the available choices: "{}"'.format(", ".join(choices))
            )

        for field_name, field in self.fields.items():
            # Using `type()` comparison in place if `isinstance` since we do not want
            # to compare on the field class inheritance.
            # For example, a `NullBooleanField` is also an instance of `BooleanField`,
            # therefore the proper widget will not be applied.
            field_type = type(field)
            if field_type is forms.fields.BooleanField:
                field.widget = ExtendedBooleanCheckboxInput()
            elif field_type is forms.fields.NullBooleanField:
                field.widget = ExtendedNullBooleanSelect()

    def save(self, commit=True):
        """Set the `created_by` and `last_modified_by` values before save."""
        self.instance.created_by = self.user
        self.instance.last_modified_by = self.user
        return super().save(commit)


class BaseImportModelFormSet(BaseModelFormSet):
    """Base ModelFormSet class extension to be used in an Importer."""

    def __init__(self, *args, **kwargs):
        self._warnings = None
        super().__init__(*args, **kwargs)

    def _get_warnings(self):
        """Return a list of ``form.warnings`` for every form in self.forms."""
        if self._warnings is None:
            self.warnings_clean()
        return self._warnings

    warnings = property(_get_warnings)

    def warnings_clean(self):
        """
        Clean all ``self.data`` and populates ``self._warning``.
        Based on full_clean.
        """
        self._warnings = []
        if not self.is_bound:  # Stop further processing.
            return
        for i in range(0, self.total_form_count()):
            form = self.forms[i]
            if form.warnings:
                self._warnings.append(form.warnings)

    def clean(self):
        """Add row duplication validation."""
        super().clean()
        all_values = []
        has_duplicate = False

        fields_name = self.model.get_identifier_fields()

        if self.model.__name__ == "ProductComponent":
            return

        for i in range(0, self.total_form_count()):
            form = self.forms[i]
            cleaned_data = getattr(form, "cleaned_data", None)
            if not cleaned_data:
                continue

            values = [str(cleaned_data.get(field_name)) for field_name in fields_name]

            if values not in all_values:
                all_values.append(values)
            else:
                has_duplicate = True
                # Inject the error at the Form level
                for field_name in fields_name:
                    if field_name not in form._errors:
                        form._errors[field_name] = self.error_class([])
                    form._errors[field_name].append("This row is a duplicate.")

        # Raise after the loop as we may have several duplicates
        # Throw at the FormSet level, available at formset.non_form_errors
        if has_duplicate:
            raise forms.ValidationError("One of the row is a duplicate.")


class ImportableUploadFileForm(forms.Form):
    file = SmartFileField(extensions=["csv"])


class BaseImporter:
    """
    Import in 3 steps:
        1. File upload:
            * headers validation
            * no access to step 2 until all required columns are present
            * no check on data content

        2. Import preview:
            * building 1 form per row based on the input data
            * feedback on errors, additions, reconciliations
            * empty rows are skipped
            * requires full input data validity to proceed

        3. Import:
            * creates new objects using each form.save()
            * Return an import "report"
    """

    model_form = None
    formset_class = BaseImportModelFormSet
    upload_form_class = ImportableUploadFileForm
    add_to_product = False
    update_existing = False

    def __init__(self, user, file_location=None, formset_data=None):
        if not self.model_form and not isinstance(self.model_form, BaseImportModelForm):
            raise AttributeError

        self.user = user
        self.dataspace = user.dataspace
        self.model_class = self.model_form._meta.model
        self.verbose_name = self.model_class._meta.verbose_name
        self.fatal_errors = []  # Any of these errors locks the user in step 1
        self.headers = []  # Using a list rather than a set to keep the order
        self.ignored_columns = set()
        self.file_location = file_location
        self.results = {}

        self.required_fields = []
        self.supported_fields = []
        self.default_value_fields = {}
        self.construct_field_lists()

        if not formset_data and file_location:
            input_as_list_of_dict = self.process_file_input()
            formset_data = self.get_data_for_formset(input_as_list_of_dict)

        if formset_data:
            self.formset = self.build_formset(formset_data)
            self.formset.is_valid()  # Triggers the validation methods

    def construct_field_lists(self):
        """
        Construct 2 lists of fields `supported_fields` and `required_fields`,
        based on the ModelForm rather than the Model so even the added fields
        on the Form are supported.
        Also constructs a default_value_fields dict of the default values.
        """
        protected_fields = get_protected_fields(self.model_class, self.user)

        for field_name, field in self.model_form.base_fields.items():
            if field_name in protected_fields:
                continue

            # "is not None" because 0 and False can be initial values
            if not field.required or field.initial is not None:
                self.supported_fields.append(field_name)
            else:
                self.required_fields.append(field_name)

            # Keeping the default values in a dict to be used in the data
            if field.initial is not None:
                self.default_value_fields[field_name] = field.initial

    def build_headers(self, header_row):
        """Build the headers and ignored_columns sets."""
        for header in header_row:
            if header not in self.supported_fields + self.required_fields:
                self.ignored_columns.add(header)
            elif header not in self.headers:
                self.headers.append(header)
            else:
                self.fatal_errors.append(f'Column "{header}" is listed more than once.')

    def get_reader(self):
        # Encoding is assumed to be either UTF-8 or Windows-1252 (because Excel
        # writes CSVs with this encoding by default)
        try:
            with open(self.file_location, newline="", encoding="utf-8-sig") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # Opening a file in cp1252 is not going to cause decode errors
            # because cp1252 is a single-byte encoding and will try to decode
            # each byte even if it does it wrong
            with open(self.file_location, newline="", encoding="windows-1252") as f:
                lines = f.readlines()
        return csv.reader(lines)

    @staticmethod
    def _get_unicode_hint(exc):
        """
        Return an hint on the unicode string that caused the issue.
        This code was taken from django.views.debug.ExceptionReporter
        """
        if not issubclass(type(exc), UnicodeError):
            return

        start = getattr(exc, "start", None)
        end = getattr(exc, "end", None)
        if start is not None and end is not None:
            unicode_str = exc.args[1]
            start = max(start - 5, 0)
            end = min(end + 5, len(unicode_str))
            return smart_str(
                unicode_str[start:end],
                "ascii",
                errors="replace",
            )

    def process_file_input(self):
        if self.file_location.endswith(".csv"):
            return self.process_file_input_csv()
        elif self.file_location.endswith(".json"):
            return self.process_file_input_json()
        else:
            raise NotImplementedError

    def prepare_data_json(self, data):
        return

    def process_file_input_json(self):
        with open(self.file_location) as f:
            file_content = f.read()

        try:
            data = json.loads(file_content)
        except json.JSONDecodeError:
            self.fatal_errors.append("The content is not proper JSON.")
            return

        return self.prepare_data_json(data)

    def process_file_input_csv(self):
        try:
            reader = self.get_reader()
        except UnicodeDecodeError as e:
            msg = "Encoding issue."
            unicode_hint = self._get_unicode_hint(e)
            if unicode_hint:
                msg += f" The string that could not be encoded/decoded was: {unicode_hint}"
            self.fatal_errors.append(msg)
            return

        try:
            header_row = next(reader)
        except StopIteration:
            self.fatal_errors.append("The input file is empty.")
            return
        except (UnicodeDecodeError, UnicodeEncodeError):
            self.fatal_errors.append('The input file is not "utf-8" encoded.')
            return
        else:
            # Keeping the header length for future row size validation
            header_row_len = len(header_row)

        # Headers validation. Verifies that the required columns are present
        for field in self.required_fields:
            if field not in header_row:
                self.fatal_errors.append(f'Required column missing: "{field}".')

        self.build_headers(header_row)

        if self.fatal_errors:
            return

        # Craft a list of dictionaries (1 per row) to be used in future
        # validation and processing
        input_as_list_of_dict = []
        for line_number, row in enumerate(reader, start=2):
            # Skip empty and trailing rows
            if not row:
                continue

            if len(row) != header_row_len:
                self.fatal_errors.append(f"Row at line {line_number} is not valid.")
                return

            row_as_dict = {}
            for j, cell in enumerate(row):
                field_name = header_row[j]
                if field_name not in self.ignored_columns:
                    row_as_dict[field_name] = cell

            input_as_list_of_dict.append(row_as_dict)

        # Proper header columns but no data row
        if not input_as_list_of_dict:
            self.fatal_errors.append("No data row in input file.")
            return

        if len(input_as_list_of_dict) > DEFAULT_MAX_NUM:
            self.fatal_errors.append(f"Import limited to {DEFAULT_MAX_NUM} rows")
            return

        return input_as_list_of_dict

    def get_formset_factory(self):
        """Return a FormSet class for use on the formset creation."""
        return modelformset_factory(
            self.model_class, form=self.model_form, formset=self.formset_class, extra=0
        )

    def get_data_for_formset(self, input_as_list_of_dict):
        """
        Return an input compatible with formset `data` argument from a list of
        mapping field name->value.
        """
        if not input_as_list_of_dict:
            return

        data = {
            "form-TOTAL_FORMS": str(len(input_as_list_of_dict)),
            "form-INITIAL_FORMS": "0",
            "form-MAX_NUM_FORMS": DEFAULT_MAX_NUM,
        }

        for index, row in enumerate(input_as_list_of_dict):
            # Set value if none was provided for field with default on the Model
            for field_name, default_value in self.default_value_fields.items():
                # Handle either column not present and present with empty value
                if field_name not in row or not row[field_name]:
                    row[field_name] = default_value
            # Crafting the data to be used as the Formset input
            for field_name, value in row.items():
                data.update({f"form-{index}-{field_name}": value})

        return data

    def get_form_kwargs(self):
        return {
            "user": self.user,
            "dataspace": self.dataspace,
        }

    def build_formset(self, formset_data):
        """Return the formset instance from then given `formset_data`."""
        formset_class = self.get_formset_factory()
        mutable_data = formset_data.copy()

        return formset_class(
            data=mutable_data,
            queryset=self.model_class.objects.none(),
            form_kwargs=self.get_form_kwargs(),
        )

    @staticmethod
    def get_supported_values(field):
        identifier_field = getattr(field, "identifier_field", None)

        if identifier_field and field.queryset:  # ModelChoiceFieldForImport
            return [(getattr(instance, identifier_field), None) for instance in field.queryset]
        elif isinstance(field, TypedChoiceField):
            return [(value, description) for value, description in field.choices if value]
        elif isinstance(field, BooleanField):
            return [("True", "True, T, Y"), ("False", "No, F, N")]

        return []

    def get_key_sorted_fields(self):
        """
        Return a key-sorted dict of the supported field based on the
        ModelForm bounded fields so the QuerySet values for the FKs are
        available.
        Note that this can only be done on an instance of the model_form.
        """
        model_form_instance = self.model_form(dataspace=self.dataspace, user=self.user)

        for field in model_form_instance.fields.values():
            field.supported_values = self.get_supported_values(field)

        return sorted(model_form_instance.fields.items())

    def is_valid(self):
        return self.formset.is_valid()

    @property
    def errors(self):
        return self.formset.errors

    @transaction.atomic()
    def save_all(self):
        """Save new objects in DB, skip matched objects. Commit only on success."""
        if not self.formset.is_valid():  # Just in case...
            return

        self.results = {"added": [], "modified": [], "unmodified": []}
        for form in self.formset:
            self.save_form(form)

    def save_form(self, form):
        instance = form.instance

        if not instance.pk:
            saved_instance = form.save()
            self.results["added"].append(saved_instance)
            History.log_addition(self.user, saved_instance)
            return

        elif self.update_existing:
            # We need to refresh the instance from the db because form.instance has
            # the unsaved form.cleaned_data modification at that stage.
            instance.refresh_from_db()
            updated_fields = instance.update_from_data(self.user, form.cleaned_data, override=False)
            if updated_fields:
                self.results["modified"].append(instance)
                msg = f'Updated {", ".join(updated_fields)} from import'
                History.log_change(self.user, instance, message=msg)
                return

        self.results["unmodified"].append(instance)

    def get_added_instance_ids(self):
        """Return the list of added instance ids."""
        if self.results.get("added"):
            return [instance.id for instance in self.results["added"]]

    def get_admin_changelist_url(self):
        """Return the URL for the changelist of the current model class."""
        opts = self.model_class._meta
        info = opts.app_label, opts.model_name
        return reverse("admin:{}_{}_changelist".format(*info))

    def get_add_to_product_form(self, request):
        relation_model = getattr(self, "relation_model", None)
        add_to_product_perm = getattr(self, "add_to_product_perm", None)

        conditions = [
            relation_model,
            add_to_product_perm,
            request.user.has_perm(add_to_product_perm),
        ]
        if not all(conditions):
            return

        form = AddToProductMultipleForm(
            request=request,
            model=self.model_form._meta.model,
            relation_model=relation_model,
        )

        # Do not include the `form` if the Product QuerySet is empty
        if form.fields["product"].queryset:
            return form


@login_required()
def import_view(request, importer_class):
    user = request.user
    importer = importer_class(user)
    upload_form_class = importer.upload_form_class

    opts = importer.model_form._meta.model._meta
    perm_codename = get_permission_codename("add", opts)
    if not user.has_perm(f"{opts.app_label}.{perm_codename}"):
        return HttpResponseRedirect(resolve_url(settings.LOGIN_REDIRECT_URL))

    if request.GET.get("get_template"):  # ?get_template=1
        header = ",".join(importer.required_fields + importer.supported_fields)
        filename = "{}_import_template.csv".format(importer.verbose_name.replace(" ", "_"))
        response = HttpResponse(header, content_type="application/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    file_form = None
    if request.method == "POST":
        if "form-TOTAL_FORMS" in request.POST:
            importer = importer_class(user, formset_data=request.POST)
            importer.save_all()
        else:
            # Every uploaded file are stored in a temp location as we removed
            # the MemoryFileUploadHandler in the FILE_UPLOAD_HANDLERS settings.
            # We do not keep track of this location once the file has been
            # processed.
            file_form = upload_form_class(request.POST, request.FILES)
            if file_form.is_valid():
                uploaded_file = request.FILES["file"]
                file_location = uploaded_file.temporary_file_path()
                importer = importer_class(user, file_location=file_location)
    else:
        file_form = upload_form_class()

    return render(
        request,
        "admin/object_import.html",
        {
            "file_form": file_form,
            "importer": importer,
            "add_to_product_form": importer.get_add_to_product_form(request),
        },
    )


class ComponentRelatedFieldImportMixin:
    """Regroup common methods used to match a FK field to a Component instance."""

    @staticmethod
    def get_name_version(str_value):
        try:
            return extract_name_version(str_value)
        except SyntaxError:
            raise forms.ValidationError('Invalid format. Expected format: "<name>:<version>".')

    def _clean_name_version_related_field(self, field_name, model_class, queryset=None):
        cleaned_data = self.cleaned_data.get(field_name)
        if not cleaned_data:
            return

        field = self.fields[field_name]
        name, version = self.get_name_version(cleaned_data)

        if not queryset:
            queryset = model_class.objects.scope(self.dataspace)

        try:
            cleaned_data = queryset.get(name=name, version=version)
        except ObjectDoesNotExist:
            raise forms.ValidationError(f"Could not find the {model_class._meta.verbose_name}.")
        else:
            field.value_for_display = cleaned_data.get_admin_link(target="_blank")

        return cleaned_data
