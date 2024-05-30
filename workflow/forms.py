#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json

from django import forms
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.exceptions import ObjectDoesNotExist
from django.forms import fields
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML
from crispy_forms.layout import Button
from crispy_forms.layout import Div
from crispy_forms.layout import Field
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout
from crispy_forms.layout import Submit

from dje.fields import SmartFileField
from dje.forms import StrictSubmit
from dje.models import is_secured
from dje.widgets import AutocompleteInput
from dje.widgets import DatePicker
from product_portfolio.models import Product
from workflow.models import Request
from workflow.models import RequestAttachment

submit_as_private = StrictSubmit(
    "submit_as_private",
    _("Submit As Private"),
    css_id="is_private",
    css_class="btn-outline-dark",
    data_placement="top",
    data_toggle="tooltip",
    title="Submit your request so that the details are visible "
    "only to yourself and to request reviewers; other "
    "users will see only a limited summary. The request "
    "reviewers have the option to make the request public "
    "when appropriate.",
)

save_draft = StrictSubmit(
    "save_draft",
    _("Save Draft"),
    css_class="btn-outline-success",
    data_placement="top",
    data_toggle="tooltip",
    title='Self-assign this request with the "Draft" status. ' "Notifications are not sent.",
)


class RequestForm(forms.ModelForm):
    object_id = forms.CharField(
        widget=forms.HiddenInput,
        required=False,
    )
    applies_to = forms.CharField(
        label=_("Applies to"),
        required=False,
        widget=AutocompleteInput(display_link=False),
        help_text=_(
            "Identify the application object associated with this request. "
            "This can be a component, package, license, or product depending on "
            "the type of request."
        ),
    )
    add_object_to_product = forms.BooleanField(
        required=False,
        initial=True,
        help_text=_(
            'Assign the object defined in "Applies to" to the Product defined '
            'in "Product context" on creation of this Request.'
        ),
    )

    class Meta:
        model = Request
        fields = [
            "title",
            "applies_to",
            "add_object_to_product",
            "product_context",
            "assignee",
            "priority",
            "status",
            "notes",
            "cc_emails",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        if not self.user:
            raise AttributeError("User is required.")

        request_template = kwargs.pop("request_template")
        if not request_template:
            raise AttributeError("RequestTemplate is required.")
        self.request_template = request_template

        # Validate the given object_id, this Set self.content_object
        object_id = kwargs.get("initial", {}).get("object_id")
        if object_id:
            if not self.set_content_object(object_id):
                del kwargs["initial"]["object_id"]

        super().__init__(*args, **kwargs)

        self.is_addition = not self.instance.id

        has_change_permission = all(
            [
                self.user.is_staff,
                self.user.has_perm("workflow.change_request"),
            ]
        )
        if self.is_addition or not has_change_permission:
            del self.fields["status"]
            del self.fields["notes"]

        content_object = self.instance.content_object or getattr(self, "content_object", None)

        if request_template.include_applies_to:
            api_url = reverse(f"api_v2:{request_template.content_type.model}-list")
            self.fields["applies_to"].widget.attrs.update({"data-api_url": api_url})
            self.set_applies_to_view_link(content_object)
            if content_object:
                self.fields["applies_to"].initial = str(content_object)
                # Force text to avoid str() vs. int() equality issue in field.has_changed()
                self.fields["object_id"].initial = str(content_object.id)
        else:
            del self.fields["applies_to"]

        model_name = self.request_template.content_type.model
        include_add_object_to_product = all(
            [
                self.is_addition,
                request_template.include_applies_to,
                request_template.include_product,
                model_name in ["component", "package"],
                self.user.has_perm(f"product_portfolio.add_product{model_name}"),
            ]
        )
        if not include_add_object_to_product:
            del self.fields["add_object_to_product"]

        if request_template.include_product:
            self.fields["product_context"].queryset = Product.objects.get_queryset(self.user)
        else:
            del self.fields["product_context"]

        assignee_field = self.fields["assignee"]
        # The assignee requirement is done in the `self.clean()` method.
        # We do not enforce it on the HTML side since it can be automatically
        # set to self on "Saving Draft"
        assignee_field.required = False
        assignee_field.queryset = assignee_field.queryset.scope(self.user.dataspace)
        if request_template.default_assignee:
            assignee_field.initial = request_template.default_assignee

        priority_field = self.fields["priority"]
        priority_field.queryset = priority_field.queryset.scope(self.user.dataspace)

        self.questions = request_template.questions.all()
        self.add_question_fields()

    def set_applies_to_view_link(self, content_object=None):
        if content_object:
            absolute_url = content_object.get_absolute_url()
            style = ""
        else:
            absolute_url = ""
            style = "display: none;"

        initial_label = self.fields["applies_to"].label
        view_object_link_template = (
            '{} <a href="{}" style="{}" id="id_applies_to_link" target="_blank" '
            '   title="View object" data-bs-toggle="tooltip" aria-label="View object">'
            '<i class="fas fa-external-link-alt ms-1"></i>'
            "</a>"
        )
        view_object_link = format_html(
            view_object_link_template, initial_label, absolute_url, style
        )
        self.fields["applies_to"].label = view_object_link

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_tag = False
        helper.form_method = "post"
        helper.form_id = "workflow-request-form"

        question_fields = [
            Field(field) for field in self.fields.keys() if field not in self._meta.fields
        ]

        helper.layout = Layout(
            Fieldset(
                None,
                "title",
                *question_fields,
            ),
            HTML("<hr>"),
            Fieldset(
                None,
                Button("cancel", _("Cancel"), css_class="btn-secondary"),
                Div(
                    submit_as_private,
                    save_draft if self.is_addition else None,
                    StrictSubmit("submit", _("Submit"), css_class="btn-success"),
                    css_class="float-end",
                ),
            ),
        )

        return helper

    @property
    def helper_right_side(self):
        helper = FormHelper()
        helper.form_tag = False

        requester_html = ""
        if self.instance.id:
            requester = self.instance.requester
            created_date = naturaltime(self.instance.created_date)
            requester_html = (
                f"<hr>"
                f'<div class="small-label mb-3">'
                f"Created by <strong>{requester}</strong> {created_date}"
                f"</div>"
            )

        request_fields = [
            Field(field)
            for field in self._meta.fields
            if field in self.fields.keys() and field != "title"
        ]

        helper.layout = Layout(
            Fieldset(
                None,
                *request_fields,
                HTML(requester_html),
                css_class="right-side",
            )
        )

        return helper

    def add_question_fields(self):
        """
        Create fields on this form instance from the list of questions assigned
        to the RequestTemplate.
        """
        initial_data_as_dict = self.instance.get_serialized_data() if self.instance.id else {}

        for question in self.questions:
            extra = None
            if question.input_type == "TextField":
                question.input_type = "CharField"
                extra = {"widget": forms.Textarea(attrs={"rows": 2})}
            if question.input_type == "BooleanField":
                # Using a Select on purpose to make the Yes/No choice more clear
                question.input_type = "ChoiceField"
                choices = (
                    (1, "Yes"),
                    (0, "No"),
                )
                extra = {
                    "choices": choices,
                    "widget": forms.Select,
                }
            if question.input_type == "DateField":
                extra = {
                    "widget": DatePicker,
                    "error_messages": {
                        "invalid": _("Enter a valid date: YYYY-MM-DD."),
                    },
                }

            field_class = getattr(fields, question.input_type, None)
            if not field_class:
                continue

            field_args = {
                "label": question.label,
                "required": question.is_required,
                "help_text": question.help_text,
            }

            if extra:
                field_args.update(extra)

            value = initial_data_as_dict.get(question.label)
            if value:
                # Set proper type to avoid `field.has_changed` failure to compare
                if question.input_type == "DateField":
                    value = parse_date(value)
                field_args.update({"initial": value})

            key = f"field_{question.position}"
            self.fields[key] = field_class(**field_args)

    def set_content_object(self, object_id):
        """
        If an object_id is given when GETing the view, the validity of this id
        is checked on Form initialization.
        It's also validated on Form submission, using the usual clean_ methods.
        """
        if not object_id or not self.request_template.include_applies_to:
            return

        content_type = self.request_template.content_type
        pk_field = "uuid" if len(object_id) == 36 else "id"
        filters = {
            "dataspace": self.user.dataspace,
            pk_field: object_id,
        }

        try:
            self.content_object = content_type.get_object_for_this_type(**filters)
        except ObjectDoesNotExist:
            # Instance with this id does not exists or not in the user dataspace
            return
        return object_id

    def clean_object_id(self):
        object_id = self.cleaned_data.get("object_id")

        if not object_id or not self.request_template.include_applies_to:
            return

        if not self.set_content_object(object_id):
            self.add_error("applies_to", "Invalid value.")
            raise forms.ValidationError("Invalid value.")

        return object_id

    def clean(self):
        cleaned_data = super().clean()

        assignee = self.cleaned_data.get("assignee")
        is_draft = "save_draft" in self.data
        if not assignee and not is_draft:
            self.add_error("assignee", "This field is required.")

        applies_to = self.cleaned_data.get("applies_to")
        object_id = self.cleaned_data.get("object_id")
        content_object = getattr(self, "content_object", "")

        conditions = [
            applies_to and not object_id,
            applies_to and applies_to != str(content_object),
        ]

        if any(conditions):
            self.add_error("applies_to", "Invalid value.")

        permission_error_msg = "{} does not have the permission to view {}"
        product_context = self.cleaned_data.get("product_context")
        if assignee and product_context and not assignee.has_perm("view_product", product_context):
            self.add_error("assignee", permission_error_msg.format(assignee, product_context))

        if assignee and content_object:
            manager = content_object.__class__._default_manager
            if is_secured(manager) and not assignee.has_perm("view_product", content_object):
                self.add_error("assignee", permission_error_msg.format(assignee, content_object))

        return cleaned_data

    def save(self, *args, **kwargs):
        content_object = getattr(self, "content_object", None)
        # Set content_object rather than object_id so instance.content_object
        # is available in further processing (required in notifications)
        if content_object:
            self.instance.content_object = self.content_object
        else:  # Remove the content_object
            self.instance.object_id = None

        serialized_data = {}
        for q in self.questions:
            cleaned_value = self.cleaned_data.get(f"field_{q.position}")
            # str Convert the datetime object in a string
            # None is stored as empty string rather than str(None)
            value = str(cleaned_value) if cleaned_value is not None else ""
            serialized_data[q.label] = value
        self.instance.serialized_data = json.dumps(serialized_data)

        # Protect those fields value on edition
        if not self.instance.id:
            self.instance.requester = self.user
            self.instance.dataspace = self.user.dataspace
            self.instance.request_template = self.request_template
        else:
            self.instance.last_modified_by = self.user

        if "submit_as_private" in self.data:
            self.instance.is_private = True

        if "save_draft" in self.data:
            self.instance.assignee = self.user
            self.instance.status = Request.Status.DRAFT

        instance = super().save(*args, **kwargs)

        product = self.cleaned_data.get("product_context")
        model_name = self.request_template.content_type.model
        do_assign_objects = all(
            [
                self.is_addition,
                content_object,
                self.cleaned_data.get("add_object_to_product"),
                product and product.can_be_changed_by(self.user),
                model_name in ["component", "package"],
                self.user.has_perm(f"product_portfolio.add_product{model_name}"),
            ]
        )
        if do_assign_objects:
            product.assign_objects([content_object], self.user)

        return instance


class RequestAttachmentForm(forms.ModelForm):
    SUBMIT_VALUE = _("Upload")
    # `max_upload_size` is not provided, the MAX_UPLOAD_SIZE settings value is used.
    file = SmartFileField()

    class Meta:
        model = RequestAttachment
        fields = ["file"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        if not self.user:
            raise AttributeError("User is required.")

        self.request_instance = kwargs.pop("request_instance")
        if not self.request_instance:
            raise AttributeError("A Request instance is required.")

        super().__init__(*args, **kwargs)

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_method = "post"
        helper.form_id = "request-attachment-form"
        helper.form_show_labels = False
        helper.form_class = "no-margin"
        helper.attrs = {
            "autocomplete": "off",
        }
        helper.layout = Layout(
            "file",
            Submit("submit", self.SUBMIT_VALUE, css_class="btn-success"),
        )
        return helper

    def save(self, *args, **kwargs):
        # Do not change those values on edition
        if not self.instance.id:
            self.instance.dataspace = self.user.dataspace
            self.instance.uploader = self.user
            self.instance.request = self.request_instance

        return super().save(*args, **kwargs)
