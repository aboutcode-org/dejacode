#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

import yaml


class DejaCodeConfig(AppConfig):
    name = "dje"
    verbose_name = _("DejaCode")

    def ready(self):
        from dje.mass_update import action_end
        from dje.notification import successful_mass_update

        action_end.connect(successful_mass_update)

        from rest_framework.renderers import DocumentationRenderer

        DocumentationRenderer.languages = []

        # Ensure that mappings are always dumped in the items order when using `yaml.safe_dump`.
        def ordered_dumper(dumper, data):
            return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())

        yaml.SafeDumper.add_representer(dict, ordered_dumper)

        from axes.signals import user_locked_out

        from dje.notification import notify_on_user_locked_out

        user_locked_out.connect(notify_on_user_locked_out, sender="axes")

        from django.conf import settings

        if settings.ENABLE_SELF_REGISTRATION:
            from django.contrib.auth import get_user_model
            from django.db.models.signals import post_save

            from dje.notification import notify_on_user_added_or_updated

            post_save.connect(notify_on_user_added_or_updated,
                              sender=get_user_model())
