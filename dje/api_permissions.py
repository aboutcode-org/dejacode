#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from guardian.shortcuts import assign_perm
from guardian.shortcuts import get_perms
from guardian.shortcuts import get_user_perms
from guardian.shortcuts import get_users_with_perms
from guardian.shortcuts import remove_perm
from rest_framework import permissions
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

User = get_user_model()


class CanManageObjectPermissions(permissions.BasePermission):
    """
    Allows managing object-level permissions if the user is:
    - a superuser, or
    - the object's owner (configurable via ``owner_field`` on the View), or
    - has a special manage permission (global or object-level).
    """

    owner_field = "created_by"
    manage_permission_codename = "manage_object_permissions"

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user.is_authenticated:
            return False

        # 1. Superusers always allowed
        if user.is_superuser:
            return True

        # 2. Check if user matches object's owner field
        # The field can be overridden on the ViewSet (e.g., owner_field = "owner")
        owner_field = getattr(view, "owner_field", self.owner_field)
        owner = getattr(obj, owner_field, None)
        if owner == user:
            return True

        # 3. Check for specific manage permission (global or object-level)
        app_label = obj._meta.app_label
        codename = getattr(view, "manage_permission_codename", self.manage_permission_codename)
        perm_name = f"{app_label}.{codename}"
        if user.has_perm(perm_name) or user.has_perm(perm_name, obj):
            return True

        return False


class ObjectPermissionSerializer(serializers.Serializer):
    """
    Generic serializer for representing or updating object-level permissions.
    Accepts:
      - user: user ID
      - permissions: list of permission codenames
    """

    # TODO: Scope by dataspace, see DataspacedSlugRelatedField
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field="username",
    )
    # user = DataspacedSlugRelatedField(slug_field="username")
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=False)

    class Meta:
        fields = (
            "user",
            "permissions",
        )

    def to_representation(self, instance):
        """Make sure to provide the target object in context via `context["object"]`."""
        obj = self.context.get("object")
        user = instance
        return {
            "dataspace": user.dataspace.name,
            "username": user.get_username(),
            "object_permissions": get_user_perms(user, obj),
            "model_permissions": get_perms(user, obj),
        }


class ObjectPermissionsMixin:
    """
    Mixin that adds a `/permissions/` endpoint for any object-level ViewSet.
    Supports GET (list), POST (assign), and DELETE (remove) operations.

    GET /api/{model}/{uuid}/permissions/ → list all users and perms
    POST /api/{model}/{uuid}/permissions/ → assign perms to a user
    DELETE /api/{model}/{uuid}/permissions/ → remove perms from a user
    """

    @action(
        detail=True,
        methods=["get", "post", "delete"],
        url_path="permissions",
        serializer_class=ObjectPermissionSerializer,
        permission_classes=[CanManageObjectPermissions],
    )
    def manage_permissions(self, request, *args, **kwargs):
        """
        Manage object-level permissions for this object.

        - GET: List users and their permissions.
        - POST: Assign permissions to a user. Provide `user` ID and `permissions` list.
        - DELETE: Remove permissions from a user. Provide `user` ID and `permissions`
          list.
        """
        obj = self.get_object()
        serializer_context = {"object": obj}

        if request.method == "GET":
            users_with_perms = get_users_with_perms(obj, attach_perms=True)
            serializer = self.get_serializer(
                users_with_perms.keys(), many=True, context=serializer_context
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        # POST or DELETE
        serializer = self.get_serializer(data=request.data, context=serializer_context)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]
        perms = serializer.validated_data["permissions"]

        if request.method == "POST":
            errors = []
            for perm in perms:
                try:
                    assign_perm(perm, user, obj)
                except ObjectDoesNotExist as e:
                    errors.append(f"Cannot assign permission '{perm}': {str(e)}")

            if errors:
                return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"status": "permissions assigned"}, status=status.HTTP_200_OK)

        if request.method == "DELETE":
            errors = []
            for perm in perms:
                try:
                    remove_perm(perm, user, obj)
                except ObjectDoesNotExist as e:
                    errors.append(f"Cannot remove permission '{perm}': {str(e)}")

            if errors:
                return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"status": "permissions removed"}, status=status.HTTP_200_OK)
