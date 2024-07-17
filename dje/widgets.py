#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.admin.widgets import AdminTextInputWidget
from django.db.models.fields import BLANK_CHOICE_DASH
from django.forms import widgets
from django.forms.utils import flatatt
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from django_filters.widgets import LinkWidget


class DropDownWidget(LinkWidget):
    dropdown_template = """
    <div class="dropdown btn-group">
      <a class="btn btn-outline-secondary btn-xs dropdown-toggle {active}" href="#" role="button"
         data-bs-toggle="dropdown" aria-haspopup="true" aria-expanded="false"
         aria-label="{label} options dropdown">
      </a>
      {menu}
    </div>
    """

    def __init__(self, attrs=None, choices=(), anchor=None, right_align=False, label=None):
        self.anchor = anchor
        self.right_align = right_align
        self.label = label
        super().__init__(attrs, choices)

    def render(self, name, value, attrs=None, renderer=None, choices=()):
        css_class = "dropdown-menu"
        if self.right_align:
            css_class += " dropdown-menu-end"
        attrs = dict(attrs)
        attrs.update({"class": css_class})

        if not hasattr(self, "data"):
            self.data = {}
        if value is None:
            value = ""
        final_attrs = self.build_attrs(self.attrs, extra_attrs=attrs)
        output = [f"<div{flatatt(final_attrs)}>"]
        options = self.render_options(choices, [value], name)
        if options:
            output.append(options)
        output.append("</div>")
        menu = format_html("\n".join(output))

        return format_html(
            self.dropdown_template,
            menu=menu,
            active="active" if value else "",
            label=self.label if self.label else name.title(),
        )

    def render_option(self, name, selected_choices, option_value, option_label):
        option_value = str(option_value)
        if option_label == BLANK_CHOICE_DASH[0][1]:
            option_label = _("All")

        data = self.data.copy()
        data[name] = option_value
        selected = data == self.data or option_value in selected_choices
        css_class = "dropdown-item"
        if selected:
            css_class += " active"

        try:
            url = data.urlencode()
        except AttributeError:
            # doseq is required for proper encoding,
            url = urlencode(data, doseq=True)

        return self.option_string().format(
            css_class=css_class,
            query_string=url,
            label=str(option_label),
            anchor=self.anchor or "",
        )

    def option_string(self):
        return '<a href="?{query_string}{anchor}" class="{css_class}">{label}</a>'


class DropDownRightWidget(DropDownWidget):
    def __init__(self, attrs=None, choices=(), *args, **kwargs):
        super().__init__(attrs, choices, *args, **kwargs)
        self.right_align = True


class DropDownAsListWidget(DropDownRightWidget):
    dropdown_template = """
    <li class="dropdown {active}">
      <a class="dropdown-toggle" data-bs-toggle="dropdown" href="#"
         aria-label="{label} options dropdown">
        {label} <b class="caret"></b>
      </a>
      {menu}
    </li>
    """


class SortDropDownWidget(DropDownRightWidget):
    dropdown_template = """
    <div class="dropdown {active}" data-bs-toggle="tooltip" data-bs-trigger="hover" title="Sort">
      <a class="btn btn-outline-dark dropdown-toggle" data-bs-toggle="dropdown" href="#"
         aria-label="Sort">
        <i class="fas fa-sort-amount-down"></i> <span class="caret"></span>
      </a>
      {menu}
    </div>
    """


class BootstrapSelectMixin:
    def __init__(self, attrs=None, choices=(), search=True, header_title="", search_placeholder=""):
        self.search = search
        self.header_title = header_title
        self.search_placeholder = search_placeholder
        super().__init__(attrs, choices)

    def order_choices_selected_first(self, choices, value):
        ordered_choices = []
        for option_value, option_label in list(choices):
            entry = (option_value, option_label)
            if option_value in value:
                ordered_choices.insert(0, entry)
            else:
                ordered_choices.append(entry)
        return ordered_choices

    def get_context(self, name, value, attrs):
        # Apply the order in `get_context` since this method is only called once
        # and the `self.choices` are properly set when reaching it.
        if value:
            self.choices = self.order_choices_selected_first(self.choices, value)

        css_class = "bootstrap-select-filter show-tick"
        if value:
            css_class += " active"

        extra_attrs = {
            "class": css_class,
            "data-dropdown-align-right": "true",
            "data-header": self.header_title or "Select all that apply",
            "data-size": "11",
            "data-style": "btn btn-outline-secondary btn-xs",
            "data-selected-text-format": "static",
            "data-width": "100%",
            "data-dropup-auto": "false",
            "data-tick-icon": "icon-ok",
        }

        if self.search:
            extra_attrs["data-live-search"] = "true"
            extra_attrs["data-live-search-placeholder"] = self.search_placeholder

        attrs.update(extra_attrs)
        return super().get_context(name, value, attrs)


class BootstrapSelectWidget(BootstrapSelectMixin, widgets.Select):
    pass


class BootstrapSelectMultipleWidget(BootstrapSelectMixin, widgets.SelectMultiple):
    pass


class AdminAwesompleteInputWidget(AdminTextInputWidget):
    class Media:
        css = {
            "all": ("awesomplete/awesomplete-1.1.5.css",),
        }
        # WARNING: Only `awesomplete-*.min.js` is required but the full list in the
        # proper order prevent from `MediaOrderConflictWarning` to be raised.
        js = [
            "admin/js/vendor/jquery/jquery.min.js",
            "admin/js/jquery.init.js",
            "admin/js/inlines.js",
            "awesomplete/awesomplete-1.1.5.min.js",
        ]

    def __init__(self, attrs=None, data_list=None):
        final_attrs = {
            "class": "vTextField awesomplete",
            "data-minchars": "1",
            "data-maxitems": "10",
            "data-autofirst": "true",
        }

        if data_list:
            # Expecting "A, B, C," with trailing comma, or "#html_id"
            final_attrs["data-list"] = data_list

        if attrs is not None:
            final_attrs.update(attrs)
        super().__init__(attrs=final_attrs)


class AwesompleteInputWidgetMixin:
    class Media:
        css = {
            "all": ("awesomplete/awesomplete-1.1.5.css",),
        }
        js = [
            "awesomplete/awesomplete-1.1.5.min.js",
        ]


class AwesompleteInputWidget(
    AwesompleteInputWidgetMixin,
    widgets.TextInput,
):
    def __init__(self, attrs=None, data_list=None):
        final_attrs = {
            "class": "awesomplete",
            "data-minchars": "1",
            "data-maxitems": "10",
            "data-autofirst": "true",
        }

        if data_list:
            # Expecting "A, B, C" or "#html_id"
            final_attrs["data-list"] = data_list

        if attrs is not None:
            final_attrs.update(attrs)
        super().__init__(attrs=final_attrs)


class AutocompleteInput(widgets.TextInput):
    template_name = "widgets/autocomplete.html"

    class Media:
        css = {"all": ("awesomplete/awesomplete-1.1.5.css",)}
        js = (
            "awesomplete/awesomplete-1.1.5.min.js",
            "js/widget_autocomplete.js",
        )

    def __init__(
        self, attrs=None, display_link=True, can_add=False, display_attribute="display_name"
    ):
        attrs = {
            "placeholder": "Start typing for suggestions...",
            **(attrs or {}),
        }

        self.display_link = display_link
        self.can_add = can_add
        self.display_attribute = display_attribute

        super().__init__(attrs=attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        field_id = attrs.get("id") or self.attrs.get("id")
        # Forcing some uniqueness in case of duplicated HTML id
        context["field_selector"] = f"input#{field_id}.autocompleteinput"
        context["object_link_id"] = f"{field_id}_link"

        context["display_attribute"] = self.display_attribute
        context["can_add"] = self.can_add

        if self.display_link:
            context["absolute_url"] = getattr(self, "absolute_url", "")

        return context


class DatePicker(widgets.DateInput):
    class Media:
        css = {
            "all": ("flatpickr/flatpickr-4.5.2.min.css",),
        }
        js = [
            "flatpickr/flatpickr-4.5.2.min.js",
        ]

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs)
        self.attrs.update({"placeholder": "YYYY-MM-DD"})
