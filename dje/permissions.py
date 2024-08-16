#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from guardian.shortcuts import assign_perm as guardian_assign_perm
from guardian.shortcuts import get_perms_for_model


def get_protected_fields(model_class, user):
    """Return the list of protected fields names for the given `user`."""
    protected_fields = getattr(
        model_class(), "permission_protected_fields", {})

    return [
        field_name
        for field_name, perm_codename in protected_fields.items()
        if not user.has_perm(f"{model_class._meta.app_label}.{perm_codename}")
    ]


def get_limited_perms_for_model(cls):
    """Remove the 'add' permission from the returned permissions list."""
    return get_perms_for_model(cls).exclude(codename__startswith="add")


def assign_all_object_permissions(user, obj):
    """
    Wrap `guardian_assign_perm` to assign the object permissions:
    view/change/delete, to the given `user`.
    """
    perms = get_limited_perms_for_model(obj._meta.model)  # view/change/delete
    for perm in perms:
        guardian_assign_perm(perm, user, obj)


def get_all_tabsets():
    """Return available tabs from all subclasses of ObjectDetailsView."""
    from dje.views import ObjectDetailsView

    return {
        view_class.model._meta.verbose_name: view_class.tabset
        for view_class in ObjectDetailsView.__subclasses__()
        if view_class.tabset
    }


def get_tabset_for_model(model_class):
    """Return the tabset content for the given `model_class`."""
    return get_all_tabsets().get(model_class._meta.verbose_name)


def get_authorized_tabs(model_class, user):
    """
    Return the authorized tabs for this `user` for the given `model_class` .
    Tab availability is always driven by the current user Dataspace.
    A `is_superuser` user can see all the tabs.
    The authorizations are based on Permissions Groups and defined in the
    DataspaceConfiguration.tab_permissions field.
    Each Groups defines a list of authorized tabs.
    Empty string is used to define authorizations for Users without any assigned Groups.
    In case multiple Groups are assigned to the User, all the authorized tabs are merged.
    """
    if user.is_superuser:
        return

    tab_permissions = user.dataspace.get_configuration("tab_permissions")
    # The authorization feature is not enabled for the current user dataspace
    if not tab_permissions:
        return

    model_name = model_class._meta.model_name
    user_groups = user.get_group_names() or [""]
    authorized_tabs = set()
    for group_name in user_groups:
        group_tabs = tab_permissions.get(group_name, {}).get(model_name, [])
        authorized_tabs.update(group_tabs)

    return list(authorized_tabs) or [None]
