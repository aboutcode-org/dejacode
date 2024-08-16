#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import template
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from rest_hooks.models import AbstractHook

from dje.models import DataspacedModel


# DataspacedModel is first as we want to apply it last for proper overrides
class Webhook(DataspacedModel, AbstractHook):
    is_active = models.BooleanField(default=True)
    extra_payload = models.JSONField(
        blank=True,
        default=dict,
        help_text=_("Extra data as JSON to be included in the payload"),
    )
    extra_headers = models.JSONField(
        blank=True,
        default=dict,
        help_text=_("Extra headers as JSON to be included in the request"),
    )

    class Meta:
        unique_together = ("dataspace", "uuid")

    def __str__(self):
        return f"{self.event} => {self.target}"

    def dict(self):
        return {"uuid": str(self.uuid), "event": self.event, "target": self.target}

    def get_extra_headers(self):
        """Inject `hook_env` context in headers template values."""
        if hook_env := settings.HOOK_ENV:
            hook_env_context = template.Context(hook_env)
            return {
                key: self.render_template(value, hook_env_context)
                for key, value in self.extra_headers.items()
            }

        return self.extra_headers

    @staticmethod
    def render_template(value, hook_env_context):
        if "{{" in value and "}}" in value:
            return template.Template(value).render(hook_env_context)
        return value


def find_and_fire_hook(
    event_name,
    instance,
    user_override=None,
    dataspace=None,
    payload_override=None,
):
    """
    Fire active Webhook instances found in the `dataspace` for the `event_name`.
    If `dataspace` is not provided, uses the Dataspace of the `instance`.
    """
    if not dataspace and instance:
        dataspace = instance.dataspace
    if not dataspace:
        raise AttributeError("Provide one of `dataspace` or `instance` argument.")

    filters = {
        "event": event_name,
        "is_active": True,
    }

    hooks = Webhook.objects.scope(dataspace).filter(**filters)

    for hook in hooks:
        hook.deliver_hook(instance, payload_override)
