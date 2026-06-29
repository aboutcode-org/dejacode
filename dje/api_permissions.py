#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ObjectDoesNotExist

from guardian.shortcuts import assign_perm
from guardian.shortcuts import get_groups_with_perms
from guardian.shortcuts import get_users_with_perms
from guardian.shortcuts import remove_perm
from rest_framework import permissions
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from dje.api import DataspacedSlugRelatedField

User = get_user_model()


class CanManageObjectPermissions(permissions.BasePermission):
    """
    Allows managing object-level permissions if the user is:
    - a superuser, or
    - the object's owner (configurable via ``owner_field`` on the View).
    """

    owner_field = "created_by"

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        owner_field = getattr(view, "owner_field", self.owner_field)
        owner = getattr(obj, owner_field, None)
        return owner == user


class ObjectPermissionSerializer(serializers.Serializer):
    """
    Validates POST/DELETE input for the manage_permissions action.
    Exactly one of ``user`` or ``group`` must be provided alongside ``permissions``.
    """

    user = DataspacedSlugRelatedField(
        queryset=User.objects.all(),
        slug_field="username",
        required=False,
        allow_null=True,
        default=None,
    )
    group = serializers.SlugRelatedField(
        queryset=Group.objects.all(),
        slug_field="name",
        required=False,
        allow_null=True,
        default=None,
    )
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=False)

    class Meta:
        fields = ("user", "group", "permissions")

    def validate(self, data):
        has_user = data.get("user") is not None
        has_group = data.get("group") is not None
        if not has_user and not has_group:
            raise serializers.ValidationError("Either 'user' or 'group' must be provided.")
        if has_user and has_group:
            raise serializers.ValidationError(
                "Only one of 'user' or 'group' can be provided, not both."
            )
        return data


class ObjectPermissionsMixin:
    """
    Mixin that adds a ``/permissions/`` endpoint for any object-level ViewSet.
    Supports GET (list), POST (assign), and DELETE (remove) operations for
    both individual users and groups.

    GET /api/{model}/{uuid}/permissions/
    POST /api/{model}/{uuid}/permissions/
    DELETE /api/{model}/{uuid}/permissions/
    """

    @action(
        detail=True,
        methods=["get", "post", "delete"],
        url_path="permissions",
        serializer_class=ObjectPermissionSerializer,
        permission_classes=[permissions.IsAuthenticated, CanManageObjectPermissions],
    )
    def manage_permissions(self, request, *args, **kwargs):
        """
        Manage object-level permissions for this object.

        - GET: List users and groups with their permissions.
        - POST: Assign permissions. Provide ``user`` or ``group`` and ``permissions`` list.
        - DELETE: Remove permissions. Provide ``user`` or ``group`` and ``permissions`` list.
        """
        obj = self.get_object()
        serializer_context = {**self.get_serializer_context(), "object": obj}

        if request.method == "GET":
            users_with_perms = get_users_with_perms(obj, attach_perms=True)
            groups_with_perms = get_groups_with_perms(obj, attach_perms=True)
            data = {
                "users": [
                    {
                        "dataspace": user.dataspace.name,
                        "username": user.get_username(),
                        "object_permissions": list(perms),
                    }
                    for user, perms in users_with_perms.items()
                ],
                "groups": [
                    {
                        "name": group.name,
                        "object_permissions": list(perms),
                    }
                    for group, perms in groups_with_perms.items()
                ],
            }
            return Response(data, status=status.HTTP_200_OK)

        # POST or DELETE
        serializer = self.get_serializer(data=request.data, context=serializer_context)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        target = serializer.validated_data["user"] or serializer.validated_data["group"]
        perms = serializer.validated_data["permissions"]

        if request.method == "POST":
            errors = []
            for perm in perms:
                try:
                    assign_perm(perm, target, obj)
                except ObjectDoesNotExist:
                    errors.append(f"Cannot assign permission '{perm}' due to an internal error.")

            if errors:
                return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"status": "permissions assigned"}, status=status.HTTP_200_OK)

        if request.method == "DELETE":
            errors = []
            for perm in perms:
                try:
                    remove_perm(perm, target, obj)
                except ObjectDoesNotExist:
                    errors.append(f"Cannot remove permission '{perm}' due to an internal error.")

            if errors:
                return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"status": "permissions removed"}, status=status.HTTP_200_OK)
