#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.utils.html import format_html


class UsagePolicyWidgetWrapper(RelatedFieldWidgetWrapper):
    def __init__(self, *args, **kwargs):
        self.object_instance = kwargs.pop("object_instance")
        super().__init__(*args, **kwargs)

    def render(self, name, value, *args, **kwargs):
        rendered = super().render(name, value, *args, **kwargs)

        value_from_license = ""
        if self.object_instance and self.object_instance.policy_from_primary_license:
            value_from_license = format_html(
                '<div class="grp-readonly">Value from primary license {}: {}</div>',
                self.object_instance.primary_license,
                self.object_instance.policy_from_primary_license,
            )

        return format_html("{}{}", rendered, value_from_license)
