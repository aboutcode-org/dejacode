#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from contextlib import suppress

from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import validators
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML
from crispy_forms.layout import Div
from crispy_forms.layout import Field
from crispy_forms.layout import Fieldset
from crispy_forms.layout import Layout
from django_registration.backends.activation.views import ActivationView
from django_registration.exceptions import ActivationError
from django_registration.forms import RegistrationFormUniqueEmail
from hcaptcha_field import hCaptchaField

from dje.forms import StrictSubmit
from dje.models import Dataspace
from dje.models import History
from dje.tasks import send_mail_to_admins_task

User = get_user_model()
REGISTRATION_DEFAULT_DATASPACE = "Evaluation"
REGISTRATION_DEFAULT_IS_STAFF = True
REGISTRATION_DEFAULT_GROUPS = (
    "Trial-View",
    "Trial-Level-1",
)


class DejaCodeActivationView(ActivationView):
    def get_success_url(self, user=None):
        """Add support for 'Sign Up' registration and User creation in admin."""
        if user.has_usable_password():
            # User created from registration process
            return self.success_url

        # User created in the admin addition view
        return self.get_password_reset_confirm_url(user)

    @staticmethod
    def get_password_reset_confirm_url(user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(user)
        return reverse("password_reset_confirm", args=(uid, token))

    def get_user(self, username):
        """
        Remove the `already_activated` exception from original method.

        The activation link is valid and usable until the
        `ACCOUNT_ACTIVATION_DAYS` period is expired.

        This is required, for a user created by an admin user, to reach
        the "set password" form even if the activation URL was already
        requested (by an email service for example).
        """
        User = get_user_model()
        try:
            user = User.objects.get(
                **{
                    User.USERNAME_FIELD: username,
                }
            )
            return user
        except User.DoesNotExist:
            raise ActivationError(
                self.BAD_USERNAME_MESSAGE, code="bad_username")


class DejaCodeRegistrationForm(RegistrationFormUniqueEmail):
    """Used in `registration.backends.hmac.views.RegistrationView`."""

    use_required_attribute = False
    hcaptcha = hCaptchaField()

    class Meta(RegistrationFormUniqueEmail.Meta):
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "company",
            "password1",
            "hcaptcha",
            "updates_email_notification",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "password2" in self.fields:
            del self.fields["password2"]

        self.fields["username"].validators.append(
            validators.MinLengthValidator(3))

        placeholders = {
            "username": _("Username"),
            "email": _("Email address"),
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "company": _("Company"),
            "password1": _("Choose a password"),
        }
        for field_name, placeholder in placeholders.items():
            self.fields[field_name].widget.attrs["placeholder"] = placeholder

        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["company"].required = True

        self.fields["hcaptcha"].label = ""

        notification_label = "Receive updates on DejaCode features and news"
        self.fields["updates_email_notification"].label = notification_label

        for field in self.fields.values():
            field.help_text = None

    @property
    def helper(self):
        helper = FormHelper()
        helper.form_id = "registration"
        helper.form_method = "post"
        helper.form_action = "django_registration_register"
        helper.attrs = {"autocomplete": "off"}

        tos = HTML(
            '<p class="fw-bolder mb-2">'
            '  By clicking on "Create account" below, you are agreeing to our '
            '  <a href="https://nexb.com/dejacode-com-tos/" target="blank">Terms of Service</a>.'
            "</p>"
        )

        helper.layout = Layout(
            Fieldset(
                None,
                Field("username", css_class="input-block-level"),
                Field("email", css_class="input-block-level"),
                Div(
                    Div(Field("first_name"), css_class="col ps-0"),
                    Div(Field("last_name"), css_class="col pe-0"),
                    css_class="row m-0",
                ),
                Field("company", css_class="input-block-level"),
                Field(
                    "password1",
                    css_class="input-block-level",
                    autocomplete="new-password",
                ),
                Div(
                    Field("updates_email_notification"),
                    css_class="alert alert-primary px-2",
                ),
                "hcaptcha",
                tos,
                Div(
                    StrictSubmit(
                        "submit",
                        _("Create your account"),
                        css_class="btn btn-warning",
                    ),
                    css_class="d-grid",
                ),
            ),
        )

        return helper

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1")
        self.instance.username = self.cleaned_data.get("username")
        password_validation.validate_password(password1, self.instance)
        return password1

    def save(self, commit=True):
        """Add the default Dataspace on the user instance before saving."""
        user = super().save(commit=False)

        user.dataspace, _ = Dataspace.objects.get_or_create(
            name=REGISTRATION_DEFAULT_DATASPACE)
        user.is_active = False
        if REGISTRATION_DEFAULT_IS_STAFF:
            user.is_staff = True
        user.save()

        for group_name in REGISTRATION_DEFAULT_GROUPS:
            with suppress(Group.DoesNotExist):
                user.groups.add(Group.objects.get(name=group_name))

        self.send_notification_email_to_admins(user)
        History.log_addition(user, user)
        return user

    @staticmethod
    def send_notification_email_to_admins(user):
        subject = "[DejaCode] New User registration"
        message = f"New registration for user {user.username} {user.email}"
        send_mail_to_admins_task.delay(subject, message)
