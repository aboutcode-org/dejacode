#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django import forms
from django.contrib import admin

from dje.admin import DataspacedAdmin
from dje.admin import ProhibitDataspaceLookupMixin
from dje.admin import dejacode_site
from dje.forms import DataspacedAdminForm
from notification.models import WEBHOOK_EVENTS
from notification.models import WebhookDelivery
from notification.models import WebhookSubscription


class WebhookSubscriptionForm(DataspacedAdminForm):
    EVENTS = [(event, event) for event in WEBHOOK_EVENTS]

    class Meta:
        model = WebhookSubscription
        fields = [
            "target_url",
            "event",
            "is_active",
            "extra_payload",
            "extra_headers",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"] = forms.ChoiceField(choices=self.EVENTS)


class WebhookDeliveryInline(admin.TabularInline):
    model = WebhookDelivery
    fields = ("sent_date", "response_status_code", "delivery_error")
    readonly_fields = ("sent_date", "response_status_code", "delivery_error")
    extra = 0
    can_delete = False
    show_change_link = False
    verbose_name_plural = "Last 10 deliveries"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        latest_pks = qs.order_by("-sent_date").values_list("pk", flat=True)[:10]
        return qs.filter(pk__in=latest_pks).order_by("-sent_date")


@admin.register(WebhookSubscription, site=dejacode_site)
class WebhookSubscriptionAdmin(ProhibitDataspaceLookupMixin, DataspacedAdmin):
    list_display = ("__str__", "event", "target_url", "is_active", "dataspace")
    form = WebhookSubscriptionForm
    list_filter = ("is_active", "event")
    activity_log = False
    actions = []
    actions_to_remove = ["copy_to", "compare_with"]
    email_notification_on = ()
    inlines = [WebhookDeliveryInline]
