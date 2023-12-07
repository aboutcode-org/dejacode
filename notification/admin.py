#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured

from dje.admin import DataspacedAdmin
from dje.admin import ProhibitDataspaceLookupMixin
from dje.admin import dejacode_site
from dje.forms import DataspacedAdminForm
from notification.models import Webhook

HOOK_EVENTS = settings.HOOK_EVENTS
if HOOK_EVENTS is None:
    raise ImproperlyConfigured("settings.HOOK_EVENTS is not defined")


class WebookForm(DataspacedAdminForm):
    EVENTS = [(event, event) for event in HOOK_EVENTS.keys()]

    class Meta:
        model = Webhook
        fields = [
            "target",
            "event",
            "is_active",
            "extra_payload",
            "extra_headers",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"] = forms.ChoiceField(choices=self.EVENTS)

        add = not kwargs.get("instance")
        if add:
            self.instance.user = self.request.user


@admin.register(Webhook, site=dejacode_site)
class WebookAdmin(ProhibitDataspaceLookupMixin, DataspacedAdmin):
    list_display = ("__str__", "event", "target", "is_active", "dataspace")
    form = WebookForm
    list_filter = ("is_active", "event")
    activity_log = False
    actions = []
    actions_to_remove = ["copy_to", "compare_with"]
    email_notification_on = ()
