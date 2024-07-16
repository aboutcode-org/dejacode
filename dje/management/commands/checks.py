#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import Counter
from itertools import groupby

from django.core.checks import Error
from django.core.checks import Info
from django.core.checks import Warning
from django.core.checks import register
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db.models.functions import Length

from component_catalog.license_expression_dje import build_licensing
from component_catalog.license_expression_dje import normalize_and_validate_expression
from component_catalog.license_expression_dje import parse_expression
from component_catalog.models import Component
from component_catalog.models import Package
from component_catalog.models import Subcomponent
from license_library.models import License
from organization.models import Owner
from product_portfolio.models import Product
from product_portfolio.models import ProductComponent
from reporting.models import ColumnTemplate
from reporting.models import Query


# Case-insensitive grouping on the name field value.
def lowercase_name(instance):
    return instance.name.lower()


@register("data")
def check_for_leading_or_trailing_spaces_in_name(app_configs, **kwargs):
    """
    Resolution:
    for obj in qs:
        obj.name = obj.name.strip()  # Clean whitespace on both sides
        obj.save()
    """
    errors = []

    dataspace = app_configs["dataspace"]
    for model_class in [Owner, License, Component, Product]:
        qs = model_class.objects.scope(dataspace).filter(
            Q(name__startswith=" ") | Q(name__endswith=" ")
        )

        for obj in qs:
            errors.append(
                Error(
                    "Leading or trailing space in name",
                    hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                    obj=obj,
                )
            )

    return errors


@register("data")
def check_for_leading_or_trailing_spaces_in_version(app_configs, **kwargs):
    """
    Resolution:
    for obj in qs:
        obj.version = obj.version.strip()  # Clean whitespace on both sides
        obj.save()
    """
    errors = []

    dataspace = app_configs["dataspace"]
    for model_class in [Component, Product]:
        qs = model_class.objects.scope(dataspace).filter(
            Q(version__startswith=" ") | Q(version__endswith=" ")
        )

        for obj in qs:
            errors.append(
                Error(
                    "Leading or trailing space in version",
                    hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                    obj=obj,
                )
            )

    return errors


@register("data")
def check_for_double_spaces(app_configs, **kwargs):
    """
    Resolution:
    for obj in qs:
        obj.name = obj.name.replace('  ', ' ')
        obj.save()
    """
    errors = []

    dataspace = app_configs["dataspace"]
    for model_class in [Owner, License, Component]:
        qs = model_class.objects.scope(dataspace).filter(name__contains="  ")

        for obj in qs:
            errors.append(
                Error(
                    "Contains double whitespaces",
                    hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                    obj=obj,
                )
            )

    return errors


@register("data")
def check_for_primary_language_unknown(app_configs, **kwargs):
    """Resolution: Manual"""
    from component_catalog.programming_languages import PROGRAMMING_LANGUAGES

    errors = []
    model_class = Component
    dataspace = app_configs["dataspace"]

    qs = (
        model_class.objects.scope(dataspace)
        .exclude(primary_language__in=PROGRAMMING_LANGUAGES)
        .exclude(primary_language__exact="")
    )

    for obj in qs:
        errors.append(
            Error(
                "Primary language unknown",
                hint='<{} pk={}> "{}"'.format(model_class.__name__, obj.pk, obj.primary_language),
                obj=obj,
            )
        )

    return errors


@register("data")
def check_for_too_long_name(app_configs, **kwargs):
    errors = []
    dataspace = app_configs["dataspace"]

    for model_class in [Component]:
        qs = (
            model_class.objects.scope(dataspace)
            .annotate(name_len=Length("name"))
            .filter(name_len__gt=50)
        )

        for obj in qs:
            errors.append(
                Error(
                    "Name is longer than 70 characters",
                    hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                    obj=obj,
                )
            )

    return errors


@register("data")
def check_for_component_without_assigned_license(app_configs, **kwargs):
    """Resolution: Manual"""
    errors = []
    model_class = Component
    dataspace = app_configs["dataspace"]

    qs = model_class.objects.scope(dataspace).filter(componentassignedlicense__isnull=True)

    for obj in qs:
        errors.append(
            Warning(
                "No license assigned",
                hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                obj=obj,
            )
        )

    return errors


# Available in changelist: /admin/component_catalog/package/?component__isnull=0
@register("deprecated")
def check_for_orphan_package(app_configs, **kwargs):
    """Check for packages not assigned to any Component."""
    errors = []
    model_class = Package
    dataspace = app_configs["dataspace"]

    qs = model_class.objects.scope(dataspace).filter(componentassignedpackage__isnull=True)

    for obj in qs:
        errors.append(
            Warning(
                "No component assigned",
                hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                obj=obj,
            )
        )

    return errors


# Available in changelist: /admin/component_catalog/package/?url=
@register("deprecated")
def check_for_packages_with_no_url(app_configs, **kwargs):
    """
    Check for packages with an empty 'download_url' field.
    There may be some use-case where an empty URL is OK, like for internal
    private Components.
    """
    errors = []
    model_class = Package
    dataspace = app_configs["dataspace"]

    qs = model_class.objects.scope(dataspace).filter(download_url__iexact="")

    for obj in qs:
        errors.append(
            Warning(
                "No URL set",
                hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                obj=obj,
            )
        )

    return errors


# Turned off.
# @register('data')
def check_for_packages_with_double_slash(app_configs, **kwargs):
    """Check for packages with a double slash "//" in the URL path."""
    errors = []
    model_class = Package
    dataspace = app_configs["dataspace"]

    qs = model_class.objects.scope(dataspace).filter(download_url__iregex=r"^.*://.*//")

    for obj in qs:
        errors.append(
            Warning(
                'Double slash "//" in URL',
                hint="<{} pk={}>".format(model_class.__name__, obj.pk),
                obj=obj,
            )
        )

    return errors


# @register('data')
def check_for_packages_with_duplicated_url(app_configs, **kwargs):
    """Check for packages with duplicated URL."""
    errors = []
    model_class = Package
    dataspace = app_configs["dataspace"]

    qs = model_class.objects.scope(dataspace)
    url_list = qs.values_list("download_url", flat=True).order_by("download_url")
    duplicates = [x for x, y in Counter(url_list).items() if y > 1]

    errors.append(
        Warning(
            "Duplicated Package URLs",
            hint="\n\t".join(duplicates),
        )
    )

    return errors


@register("data")
def check_for_case_inconsistencies(app_configs, **kwargs):
    """Resolution: Manual"""
    errors = []
    dataspace = app_configs["dataspace"]

    for model_class in [Owner, License, Component]:
        qs = model_class.objects.scope(dataspace)

        # The iterable needs to already be sorted on the same key function.
        for _, group in groupby(sorted(qs, key=lowercase_name), lowercase_name):
            inconsistencies = set(instance.name for instance in group)
            # Checking for inconsistencies within each group
            if len(inconsistencies) > 1:
                errors.append(
                    Info(
                        "Case inconsistencies",
                        hint='<{}> "{}"'.format(model_class.__name__, str(list(inconsistencies))),
                    )
                )

    return errors


@register("data")
def check_for_field_validation_issues(app_configs, **kwargs):
    """Resolution: Manual"""
    errors = []
    dataspace = app_configs["dataspace"]

    for model_class in [Owner, License, Component, Package]:
        qs = model_class.objects.scope(dataspace)

        for field in model_class._meta.get_fields():
            if not hasattr(field, "validators"):
                continue
            for validator in field.validators:
                for instance in qs:
                    field_value = getattr(instance, field.name, None)
                    if not field_value:
                        continue
                    try:
                        validator(field_value)
                    except ValidationError:
                        errors.append(
                            Warning(
                                "Field validation issue",
                                hint="<{} pk={} field={} value={}>".format(
                                    model_class.__name__, instance.pk, field.name, field_value
                                ),
                                obj=instance,
                            )
                        )

    return errors


@register("expression")
def check_for_license_expression_choice_inconsistencies(app_configs, **kwargs):
    """
    Check that the license expression of a product component is made of
    licenses defined as the component level.

    Resolution: Manual
    """
    errors = []
    dataspace = app_configs.get("dataspace")

    for model_class in [ProductComponent, Subcomponent]:
        qs = model_class.objects.exclude(license_expression__exact="")
        qs = qs.prefetch_related("licenses__dataspace")
        if dataspace:
            qs = qs.scope(dataspace)

        for obj in qs:
            component = obj.component if model_class is ProductComponent else obj.child
            if not component:  # ProductComponent.component == None
                continue

            try:
                licenses = component.licenses.for_expression()
                normalize_and_validate_expression(
                    obj.license_expression, licenses, validate_known=True, include_available=True
                )
            except ValidationError as e:
                errors.append(
                    Error(
                        "License expression error. {}".format(str(e).replace("<br>", " -- ")),
                        hint="<{} dataspace={} pk={}>".format(
                            model_class.__name__, obj.dataspace, obj.pk
                        ),
                        obj=obj,
                    )
                )

    return errors


@register("expression")
def check_for_license_expression_validity(app_configs, **kwargs):
    """
    Check that the license expressions are syntactically correct.
    Does not validate that the license synbols/keys exist.

    Resolution: Manual
    """
    licensing = build_licensing()
    dataspace = app_configs.get("dataspace")

    errors = []

    for model_class in [Component, Product, ProductComponent, Subcomponent]:
        qs = model_class.objects.exclude(license_expression__exact="")
        if dataspace:
            qs = qs.scope(dataspace)

        for obj in qs:
            try:
                parse_expression(obj.license_expression, licenses=licensing, validate_known=False)
            except Exception as e:
                errors.append(
                    Error(
                        "License expression error. {}".format(str(e).replace("<br>", " -- ")),
                        hint="<{} dataspace={} pk={}>".format(
                            model_class.__name__, obj.dataspace, obj.pk
                        ),
                        obj=obj,
                    )
                )

    return errors


# Turned off as it takes too much time to run on a real set of data.
# Turn on manually when needed.
# @register('data')
def check_for_fields_value_inconsistencies(app_configs, **kwargs):
    """Resolution: Manual"""
    errors = []
    model_class = Component
    dataspace = app_configs["dataspace"]

    fields_to_check = (
        "owner",
        "type",
        "primary_language",
        "homepage_url",
        # Callables on the model
        # ('Licenses', 'licenses'),
    )

    qs = model_class.objects.scope(dataspace)

    for _, group in groupby(sorted(qs, key=lowercase_name), lowercase_name):
        issues = []
        # Turns the generator into a list as we need to iterate several times.
        group_list = list(group)

        for field_name in fields_to_check:
            if isinstance(field_name, tuple):
                field_name, method = field_name
                inconsistencies = {str(getattr(instance, method)()) for instance in group_list}
            else:
                inconsistencies = {getattr(instance, field_name) for instance in group_list}

            if len(inconsistencies) > 1:
                msg = f"{field_name}: {list(inconsistencies)}"
                issues.append(msg)

        if issues:
            component_pk = group_list[0].pk
            errors.append(
                Info(
                    "Case inconsistencies",
                    hint='<{} pk={}> "{}"'.format(
                        model_class.__name__, component_pk, "\n".join(issues)
                    ),
                )
            )

    return errors


@register("reporting")
def check_for_broken_reporting_query(app_configs, **kwargs):
    errors = []
    model_class = Query
    qs = model_class.objects.all()
    dataspace = app_configs.get("dataspace")

    if dataspace:
        qs = qs.scope(dataspace)

    for obj in qs:
        if not obj.is_valid():
            errors.append(
                Error(
                    "Broken reporting Query",
                    hint="<{} dataspace={} pk={}>".format(
                        model_class.__name__, obj.dataspace, obj.pk
                    ),
                    obj=obj,
                )
            )

    return errors


@register("reporting")
def check_for_reporting_query_with_no_filters(app_configs, **kwargs):
    errors = []
    model_class = Query
    qs = Query.objects.filter(filters__isnull=True)
    dataspace = app_configs.get("dataspace")

    if dataspace:
        qs = qs.scope(dataspace)

    for obj in qs:
        errors.append(
            Warning(
                "No Query filters set",
                hint="<{} dataspace={} pk={}>".format(model_class.__name__, obj.dataspace, obj.pk),
                obj=obj,
            )
        )

    return errors


@register("reporting")
def check_for_broken_reporting_column_template(app_configs, **kwargs):
    errors = []
    model_class = ColumnTemplate
    qs = ColumnTemplate.objects.all()
    dataspace = app_configs.get("dataspace")

    if dataspace:
        qs = qs.scope(dataspace)

    for obj in qs:
        if not obj.is_valid():
            errors.append(
                Error(
                    "",
                    hint="<{} dataspace={} pk={}>".format(
                        model_class.__name__, obj.dataspace, obj.pk
                    ),
                    obj=obj,
                )
            )

    return errors
