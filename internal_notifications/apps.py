#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InternalNotificationsConfig(AppConfig):
    name = "internal_notifications"
    # Label of the former django-notifications-patched app: keeps the table,
    # the migration history, and the content types unchanged.
    label = "notifications"
    verbose_name = _("Notifications")
