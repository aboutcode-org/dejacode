#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import functools

from django import forms
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.fields.related import ForeignKey
from django.db.models.fields.related import ManyToManyField
from django.db.models.fields.related import ManyToOneRel
from django.forms import formsets
from django.forms.models import BaseInlineFormSet

from component_catalog.models import Component
from component_catalog.models import ComponentAssignedLicense
from component_catalog.models import ComponentAssignedPackage
from component_catalog.models import ComponentKeyword
from component_catalog.models import ComponentStatus
from component_catalog.models import ComponentType
from component_catalog.models import Package
from component_catalog.models import PackageAssignedLicense
from component_catalog.models import Subcomponent
from component_catalog.models import SubcomponentAssignedLicense
from dje.forms import DataspacedAdminForm
from dje.mass_update import DejacodeMassUpdateForm
from dje.models import DejacodeUser
from dje.models import ExternalReference
from dje.models import ExternalSource
from license_library.models import License
from license_library.models import LicenseAnnotation
from license_library.models import LicenseAssignedTag
from license_library.models import LicenseCategory
from license_library.models import LicenseChoice
from license_library.models import LicenseProfile
from license_library.models import LicenseProfileAssignedTag
from license_library.models import LicenseStatus
from license_library.models import LicenseStyle
from license_library.models import LicenseTag
from license_library.models import LicenseTagGroup
from license_library.models import LicenseTagGroupAssignedTag
from license_library.models import validate_slug_plus
from organization.models import Owner
from organization.models import Subowner
from policy.models import UsagePolicy
from product_portfolio.models import CodebaseResource
from product_portfolio.models import CodebaseResourceUsage
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from product_portfolio.models import ProductDependency
from product_portfolio.models import ProductInventoryItem
from product_portfolio.models import ProductItemPurpose
from product_portfolio.models import ProductPackage
from product_portfolio.models import ProductRelationStatus
from product_portfolio.models import ProductStatus
from reporting.fields import BooleanSelect
from reporting.fields import DateFieldFilterSelect
from reporting.fields import NullBooleanSelect
from reporting.introspection import get_model_label
from reporting.introspection import introspector
from reporting.models import ISNULL_LOOKUP_CHOICES
from reporting.models import LICENSE_TAG_PREFIX
from reporting.models import ColumnTemplate
from reporting.models import Filter
from reporting.models import OrderField
from reporting.models import Query
from reporting.models import Report
from reporting.models import get_reportable_models
from workflow.models import Request
from workflow.models import RequestTemplate

# The list of models that are allowed to be referenced by ``Filter`` and
# ``ColumnTemplateAssignedField``
MODEL_WHITELIST = [
    Component,
    ComponentAssignedPackage,
    ComponentAssignedLicense,
    ComponentKeyword,
    ComponentStatus,
    ComponentType,
    Package,
    PackageAssignedLicense,
    License,
    LicenseAnnotation,
    LicenseAssignedTag,
    LicenseCategory,
    LicenseChoice,
    LicenseProfile,
    LicenseProfileAssignedTag,
    LicenseStatus,
    LicenseStyle,
    LicenseTag,
    LicenseTagGroup,
    LicenseTagGroupAssignedTag,
    Owner,
    Subcomponent,
    SubcomponentAssignedLicense,
    Subowner,
    Request,
    RequestTemplate,
    UsagePolicy,
    Product,
    ProductComponent,
    ProductPackage,
    ProductStatus,
    ProductRelationStatus,
    ProductDependency,
    ProductInventoryItem,
    ProductItemPurpose,
    ExternalReference,
    ExternalSource,
    DejacodeUser,
    CodebaseResource,
    CodebaseResourceUsage,
]

FIELDS_WHITELIST = {
    # WARNING: Do not expose more User fields, for security and privacy reasons.
    DejacodeUser: ["username"],
}


@functools.lru_cache(maxsize=None)
def get_model_data_for_query():
    """
    Return a dict-based data structure of the models and their fields available
    in the Query system.
    """
    model_classes = introspector.get_related_models(get_reportable_models())
    return introspector.get_model_data(
        model_classes=model_classes,
        model_whitelist=MODEL_WHITELIST,
        get_m2m=True,
        # Do not display the related many-to-many fields because there is no
        # need to query against them
        get_related_m2m=False,
        get_related=True,
        get_generic_relation=True,
        field_whitelist=FIELDS_WHITELIST,
    )


@functools.lru_cache(maxsize=None)
def get_model_data_for_order_field():
    """
    Return a dict-based data structure of the models and their fields available
    in the OrderField system.
    """
    model_classes = get_reportable_models()
    return introspector.get_model_data(
        model_classes=model_classes,
        model_whitelist=MODEL_WHITELIST,
        omit_foreign_key_fields=False,
        get_m2m=False,
        get_related_m2m=False,
        get_related=False,
        get_generic_relation=False,
        field_whitelist=FIELDS_WHITELIST,
    )


def get_model_data_for_column_template(dataspace=None):
    """
    Return a dict-based data structure of the models and their fields available
    in the ColumnTemplate system.
    An optional dataspace can be given, the LicenseTag will not be included
    if the dataspace is not specified.
    """
    model_classes = introspector.get_related_models(get_reportable_models())
    model_data = introspector.get_model_data(
        model_classes=model_classes,
        model_whitelist=MODEL_WHITELIST,
        get_m2m=True,
        # Do not display the related many-to-many fields because they don't
        # make sense as selectable columns
        get_related_m2m=False,
        get_related=True,
        get_generic_relation=True,
        field_whitelist=FIELDS_WHITELIST,
    )

    # Extend model_data with some properties
    extended_model_data = {
        "component_catalog:component": {
            "Properties": [
                "urn",
                "details_url",
                "concluded_license_expression_spdx",
                "declared_license_expression_spdx",
                "other_license_expression_spdx",
                "primary_license",
                "attribution_required",
                "redistribution_required",
                "change_tracking_required",
                "where_used",
            ],
        },
        "component_catalog:package": {
            "Properties": [
                "identifier",
                "urn",
                "details_url",
                "concluded_license_expression_spdx",
                "declared_license_expression_spdx",
                "other_license_expression_spdx",
                "primary_license",
                "attribution_required",
                "redistribution_required",
                "change_tracking_required",
                "package_url",
                "short_package_url",
                "where_used",
                "inferred_url",
            ],
        },
        "license_library:license": {
            "Properties": [
                "urn",
                "details_url",
                "spdx_url",
                "attribution_required",
                "redistribution_required",
                "change_tracking_required",
                "where_used",
                "language_code",
            ],
        },
        "organization:owner": {
            "Properties": [
                "urn",
            ],
        },
        "workflow:request": {
            "Properties": [
                "serialized_data_html",
                "details_url",
                "content_object",
            ],
        },
    }

    if dataspace:
        qs = LicenseTag.objects.scope(dataspace)
        extended_model_data["license_library:license"].update(
            {
                "License Tags": [f"{LICENSE_TAG_PREFIX}{tag.label}" for tag in qs],
            }
        )

    for model in get_reportable_models():
        model_label = get_model_label(model)

        if model_label not in model_data:
            continue

        fields = model_data[model_label]["fields"]
        grouped_fields = model_data[model_label]["grouped_fields"]
        meta = model_data[model_label]["meta"]
        extra_groups = []

        for group, labels in extended_model_data.get(model_label, {}).items():
            for label in labels:
                fields.append(label)
                meta[label] = {}
                extra_groups.append({"group": group, "label": label, "value": label})

        grouped_fields.extend(extra_groups)

    return model_data


class CleanContentTypeFormMixin:
    """
    Prevent from changing the content_type of the instance if already assigned
    to at least 1 Report.
    """

    def clean_content_type(self):
        content_type = self.cleaned_data.get("content_type")

        # Editing and at least 1 Report object using this instance
        if self.instance.pk and self.instance.report_set.exists():
            if self.instance.content_type != content_type:
                raise forms.ValidationError(
                    "The content type cannot be modified since this object "
                    "is assigned to a least one Report instance."
                )

        return content_type


class QueryForm(CleanContentTypeFormMixin, DataspacedAdminForm):
    class Meta:
        model = Query
        fields = "__all__"


class FilterForm(forms.ModelForm):
    class Meta:
        model = Filter
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """
        Disables the auto-strip on the value field.
        Filters may require to match on leading and trailing spaces.
        """
        super().__init__(*args, **kwargs)
        self.fields["value"].strip = False

    @staticmethod
    def validate_the_field_name_value(cleaned_data):
        field_name = cleaned_data.get("field_name")
        query = cleaned_data.get("query")

        if field_name and query and query.content_type_id:
            introspector.validate_field_traversal_of_model_data(
                fields=field_name.split("__"),
                starting_model=query.content_type.model_class(),
                model_data=get_model_data_for_query(),
            )

    @staticmethod
    def validate_lookup_type(cleaned_data):
        """
        Validate the lookup type against the field type.
        Boolean fields do not support iexact for example.
        """
        lookup = cleaned_data.get("lookup")
        field_name = cleaned_data.get("field_name")
        query = cleaned_data.get("query")
        value = cleaned_data.get("value")

        # We use the content_type_id to check is the query form is valid on
        # addition
        if not all([lookup, field_name, query, query.content_type_id]):
            return

        model_class = query.content_type.model_class()
        field_instance = introspector.get_model_field_via_field_traversal(
            fields=field_name.split("__"),
            starting_model=model_class,
            model_data=get_model_data_for_query(),
        )

        if isinstance(field_instance, (models.BooleanField)):
            if lookup == "iexact":
                raise ValidationError('Lookup "iexact" on Boolean field is not supported')

        if lookup == "descendant":
            if not getattr(model_class, "get_descendant_ids", None):
                raise ValidationError(
                    'Lookup "descendant" only supported on models with hierarchy.'
                )
            if field_name != "id":
                raise ValidationError('Lookup "descendant" only supported on "id" field.')

        elif lookup == "product_descendant":
            if model_class.__name__ != "Component":
                raise ValidationError(
                    'Lookup "product_descendant" only supported on Component object type.'
                )

        elif lookup == "isnull":
            not_valid = all(
                [
                    not isinstance(
                        field_instance, (ManyToOneRel, ManyToManyField, GenericRelation)
                    ),
                    not getattr(field_instance, "null", False),
                ]
            )

            if not_valid:
                raise ValidationError(
                    f'Lookup "{lookup}" is only supported on nullable fields. '
                    f'A "isempty" lookup is available for non-nullable fields'
                )

        elif lookup == "isempty":
            if isinstance(field_instance, (ForeignKey, ManyToOneRel)):
                raise ValidationError(f'Lookup "{lookup}" is not supported on related fields.')

            if not getattr(field_instance, "blank", False):
                raise ValidationError(f'Lookup "{lookup}" is only supported on blank-able fields.')

        if lookup in ["isnull", "isempty"] and value and value not in ISNULL_LOOKUP_CHOICES:
            raise ValidationError(
                f'"{value}" is not a valid value for the {lookup} lookup. Use True or False'
            )

    def clean(self):
        cleaned_data = super().clean()

        self.validate_the_field_name_value(cleaned_data)
        self.validate_lookup_type(cleaned_data)

        return cleaned_data


class RuntimeFilterBaseFormSet(formsets.BaseFormSet):
    def __init__(self, request, filters, *args, **kwargs):
        self.request = request
        self.filters = filters
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs["request"] = self.request
        kwargs["filter_"] = self.filters[i]
        return super()._construct_form(i, **kwargs)

    @classmethod
    def get_default_prefix(cls):
        return "runtime_filters"


class RuntimeFilterForm(forms.Form):
    def __init__(self, request, filter_, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.request = request
        self.filter = filter_
        self.set_up_value_field()

    def set_up_value_field(self):
        model_data = get_model_data_for_query()
        fields = self.filter.field_name.split("__")
        field = introspector.get_model_field_via_field_traversal(
            fields=fields,
            starting_model=self.filter.query.content_type.model_class(),
            model_data=model_data,
        )

        if not field:
            return

        if isinstance(field, models.CharField) and self.filter.lookup == "in":
            placeholder = "['name-1', 'name-2', ...]"
        elif self.filter.lookup == "year":
            placeholder = "YYYY"
        elif self.filter.lookup == "month":
            placeholder = "MM"
        elif self.filter.lookup == "day":
            placeholder = "DD"
        elif isinstance(field, models.DateField):
            placeholder = "YYYY-MM-DD"
        elif isinstance(field, models.DateTimeField):
            placeholder = "YYYY-MM-DD HH:MM:SS"
        elif validate_slug_plus in getattr(field, "validators", []):
            placeholder = 'Letters, numbers, underscores or hyphens; e.g. "apache-2.0"'
        elif self.filter.lookup == "descendant":
            placeholder = "ID (integer) of the top level instance"
        else:
            # The description of CharField requires the max_length string value.
            description = getattr(field, "description", "")
            max_length = getattr(field, "max_length", "")
            placeholder = description % {"max_length": max_length}

        widget_kwargs = {
            "attrs": {
                "placeholder": placeholder,
                "class": "form-control input-block-level",
            }
        }

        widget_class = forms.TextInput
        if isinstance(field, models.TextField) or self.filter.lookup == "in":
            widget_class = forms.Textarea
            widget_kwargs["attrs"]["rows"] = "4"
        elif isinstance(field, models.BooleanField):
            widget_class = NullBooleanSelect if field.null else BooleanSelect
        elif isinstance(field, models.DateTimeField):
            widget_class = DateFieldFilterSelect
        elif self.filter.lookup in ["isnull", "isempty"]:
            widget_class = BooleanSelect
        elif field.choices:
            widget_class = forms.Select
            widget_kwargs["choices"] = [("", "All")] + list(field.choices)

        self.fields["value"] = forms.CharField(required=False, widget=widget_class(**widget_kwargs))


class OrderFieldForm(forms.ModelForm):
    class Meta:
        model = OrderField
        fields = "__all__"

    @staticmethod
    def validate_the_field_name_value(cleaned_data):
        field_name = cleaned_data.get("field_name")
        query = cleaned_data.get("query")

        if field_name and query and query.content_type_id:
            model = query.content_type.model_class()
            model_label = get_model_label(model)
            model_data = get_model_data_for_order_field()
            field_names = model_data[model_label]["fields"]

            if field_name not in field_names:
                raise ValidationError(f"{field_name} is not a field of {model.__name__}")

    def clean(self):
        cleaned_data = super().clean()
        self.validate_the_field_name_value(cleaned_data)
        return cleaned_data


class ColumnTemplateForm(CleanContentTypeFormMixin, DataspacedAdminForm):
    class Meta:
        model = ColumnTemplate
        fields = "__all__"


class ColumnTemplateAssignedFieldFormSet(BaseInlineFormSet):
    @staticmethod
    def validate_the_field_name(cleaned_data, dataspace):
        field_name = cleaned_data.get("field_name")
        column_template = cleaned_data.get("column_template")
        has_content_type = hasattr(column_template, "content_type")

        if field_name and column_template and has_content_type:
            introspector.validate_field_traversal_of_model_data(
                fields=field_name.split("__"),
                starting_model=column_template.content_type.model_class(),
                model_data=get_model_data_for_column_template(dataspace),
            )

    def clean(self):
        dataspace = self._request.user.dataspace
        for form in self.forms:
            try:
                self.validate_the_field_name(form.cleaned_data, dataspace)
            except ValidationError as e:
                form.add_error("field_name", e.message)
                raise


class ReportForm(DataspacedAdminForm):
    class Meta:
        model = Report
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        query = cleaned_data.get("query")
        column_template = cleaned_data.get("column_template")

        if query and column_template:
            # Only do something if both fields are valid so far.
            if query.content_type != column_template.content_type:
                msg = "The query and column template must have matching object types."
                self.add_error("query", msg)
                self.add_error("column_template", msg)

                raise ValidationError(
                    "{} The query has an object type of {}. The column "
                    "template has an object type of {}.".format(
                        msg,
                        query.content_type.model_class()._meta.verbose_name,
                        column_template.content_type.model_class()._meta.verbose_name,
                    )
                )

        return cleaned_data


class ReportMassUpdateForm(DejacodeMassUpdateForm):
    class Meta:
        fields = [
            "group",
        ]
