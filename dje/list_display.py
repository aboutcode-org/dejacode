#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.html import mark_safe

from dje.templatetags.dje_tags import urlize_target_blank
from dje.utils import class_wrap
from dje.utils import queryset_to_html_list


class ListDisplayItem:
    def __init__(self, name, **kwargs):
        self.name = name
        self.__name__ = name
        # Ideally we should use label_for_field but the Model is required
        self.short_description = kwargs.get("short_description", name.replace("_", " "))
        self.html_class = kwargs.get("html_class")
        kwargs.setdefault("admin_order_field", name)
        self.__dict__.update(kwargs)

    def __call__(self, obj):
        if obj:
            value = getattr(obj, self.name)
            if value:
                value = self.to_representation(value)
                if self.html_class:
                    return class_wrap(value, self.html_class)
                return value

    def __repr__(self):
        return self.name

    def to_representation(self, value):
        return value


class AsURL(ListDisplayItem):
    def to_representation(self, value):
        return urlize_target_blank(value)


class AsLink(ListDisplayItem):
    def to_representation(self, value):
        return value.get_admin_link(target="_blank")


class AsLinkList:
    def __init__(
        self,
        related_name,
        field_filter,
        verbose_name=None,
        qs_limit=0,
        html_class="width200",
        **kwargs,
    ):
        self.related_name = related_name
        self.__name__ = related_name
        self.short_description = verbose_name or related_name
        self.field_filter = field_filter
        self.qs_limit = qs_limit
        self.html_class = html_class
        kwargs.setdefault("admin_order_field", related_name)
        self.__dict__.update(kwargs)

    def __call__(self, obj):
        if obj:
            qs = getattr(obj, self.related_name).all()
            params = {f"{self.field_filter}__id__exact": obj.id}
            html = queryset_to_html_list(qs, params, self.qs_limit)
            if html:
                return class_wrap(html, self.html_class)

    def __repr__(self):
        return self.related_name


class AsJoinList(ListDisplayItem):
    def __init__(self, name, join_str, **kwargs):
        self.join_str = join_str
        kwargs["admin_order_field"] = None
        super().__init__(name, **kwargs)

    def to_representation(self, value):
        return mark_safe(self.join_str.join(value))


class AsNaturalTime(ListDisplayItem):
    def to_representation(self, value):
        date_formatted = date_format(value, "N j, Y, f A T")
        return format_html('<span title="{}">{}</span>', date_formatted, naturaltime(value))


class AsColored(ListDisplayItem):
    def to_representation(self, value):
        if value:
            return format_html(
                '<span style="color:{color_code};">{color_code}</a>', color_code=value
            )
