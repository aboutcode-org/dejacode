#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
import re
import uuid
import zipfile
from collections import defaultdict
from contextlib import suppress
from itertools import groupby
from operator import attrgetter
from urllib.parse import urlparse

from django.contrib.auth import get_permission_codename
from django.contrib.contenttypes.models import ContentType
from django.core.validators import EMPTY_VALUES
from django.db import models
from django.db.models.options import Options
from django.http.request import HttpRequest
from django.urls import Resolver404
from django.urls import resolve
from django.urls import reverse
from django.utils.html import format_html
from django.utils.html import mark_safe
from django.utils.http import urlencode

import requests
from packageurl import PackageURL


def has_permission(model, user, action):
    """Return True is the `user` has the Permission for the given action of the model."""
    opts = model._meta
    codename = get_permission_codename(action, opts)
    return user.has_perm(f"{opts.app_label}.{codename}")


def get_help_text(opts, field_name):
    """
    Return a cleaned help_text for a given `field_name` using the Model
    Meta `opts`.
    Support both the model class or the meta class as input.
    """
    if not isinstance(opts, Options) and issubclass(opts, models.Model):
        opts = opts._meta
    return opts.get_field(field_name).help_text


def normalize_newlines_as_CR_plus_LF(text):
    """Normalize the line returns."""
    # Add \r to \n not preceded by a \r
    return re.sub(r"(?<!\r)\n", "\r\n", text)


def class_wrap(value, class_):
    """Return the given HTML wrapped in a div with the given class set."""
    return format_html('<div class="{}">{}</div>', class_, mark_safe(value))


def chunked(iterable, chunk_size):
    """
    Break an `iterable` into lists of `chunk_size` length.

    >>> list(chunked([1, 2, 3, 4, 5], 2))
    [[1, 2], [3, 4], [5]]
    >>> list(chunked([1, 2, 3, 4, 5], 3))
    [[1, 2, 3], [4, 5]]
    """
    for index in range(0, len(iterable), chunk_size):
        end = index + chunk_size
        yield iterable[index:end]


def chunked_queryset(queryset, chunk_size):
    """A generator function that yields chunks of data from the queryset."""
    for start in range(0, queryset.count(), chunk_size):
        yield list(queryset[start : start + chunk_size])


def extract_name_version(name_version_str):
    """
    Return a name and a version extracted from the following syntax: 'name:version'
    Note that colons `:` characters are allowed in the name but not in the version.
    """
    if not name_version_str or ":" not in name_version_str:
        raise SyntaxError

    name, _, version = name_version_str.rpartition(":")
    return name, version


def set_intermediate_explicit_m2m(instance, field, value):
    """
    Deal with m2m with explicit intermediate through relation.
    Using get_or_create to avoid create duplicate entries.
    Warning: This will fail if required fields (except the 2 FKs) are defined
    on the intermediary model.
    """
    for related_instance in value:
        field.remote_field.through.objects.get_or_create(
            **{
                field.m2m_field_name(): instance,
                field.m2m_reverse_field_name(): related_instance,
                "dataspace": instance.dataspace,
            }
        )


def queryset_to_changelist_href(queryset, params=None):
    """Return an URL to a changelist based on the given queryset."""
    if not queryset:
        return

    if params is None:
        params = {}

    opts = queryset.model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")

    ids = queryset.values_list("id", flat=True)
    params.update({"id__in": ",".join(str(id_) for id_ in ids)})

    return f"{url}?{urlencode(params)}"


CHANGELIST_LINK_TEMPLATE = (
    '<strong>See the <a href="{}" target="_blank">{} {}</a> in changelist</strong>'
)


def queryset_to_html_list(queryset, url_params, qs_limit=None):
    """
    Return an HTML <ul> of a given queryset.
    A link to access the full list, in a changelist, of results is added.
    A limit can be specified.
    """
    # Using len() to evaluate the qs rather than a count() that will cost an
    # extra query per row.
    count = len(queryset)
    if not count:
        return

    opts = queryset.model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
    href = f"{url}?{urlencode(url_params)}"
    changelist_link = format_html(CHANGELIST_LINK_TEMPLATE, href, count, opts.verbose_name_plural)

    list_items = [
        "<li>{}</li>".format(instance.get_admin_link(target="_blank"))
        for instance in queryset[:qs_limit]
    ]

    return format_html(
        '<ul class="with-disc">{}</ul>{}', mark_safe("".join(list_items)), changelist_link
    )


def get_uuids_list_sorted(dataspace_id, model_class):
    """
    Return a sorted list of uuids for a given `model_class`, limited to the
    given `dataspace_id`.
    """
    return (
        model_class.objects.scope_by_id(dataspace_id)
        .order_by("uuid")
        .values_list("uuid", flat=True)
    )


def uuid_reconciliation(reference, target, models, overrides=None):
    """
    For each model given in `models`, iterates over the objects of the `target`
    dataspace and look for a match, using the unique_filters_for method, in the
    `reference` dataspace.
    In case of a match, Set the uuid from the reference object on the target
    object. Each non-matched object is returned for manual reconciliation.
    """
    exceptions = {}
    if overrides is None:
        overrides = {}

    for model in models:
        model_name = model.__name__
        non_matched = []

        # Start with the overrides if any.
        current_overrides = overrides.get(model_name, [])
        for override in current_overrides:
            filters = override["filters"]
            filters.update({"dataspace": target})
            try:
                instance = model.objects.get(**filters)
            except model.DoesNotExist:
                pass
            else:
                if override.get("uuid", None):
                    instance.uuid = override["uuid"]
                    instance.save()

        reference_uuids = get_uuids_list_sorted(reference.id, model)
        # Exclude uuid that exist in the target, no need to reconciliate those.
        qs = model.objects.scope(target).exclude(uuid__in=reference_uuids)
        for obj in qs:
            # Looking for the same object in the reference dataspace
            # using the unique_together values.
            filters = obj.unique_filters_for(reference)
            try:
                matched_obj = model.objects.get(**filters)
            except model.DoesNotExist:
                del filters["dataspace"]
                non_matched.append({"filters": filters, "uuid": ""})
            else:
                obj.uuid = matched_obj.uuid
                obj.save()

        if non_matched:
            exceptions[model_name] = non_matched

    return exceptions


def get_object_compare_diff(source_object, target_object, excluded=None):
    """
    Build a list of field that have a diff.
    Many2Many fields are supported and compared using the UUID.
    Dataspace security is not enforced here and need to be handled on a higher level.
    """
    from dje.models import Dataspace
    from dje.models import DejacodeUser

    if not excluded:
        excluded = []

    compare_diff = {}
    compare_diff_m2m = {}

    for field in target_object._meta.fields:
        skip_conditions = [
            field.name in excluded,
            isinstance(field, models.ManyToManyField),
            isinstance(field, models.AutoField),
            getattr(field, "auto_now_add", False),
            getattr(field, "auto_now", False),
        ]

        if isinstance(field, models.ForeignKey):
            skip_conditions.extend(
                [
                    issubclass(field.related_model, ContentType),
                    issubclass(field.related_model, Dataspace),
                    issubclass(field.related_model, DejacodeUser),
                ]
            )

        if any(skip_conditions):
            continue

        source_value = getattr(source_object, field.name)
        target_value = getattr(target_object, field.name)

        # In FK case we use the UUID to compare rather than the value
        if isinstance(field, models.ForeignKey):
            if bool(source_value) != bool(target_value):  # XOR
                compare_diff[field] = [source_value, target_value]
            elif source_value and target_value:
                if source_value.uuid != target_value.uuid:
                    compare_diff[field] = [source_value, target_value]

        elif source_value != target_value:
            if field.choices:
                source_value = source_object._get_FIELD_display(field)
                target_value = target_object._get_FIELD_display(field)
            compare_diff[field] = [source_value, target_value]

    for field in target_object._meta.many_to_many:
        source_values = getattr(source_object, field.name).all()
        target_values = getattr(target_object, field.name).all()
        source_uuids = sorted([obj.uuid for obj in source_values])
        target_uuids = sorted([obj.uuid for obj in target_values])
        if source_uuids != target_uuids:
            compare_diff_m2m[field] = [source_values, target_values]

    return compare_diff, compare_diff_m2m


def get_duplicates(queryset, field_name, function=None):
    """
    Return a list of duplicate entries in the given `queryset` using
    the `field_name` values.

    A database `function` can optionally be apply to each items before looking
    for duplicates.
    See available function at:
        - https://docs.djangoproject.com/en/dev/ref/models/database-functions/

    >>> from django.db.models.functions import Lower
    >>> from dje.utils import get_duplicates
    >>> from organization.models import Owner
    >>> queryset = Owner.objects.scope_by_name('nexB')
    >>> get_duplicates(queryset, 'name', Lower)
    """
    from collections import Counter

    func_field_name = None
    if function:
        func_field_name = f"{function.__name__.lower()}_{field_name}"
        queryset = queryset.annotate(**{func_field_name: function(field_name)})

    values_list = queryset.values_list(func_field_name or field_name, flat=True)
    return [elem for elem, count in Counter(values_list).items() if count > 1]


def get_model_class_from_path(path):
    """
    Return the model_class from a given URL path.
    "/admin/license_library/license/copy/" path will return the `License` model class.
    """
    from django.apps import apps

    namespace, app_name, model, action = path.strip("/").split("/")
    return apps.get_model(app_name, model)


def merge_relations(original, duplicate):
    """Move `original` object references (ManyToOneRel, GenericRelation) from `duplicate`."""
    if original.__class__ != duplicate.__class__ or original.dataspace != duplicate.dataspace:
        raise AssertionError

    for f in original._meta.get_fields():
        if f.one_to_many and f.auto_created:
            getattr(duplicate, f.get_accessor_name()).update(**{f.field.name: original})
        elif f.__class__.__name__ == "GenericRelation":
            getattr(duplicate, f.attname).update(**{f.object_id_field_name: original.id})


def get_preserved_filters(request, model, parameter_name="_list_filters"):
    """
    Return the preserved filters querystring.
    Forked from django.contrib.admin.options.ModelAdmin
    """
    match = request.resolver_match

    if match:
        opts = model._meta
        current_url = f"{match.app_name}:{match.url_name}"
        list_url = f"{opts.app_label}:{opts.model_name}_list"
        if current_url == list_url:  # Craft the filter from URL
            preserved_filters = request.GET.urlencode()
        else:  # Load the filter from the request
            preserved_filters = request.GET.get(parameter_name)

        if preserved_filters:
            return urlencode({parameter_name: preserved_filters})
    return ""


def group_by(queryset, field_name, values=None, count_on=None, distinct=False):
    from django.db.models import Count

    values = values or [field_name]
    count_on = count_on or field_name

    return queryset.values(*values).order_by().annotate(count=Count(count_on, distinct=distinct))


def group_by_simple(queryset, field_name):
    """Return a dict of `queryset` instances grouped by the given `field_name`."""
    # Not using a dict comprehension to support QuerySet with no ordering
    # through `.order_by(field_name)`.
    grouped = defaultdict(list)

    for field_value, group in groupby(queryset, attrgetter(field_name)):
        grouped[field_value].extend(list(group))

    return dict(grouped)


def construct_changes_details_message(changes_details):
    msg = []
    header = '\n\n\nChanges details for {model_class} "{instance}"'
    change_line = "\n\n* {field}\nOld value: {old}\nNew value: {new}"

    for instance, data in changes_details.items():
        msg.append(header.format(model_class=instance.__class__.__name__, instance=instance))
        for field, old, new in data:
            msg.append(change_line.format(field=field, old=old, new=new))
    return "".join(msg)


def version_sort_key(item):
    """
    Replace the '.' by '~' that comes at the end of the ASCII table.
    https://natsort.readthedocs.io/en/master/examples.html
    """
    return item.replace(".", "~") + "z"


def group_by_name_version(object_list):
    """
    Group by ``name`` so that we can collapse multiple versions of an
    object into one row in the table.

    Sort by ``version`` within each group, using a natural sort,
    reversed so that the highest version number comes first.
    """
    from natsort import natsorted

    return [
        natsorted(group, key=lambda x: version_sort_key(x.version), reverse=True)
        for key, group in groupby(object_list, key=attrgetter("name"))
    ]


def pop_from_get_request(request, key):
    if not isinstance(request, HttpRequest):
        raise AssertionError("`request` argument is not a HttpRequest instance")

    if key not in request.GET:
        return

    request.GET._mutable = True
    value = request.GET.pop(key)
    request.GET_mutable = False

    if value:
        return value[0]  # pop() Return a list


def remove_field_from_query_dict(query_dict, field_name, remove_value=None):
    """
    Return an encoded URL without the value for given `field_name`.
    For multi-value filters, a single value can be removed using `remove_value`.
    This URL can be used to remove a filter value from the active filters.
    """
    if not query_dict:
        return ""

    data = query_dict.copy()
    field_data = data.pop(field_name, [])

    if remove_value and len(field_data) > 1 and remove_value in field_data:
        for item in field_data:
            if item != remove_value:
                data.update({field_name: item})

    return data.urlencode()


def database_re_escape(pattern):
    """Escape special char for compatibility with the QuerySet `regex` filter."""
    re_special_char = frozenset("!$()*+.:<=>?[]^{|}-")
    return "".join(["\\" + c if c in re_special_char else c for c in pattern])


def get_referer_resolver(request):
    """Return the `ResolverMatch` extracted from the `HTTP_REFERER` request header."""
    referer = request.META.get("HTTP_REFERER")
    if not referer:
        return

    with suppress(Resolver404):
        return resolve(urlparse(referer).path)


def get_instance_from_resolver(resolver):
    """Return an instance extracted from a `ResolverMatch` object provided as `resolver`."""
    # WARNING: Only ModelAdmin changeform views are supported at the moment.
    if not resolver or not hasattr(resolver.func, "model_admin"):
        return

    model = resolver.func.model_admin.model
    object_id = resolver.kwargs.get("object_id")

    with suppress(model.DoesNotExist):
        return model.objects.get(pk=object_id)


def get_instance_from_referer(request):
    """Return an instance extracted from the `HTTP_REFERER` request header."""
    resolver = get_referer_resolver(request)
    if resolver:
        return get_instance_from_resolver(resolver)


def is_available(url):
    """
    Return True if the provided `url` is available.
    Try first with a HEAD request to avoid downloading the full content.
    Sometimes HEAD are not supported by the target webserver,
    we fallback to a regular GET request in that case.
    """
    for request_method in (requests.head, requests.get):
        try:
            response = request_method(url, allow_redirects=True)
        except requests.RequestException:
            return False
        if response.status_code == 200:
            return True
    return False


def unique_seen(objects):
    """
    Return a list of unique `objects` preserving their original order.
    These objects must be hashable.
    """
    seen = set()
    uniques = []
    for obj in objects:
        if obj not in seen:
            uniques.append(obj)
            seen.add(obj)
    return uniques


def is_uuid4(value):
    """Return True is the provided `value` is a proper UUID version 4."""
    try:
        uuid.UUID(str(value), version=4)
    except ValueError:
        return False
    return True


def get_zipfile(files):
    """
    Return a zipfile (in memory) of the provided `files`, where `files` is a
    list of `(filename, content)` entries.
    Duplicated entries are not included.
    """
    file_in_memory = io.BytesIO()

    with zipfile.ZipFile(file_in_memory, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files:
            filename = filename.replace("/", "_")
            is_duplicate = filename in zip_file.NameToInfo
            if not is_duplicate:
                zip_file.writestr(filename, content)

    return file_in_memory


def str_to_id_list(s):
    """
    Convert a comma-separated string of ids into a list of integers.

    >>> str_to_id_list('1,2,3,a')
    [1, 2, 3]
    """
    if not s:
        return []

    id_list = []
    for entry in str(s).split(","):
        try:
            id_list.append(int(entry))
        except ValueError:
            continue

    return id_list


def get_previous_next(ids, current_id):
    """
    Return the previous and next entries from a given `ids` list
    and the current id value.

    >>> get_previous_next([1, 2, 3, 4], 3)
    (2, 4)
    >>> get_previous_next(['a', 'b', 'c'], 'b')
    ('a', 'c')
    """
    previous, next = None, None

    try:
        index = ids.index(current_id)
    except ValueError:
        return None, None

    if index > 0:
        previous = ids[index - 1]
    if index < len(ids) - 1:
        next = ids[index + 1]

    return previous, next


def set_fields_from_object(source, target, fields):
    """
    Get values from `source` object and set on `target` for the given list
    of `fields`.

    Return the list of changed fields.
    """
    changed_fields = []

    for field_name in fields:
        source_value = getattr(source, field_name, None)
        target_value = getattr(target, field_name, None)

        if source_value and not target_value:
            setattr(target, field_name, source_value)
            changed_fields.append(field_name)

    return changed_fields


def get_cpe_vuln_link(cpe):
    base_url = "https://nvd.nist.gov/vuln/search/results"
    params = "?adv_search=true&isCpeNameSearch=true"
    vuln_url = f"{base_url}{params}&query={cpe}"
    return format_html(f'<a target="_blank" href="{vuln_url}">{cpe}</a>')


def safe_filename(filename):
    """Convert provided `name` to a safe filename."""
    return re.sub("[^A-Za-z0-9.-]+", "_", filename).lower()


def is_purl_str(url, validate=False):
    """
    Check if a given URL string is a Package URL (purl).

    If ``validate`` is proviuded, validate the purl format using the
    PackageURL class. If False, simply check if the string starts with
    "pkg:".
    """
    if not validate:
        return url.startswith("pkg:")

    try:
        PackageURL.from_string(purl=url)
    except ValueError:
        return False
    return True


def remove_empty_values(input_dict):
    """
    Return a new dict not including empty value entries from `input_dict`.

    None, empty string, empty list, and empty dict/set are cleaned.
    `0` and `False` values are kept.
    """
    return {key: value for key, value in input_dict.items() if value not in EMPTY_VALUES}
