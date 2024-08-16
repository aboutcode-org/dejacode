#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import copy
import logging
from contextlib import suppress

from django import dispatch
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError
from django.db import transaction
from django.db.models import AutoField
from django.db.models import BooleanField
from django.db.models import ForeignKey

from dje.models import Dataspace
from dje.models import DataspacedModel
from dje.models import DejacodeUser
from dje.models import History
from dje.models import HistoryUserFieldsMixin

logger = logging.getLogger("dje")

post_copy = dispatch.Signal()
post_update = dispatch.Signal()

SKIP = "SKIP"


COPY_DEFAULT_EXCLUDE = {
    "License Library": {
        "license": [
            "guidance",
            "guidance_url",
            "usage_policy",
        ],
    },
    "Component Catalog": {
        "component": [
            "usage_policy",
            "guidance",
            "acceptable_linkages",
        ],
        "subcomponent relationship": [
            "extra_attribution_text",
            "usage_policy",
        ],
    },
}


ALWAYS_EXCLUDE = [
    "created_date",
    "created_by",
    "last_modified_date",
    "last_modified_by",
    "request_count",
    "scanned_by",
    "project_uuid",
    "default_assignee",
]


def get_object_in(reference_obj, target_dataspace):
    """
    Return the object if matched in the `target_dataspace` using the
    UUID of the `reference_obj`.
    """
    model_class = reference_obj.__class__

    if not issubclass(model_class, DataspacedModel):
        raise AssertionError("The object is not Dataspace related")

    with suppress(model_class.DoesNotExist):
        return model_class.objects.get(uuid=reference_obj.uuid, dataspace=target_dataspace)


def get_or_create_in(reference_obj, target_dataspace, user, **kwargs):
    """
    Try to match an object in the target or create it if not found.
    Return the matched or created instance, or None if not matched and copy
    not possible.
    """
    instance_in_target = get_object_in(reference_obj, target_dataspace)

    if not instance_in_target:
        instance_in_target = copy_object(reference_obj, target_dataspace, user, **kwargs)

    return instance_in_target  # None if not matched and the copy failed


def get_copy_defaults(dataspace, model_class):
    """
    Return copy defaults from the `dataspace` configuration.
    If no configuration is available, fallback to the `COPY_DEFAULT_EXCLUDE`.
    """
    configuration = dataspace.get_configuration("copy_defaults")
    if configuration is None:  # Different from an empty `{}` saved configuration.
        configuration = COPY_DEFAULT_EXCLUDE
    app_name = model_class._meta.app_config.verbose_name
    model_name = model_class._meta.verbose_name
    return configuration.get(app_name, {}).get(model_name, [])


def get_excluded_fields(exclude_dict, dataspace, model_class):
    """Return the list of fields to be excluded from the copy."""
    if model_class in exclude_dict.keys():
        # Excluded fields declared for this model.
        # It can be an explicit empty list if no field should be excluded.
        return exclude_dict[model_class]

    return get_copy_defaults(dataspace, model_class)


@transaction.atomic()
def copy_object(reference_obj, target_dataspace, user, update=False, **kwargs):
    """
    Entry point for the copy or update of a given object in another `target`
    Dataspace.

    :param reference_obj: Instance of the object to be copied/updated.
    :param target_dataspace: Instance of the target Dataspace.
    :param user: The User to be referenced in the History.
    :param update: Try to update the target object if True
    :return: Instance of the new or updated object.
    """
    model_name = reference_obj.__class__.__name__
    debug_message = "copy_object: {operation} for <{model_name}>: {reference_obj}"
    obj_in_target = get_object_in(reference_obj, target_dataspace)

    try:
        if not obj_in_target:  # ADDITION
            # The following could throw an exception if some DB constraint is
            # not fulfilled
            logger.debug(debug_message.format(operation="COPY", **locals()))
            copy_to(reference_obj, target_dataspace, user, **kwargs)
        elif update:  # MODIFICATION, only if explicitly asked
            logger.debug(debug_message.format(operation="UPDATE", **locals()))
            update_to(reference_obj, obj_in_target, user, **kwargs)
        else:
            # There's a Match in the target but no update asked, do nothing
            logger.debug(debug_message.format(operation="NOOP", **locals()))
            return

    except IntegrityError:
        # Special case where the object cannot be copied nor updated because
        # on of his unique_together with dataspace fields (except
        # the one used for Matching in target) already exists.
        # The integrity error is propagated up from a DB constraints error as
        # the unicity constraint cannot be satisfied in the DB
        logger.debug(debug_message.format(operation="IntegrityError", **locals()))
        raise  # re-raise the exception

    # Refresh the copied/updated object, Return None if something went wrong
    return get_object_in(reference_obj, target_dataspace)


def copy_to(reference_obj, target_dataspace, user, **kwargs):
    """
    Copy reference instance to the target dataspace, using the given user for
    permissions and logging as needed.
    """
    reference_dataspace = reference_obj.dataspace
    model_class = reference_obj.__class__

    if reference_dataspace == target_dataspace:
        raise AssertionError("Reference and target cannot share the same Dataspace")

    # Copy configuration
    exclude_dict = kwargs.get("exclude", {})
    excluded_fields = get_excluded_fields(exclude_dict, user.dataspace, model_class)
    if excluded_fields == SKIP:
        logger.debug(f"copy_object: SKIP copy for {repr(reference_obj)}")
        return
    excluded_fields.extend(ALWAYS_EXCLUDE)

    # Create a copy of the instance to work on, so we do not impact the original
    # instance. Forcing a INSERT in the Database by resetting the id
    target_obj = copy.deepcopy(reference_obj)
    target_obj.id = None
    target_obj.dataspace = target_dataspace

    # Replace FKs by match or copy on the copied_object
    copy_foreignfields(reference_obj, target_obj, excluded_fields, user, **kwargs)

    # Set the proper id value on GenericForeignKey fields
    fix_generic_foreignkeys(reference_obj, target_obj)

    # Reset the excluded fields to their default value, or None
    for field_name in excluded_fields:
        try:
            field = reference_obj._meta.get_field(field_name)
        except FieldDoesNotExist:
            continue
        # get_default Return None or empty string (depending on the Field type)
        # if no default value was declared.
        setattr(target_obj, field_name, field.get_default())

    # History fields are only set when the user copy to his dataspace
    # since we do not want to associate an user with objects from another dataspace
    if user.dataspace == target_dataspace and issubclass(model_class, HistoryUserFieldsMixin):
        target_obj.created_by = user
        target_obj.last_modified_by = user

    # Add a `copy` argument for custom behavior during save()
    target_obj.save(copy=True)

    message = 'Copy object from "{}" dataspace to "{}" dataspace.'.format(
        reference_dataspace.name, target_dataspace.name
    )
    History.log_addition(user, target_obj, message)

    # Set skip_m2m_and_o2m to True to skip the m2m and o2m copy cascade.
    if not kwargs.get("skip_m2m_and_o2m", False):
        # Copy o2m and m2m can only be executed after save()
        copy_relational_fields(reference_obj, target_dataspace, user, **kwargs)
        # None of the m2m relation (through table) can exist as the object is not existing yet.
        copy_m2m_fields(reference_obj, target_dataspace, user, **kwargs)

    post_copy.send(sender=model_class, reference=reference_obj, target=target_obj, user=user)


def get_generic_foreignkeys_fields(model_class):
    return [f for f in model_class._meta.get_fields() if isinstance(f, GenericForeignKey)]


def fix_generic_foreignkeys(reference_obj, target_obj):
    """Set the proper id value on GenericForeignKey fields."""
    for generic_fk in get_generic_foreignkeys_fields(reference_obj):
        content_object = getattr(reference_obj, generic_fk.name, None)
        if content_object:
            target_obj.content_object = content_object.__class__.objects.get(
                uuid=content_object.uuid, dataspace=target_obj.dataspace
            )


def copy_foreignfields(reference_obj, target_obj, excluded_fields, user, **kwargs):
    """
    Set the FKs during copy. Try to match or copy in the target Dataspace first.
    Excluded FK fields are not copied.
    """
    for field in target_obj.local_foreign_fields:
        field_name = field.name

        skip_conditions = [
            issubclass(field.related_model, Dataspace),
            issubclass(field.related_model, ContentType),
            issubclass(field.related_model, DejacodeUser),
            field_name in excluded_fields,
        ]

        if any(skip_conditions):
            continue

        # This is the FK object instance of the reference object
        fk_instance = getattr(reference_obj, field_name, None)
        if not fk_instance:
            continue

        matched_obj = get_or_create_in(fk_instance, target_obj.dataspace, user, **kwargs)
        if matched_obj:
            setattr(target_obj, field_name, matched_obj)
        else:  # Match nor copy were not possible.
            setattr(target_obj, field_name, None)


def copy_relational_fields(reference_obj, target_dataspace, user, update=False, **kwargs):
    """
    Copy the explicitly declared related objects for this instance.
    OneToMany and GenericForeignKey need to be declared in
    Model.get_one_to_many_related_names() using the related_name.
    """
    field_names = reference_obj.get_extra_relational_fields()

    for field_name in field_names:
        field = reference_obj._meta.get_field(field_name)
        if kwargs.get("exclude", {}).get(field.related_model) == SKIP:
            logger.debug(f"copy_object: SKIP copy for {repr(reference_obj)}")
            continue

        related_manager = getattr(reference_obj, field_name, None)
        if not related_manager:
            continue

        for instance in related_manager.all():
            copy_object(instance, target_dataspace, user, update, **kwargs)


def copy_m2m_fields(reference_obj, target_dataspace, user, update=False, **kwargs):
    """
    Copy the ManyToMany fields of an instance.
    Run the copy of each 'through' relation, the related object will be
    copied by the FKs copy if not matched.
    The ManyToMany fields needs to be explicitly declared on the Model
    to be handled by the m2m copy. Implicit relations will be ignored.
    Update is supported by m2m copy: values of the m2m relation (though table)
    are updated but not the values of the related object.
    """
    # List of the m2m fields on the current Model
    m2m_fields = reference_obj._meta.many_to_many

    for m2m_field in m2m_fields:
        # Relation Model (through table)
        through_model = m2m_field.remote_field.through
        # FK fields names on the Relation Model
        m2m_field_name = m2m_field.m2m_field_name()
        reference_m2m_qs = through_model.objects.filter(**{m2m_field_name: reference_obj})

        if kwargs.get("exclude", {}).get(through_model) == SKIP:
            logger.debug(f"copy_object: SKIP copy for {repr(reference_obj)}")
            continue

        for ref_instance in reference_m2m_qs:
            # Copy each of those relation objects, missing FK instances will be copied along.
            copy_object(ref_instance, target_dataspace, user, update, **kwargs)


def update_to(reference_obj, target_obj, user, **kwargs):
    target_dataspace = target_obj.dataspace
    model_class = reference_obj.__class__

    if reference_obj.dataspace == target_dataspace:
        raise AssertionError("Reference and target cannot share the same Dataspace")

    # Copy configuration
    exclude_dict = kwargs.get("exclude", {})
    excluded_fields = get_excluded_fields(exclude_dict, user.dataspace, model_class)
    if excluded_fields == SKIP:
        logger.debug(f"copy_object: SKIP update for {repr(reference_obj)}")
        return
    excluded_fields.extend(ALWAYS_EXCLUDE)

    copy_foreignfields(reference_obj, target_obj, excluded_fields, user, **kwargs)

    generic_fk_field = [
        generic_fk.fk_field for generic_fk in get_generic_foreignkeys_fields(reference_obj)
    ]

    for field in target_obj._meta.fields:
        # Ignore the fields that are explicitly declared to be excluded
        skip_conditions = [
            field.name in excluded_fields,
            isinstance(field, ForeignKey),
            isinstance(field, AutoField),
            # For BooleanField.null=True, do not update the target value if the
            # reference value is Unknown (None).
            # Important to test against None rather than using "not" which would
            # catch False value too.
            isinstance(field, BooleanField)
            and field.null
            and getattr(reference_obj, field.name) is None,
            # Do not update the object_id value, as it is unique to the current dataspace
            field.attname in generic_fk_field,
        ]

        if any(skip_conditions):
            continue

        # Set the new value on target if none of those cases occurred
        setattr(target_obj, field.name, getattr(reference_obj, field.name))

    # History fields are only set when the user copy to his dataspace
    # since we do not want to associate an user with objects from another dataspace
    if user.dataspace == target_dataspace and issubclass(model_class, HistoryUserFieldsMixin):
        target_obj.last_modified_by = user

    serialized_data = target_obj.as_json()
    # Add a `copy` argument for custom behavior during save()
    target_obj.save(copy=True)

    # Copy o2m and m2m can only be executed after save()
    copy_relational_fields(reference_obj, target_dataspace, user, update=True, **kwargs)
    # Always update m2m relation (through table) on m2m update, the related
    # object will not be affected.
    copy_m2m_fields(reference_obj, target_dataspace, user, update=True, **kwargs)

    # The object as been updated, logging as a CHANGE
    message = 'Updated object from "{}" dataspace to "{}" dataspace.'.format(
        reference_obj.dataspace.name, target_dataspace.name
    )
    History.log_change(user, target_obj, message, serialized_data)

    post_update.send(sender=model_class, reference=reference_obj, target=target_obj, user=user)
