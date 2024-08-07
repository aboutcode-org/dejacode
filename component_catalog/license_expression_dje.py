#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from collections import defaultdict
from itertools import chain

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.forms import widgets
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from boolean.boolean import PARSE_ERRORS
from license_expression import ExpressionError
from license_expression import LicenseSymbolLike
from license_expression import Licensing
from license_expression import ParseError

from dje.widgets import AwesompleteInputWidgetMixin
from license_library.models import License

licensing_cache = caches["licensing"]


def build_licensing(licenses=None):
    """
    Return a Licensing from `licenses`: either a License QuerySet or a
    pre-built Licensing object (which is returned as-is).
    """
    if isinstance(licenses, Licensing):
        return licenses
    return Licensing(licenses)


def fetch_licensing_for_dataspace(dataspace, license_keys=None):
    """
    Return a Licensing object for the provided ``dataspace``.
    An optional list of ``license_keys`` can be provided to limit the licenses
    included in the Licensing object.
    """
    license_qs = License.objects.scope(dataspace).for_expression(license_keys)
    licensing = build_licensing(license_qs)
    return licensing


def get_dataspace_licensing(dataspace, license_keys=None):
    """
    Return a Licensing object for the provided ``dataspace``.
    The Licensing object is put in the cache for 5 minutes.
    Note that the cache is not used when ``license_keys`` are provided.
    """
    if license_keys is not None:
        # Bypass cache if license_keys is provided
        return fetch_licensing_for_dataspace(dataspace, license_keys)

    cache_key = str({dataspace.name})
    # First look in the cache for an existing Licensing for this Dataspace
    licensing = licensing_cache.get(cache_key)

    if licensing is None:
        # If not cached, compute the value and cache it
        licensing = fetch_licensing_for_dataspace(dataspace, license_keys)
        licensing_cache.set(cache_key, licensing, timeout=600)  # 10 minutes

    return licensing


def parse_expression(
    expression, licenses=None, validate_known=True, validate_strict=False, simple=False
):
    """
    Return a parsed expression object given an expression string.
    Raise Exceptions on parsing errors

    Check and parse the expression license symbols against an optional
    `licenses` object that can be either a License QuerySet or a pre-
    built Licensing object.

    If `validate_known` is True, raise a ValidationError if a license
    symbol is unknown. Also include in exception message information
    about the available licenses.

    If `validate_strict` is True, raise a ValidationError if license
    symbol in a "WITH" exception expression is invalid e.g. in "a WITH
    b" either: "a" is an exception or "b" is not an exception.
    """
    licensing = build_licensing(licenses)
    return licensing.parse(
        expression, validate=validate_known, strict=validate_strict, simple=simple
    )


def get_license_objects(expression, licenses=None):
    """
    Return a list of unique License instances from an expression string.
    Raise Exceptions on parsing errors.

    Check and parse the expression license symbols against an optional
    `licenses` object that can be either a License QuerySet or a pre-
    built Licensing object.

    The expression is assumed to:
     - be composed only from license keys (and not from license names)
     - contain ONLY known license keys

    Furthermore, the validity of "WITH" expression is not checked
    (e.g. `validate_strict` is not used when parsing then expression).
    """
    licensing = build_licensing(licenses)
    # note: we use the simple tokenizer since we support only keys here.
    parsed = licensing.parse(expression, validate=False, strict=False, simple=True)
    symbols = licensing.license_symbols(parsed, unique=True, decompose=True)
    return [symbol.wrapped for symbol in symbols if isinstance(symbol, LicenseSymbolLike)]


def normalize_and_validate_expression(
    expression,
    licenses=None,
    validate_known=True,
    validate_strict=False,
    include_available=False,
    simple=False,
):
    """
    Return a normalized and validated license expression.
    Raise Django ValidationErrors exception on errors.

    If `validate_known` is True and `include_available` is True, the
    exception message will contain extra information listing available
    licenses when the expression uses an unknown license.

    See `parse_expression` for other arguments.
    """
    include_available = validate_known and include_available
    licensing = build_licensing(licenses)

    try:
        parsed = parse_expression(
            expression, licensing, validate_known, validate_strict, simple=simple
        )

    except ExpressionError as ee:
        msg = str(ee)
        if include_available:
            msg += available_licenses_message(licensing)
        raise ValidationError(format_html(msg), code="invalid")

    except ParseError as pe:
        msg = PARSE_ERRORS[pe.error_code]
        if pe.token_string:
            msg += ": " + pe.token_string
        if include_available:
            msg += available_licenses_message(licensing)
        raise ValidationError(format_html(msg), code="invalid")

    except (ValueError, TypeError) as ve:
        msg = "Invalid reference licenses data.\n" + str(ve)
        raise ValidationError(format_html(msg), code="invalid")

    except Exception as e:
        msg = "Invalid license expression.\n" + str(e)
        raise ValidationError(format_html(msg), code="invalid")

    # NOTE: we test for None because an expression cannot be resolved to
    # a boolean and a plain "if parsed" would attempt to resolve the
    # expression to a boolean.
    if parsed is not None:
        return parsed.render(template="{symbol.key}")


def clean_related_expression(expression, related_object):
    """
    Return a normalized license expression string validated against
    the list of known licenses in a related component/package.

    If the expression is empty, return the related component/package
    expression.

    Raise ValidationError exceptions on validation errors. These
    will contain the list of known licenses in the related component/package.
    """
    if not expression:
        # Using the license_expression from the related component/package as default value
        return related_object.license_expression

    licenses = related_object.licenses.for_expression()

    if related_object.has_license_choices:
        all_licenses = (
            License.objects.scope(related_object.dataspace)
            .exclude(id__in=licenses)
            .for_expression()
        )
        related_object_licenses = get_license_objects(
            related_object.license_choices_expression, all_licenses
        )
        licenses = list(licenses) + list(related_object_licenses)

    return normalize_and_validate_expression(
        expression, licenses, validate_known=True, include_available=True
    )


def available_licenses_message(licenses):
    """
    Return an HTML formatted message string representing a list of
    available licenses given a `licenses` License QuerySet or Licensing
    object.

    Return an empty strings if there are no available known symbols
    (such as when the license expression was not parsed against a list
    of known licenses)
    """
    licensing = build_licensing(licenses)

    if licensing.known_symbols:
        sorted_keys = ", ".join(sorted(licensing.known_symbols.keys()))
        return f"<br>Available licenses: {sorted_keys}"
    return ""


class LicenseExpressionWidget(
    AwesompleteInputWidgetMixin,
    widgets.Textarea,
):
    template_name = "django/forms/widgets/license_expression.html"


class LicenseExpressionFormMixin:
    """
    Form mixin to validate and clean license_expression fields.
    Can be mixed with ImportModelForm and DataspacedAdminForm classes.

    Support Product, Component, Package models, as well as related
    type ProductComponent, Subcomponent, ProductPackage models.

    Support for multiple license_expression fields though `expression_field_names`.

    The [Product|Component|Package].license_expression is validated
    against all the licenses from the current dataspace.

    The [ProductComponent|Subcomponent|ProductPackage].license_expression is validated
    against the licenses assigned to the related Component/Package.

    If the related Component/Package is not set yet, or has no value for `license_expression`,
    the expression is validated against all the licenses of the current dataspace.
    """

    relation_fk_field = None
    expression_field_names = ["license_expression"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for expression_field_name in self.expression_field_names:
            expression_field = self.fields.get(expression_field_name)
            if expression_field:
                widget = expression_field.widget
                final_attrs = widget.build_attrs(
                    base_attrs=widget.attrs,
                    extra_attrs=self.get_expression_widget_attrs(),
                )
                expression_field.widget = LicenseExpressionWidget(final_attrs)

    def get_expression_widget_attrs(self):
        if not self.relation_fk_field:
            return {}

        related_model = self._meta.model._meta.get_field(self.relation_fk_field).related_model
        related_model_name = related_model._meta.model_name
        # Those 2 attrs are required to properly setup the license_expression_builder
        attrs = {
            "related_model_name": related_model_name.title(),
            "related_api_url": reverse(f"api_v2:{related_model_name}-list"),
        }

        instance = getattr(self, "instance", None)
        related_object = getattr(instance, self.relation_fk_field, None)

        if instance and related_object:
            attrs["related_object_license_expression"] = related_object.license_expression
            if related_object.has_license_choices:
                attrs["license_choices_expression"] = related_object.license_choices_expression

        return attrs

    def clean_license_expression(self):
        """
        Return a normalized license expression string validated against
        a list of known licenses in the dataspace or a related component/package.

        If the expression is empty, return an empty string.

        Raise ValidationError exceptions on validation errors. These
        will not contain the list of known licenses (which is too big).
        """
        expression = self.cleaned_data.get("license_expression")

        related_object = None
        if self.relation_fk_field:
            related_object = self.cleaned_data.get(self.relation_fk_field)

        if related_object and related_object.license_expression:
            # for ProductComponent, Subcomponent, or ProductPackage
            return clean_related_expression(expression, related_object)
        # for Product, Component, ProductPackage, or ProductComponent without Component/Package FK,
        # or without `license_expression` value.
        return self.clean_expression_base(expression)

    def clean_declared_license_expression(self):
        expression = self.cleaned_data.get("declared_license_expression")
        return self.clean_expression_base(expression)

    def clean_other_license_expression(self):
        expression = self.cleaned_data.get("other_license_expression")
        return self.clean_expression_base(expression)

    def clean_expression_base(self, expression):
        """
        Return a normalized license expression string validated against
        the list of known licenses in the dataspace.

        If the expression is empty, return an empty string.

        Raise ValidationError exceptions on validation errors. These
        will not contain the list of known licenses (which is too big).
        """
        if not expression:
            return ""

        # ImportModelForm, DejacodeMassUpdateForm
        dataspace = getattr(self, "dataspace", None)

        if not dataspace:  # DataspacedAdminForm
            _object = getattr(self.request, "_object", None)

            # Instance Dataspace during edition, User Dataspace during addition
            if self.instance.pk:
                dataspace = self.instance.dataspace
            elif _object:
                # Editing in an alternate dataspace
                dataspace = _object.dataspace
            else:
                dataspace = self.request.user.dataspace

        licenses = License.objects.scope(dataspace).for_expression()
        normalized = normalize_and_validate_expression(
            expression, licenses, validate_known=True, include_available=False
        )
        return normalized or expression

    def extra_init(self, request, modeladmin):
        """
        Add the client_data required for the license expression builder
        in MassUpdateForm.
        """
        modeladmin.setup_license_builder(request)


def validate_expression_on_relations(component):
    """
    Return a mapping of errors as:
        {relation model class: [id of objects with errors,...]]}
    The errors are collected from the validation of the
    Component.license_expression against
     - the ProductComponent.license_expression
     - the Subcomponent.license_expression.
    """
    # NOTE: we do not need to resolve/validate the
    # Component.license_expression here: it is fetched from the DB and
    # has been stored as a valid expression made only of license keys.

    licensing = build_licensing(licenses=component.licenses.for_expression())
    relations = chain(component.related_parents.all(), component.productcomponents.all())

    errors = defaultdict(list)
    for relation in relations:
        if not relation.license_expression:
            continue

        try:
            # Ensure that the relation uses license keys defined on the related component.
            normalize_and_validate_expression(
                relation.license_expression, licensing, validate_known=True, include_available=False
            )
        except (ValidationError, ExpressionError, ParseError, TypeError):
            errors[relation.__class__].append(relation.id)

    return errors


def combine_license_expressions(expressions, simplify=False):
    """Return a license expression string combining multiple `expressions` with an AND."""
    expressions = [e for e in expressions if e and e.strip()]

    if len(expressions) == 1:
        return expressions[0]

    licensing = Licensing()
    # join the possible multiple detected license expression with an AND
    expression_objects = [licensing.parse(e, simple=True) for e in expressions]
    combined_expression_object = licensing.AND(*expression_objects)
    if simplify:
        combined_expression_object = combined_expression_object.simplify()
    return str(combined_expression_object)


def get_unique_license_keys(license_expression):
    licensing = build_licensing()
    parsed = licensing.parse(license_expression, validate=False, strict=False, simple=True)
    symbols = licensing.license_symbols(parsed, unique=True, decompose=True)
    return {symbol.key for symbol in symbols}


def get_formatted_expression(licensing, license_expression, show_policy, show_category=False):
    normalized = parse_expression(
        license_expression, licenses=licensing, validate_known=False, validate_strict=False
    )
    return normalized.render_as_readable(
        as_link=True, show_policy=show_policy, show_category=show_category
    )


def render_expression_as_html(expression, dataspace):
    """Return the ``expression`` as rendered HTML content."""
    show_policy = dataspace.show_usage_policy_in_user_views
    licensing = get_dataspace_licensing(dataspace)

    formatted_expression = get_formatted_expression(licensing, expression, show_policy)
    return format_html(
        '<span class="license-expression">{}</span>',
        mark_safe(formatted_expression),
    )


def get_expression_as_spdx(expression, dataspace):
    """Return an SPDX license expression built from the ``expression``."""
    licensing = get_dataspace_licensing(dataspace)
    parsed_expression = parse_expression(expression, licensing)
    return parsed_expression.render(template="{symbol.spdx_id}")
