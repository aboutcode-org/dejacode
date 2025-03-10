#
# Copyright (c) nexB Inc. and others. All rights reserved.
# SPDX-License-Identifier: MIT
# See https://github.com/aboutcode-org/django-altcha for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import secrets

from django import forms
from django.conf import settings
from django.forms.widgets import HiddenInput
from django.utils.translation import gettext_lazy as _

# TODO: Add as a dependency
import altcha

"""
1. Add "to INSTALLED_APPS:

INSTALLED_APPS = [
    # ...
    "django_altcha"
]

2. Add the field on your forms:

from django_altcha import AltchaField

class Form(forms.Form):
    captcha = AltchaField()


You can provide any configuration options available at
https://altcha.org/docs/website-integration/ such as:

class Form(forms.Form):
    captcha = AltchaField(
        floating=True,
        debug=True,
        # ...
    )
"""

# Get the ALTCHA_HMAC_KEY from the settings, or generate one if not present
ALTCHA_HMAC_KEY = getattr(settings, "ALTCHA_HMAC_KEY", secrets.token_hex(32))


def get_altcha_challenge():
    """Return an ALTCHA challenge."""
    challenge = altcha.create_challenge(
        altcha.ChallengeOptions(
            hmac_key=ALTCHA_HMAC_KEY,
            max_number=50000,
        )
    )
    return challenge


class AltchaWidget(HiddenInput):
    template_name = "altcha_widget.html"
    default_options = {
        # Required: URL of your server to fetch the challenge from.
        "challengeurl": None,
        # Required: JSON-encoded challenge data
        # (use instead of challengeurl to avoid HTTP request).
        "challengejson": None,
        # Automatically verify without user interaction.
        # Possible values: "off", "onfocus", "onload", "onsubmit".
        "auto": None,
        # Artificial delay before verification (in milliseconds, default: 0).
        "delay": None,
        # Challenge expiration duration (in milliseconds).
        "expire": None,
        # Enable floating UI.
        # Possible values: "auto", "top", "bottom".
        "floating": None,
        # CSS selector of the “anchor” to which the floating UI is attached.
        # Default: submit button in the related form.
        "floatinganchor": None,
        # Y offset from the anchor element for the floating UI (in pixels, default: 12).
        "floatingoffset": None,
        # Hide the footer (ALTCHA link).
        "hidefooter": None,
        # Hide the ALTCHA logo.
        "hidelogo": None,
        # Max number to iterate to (default: 1,000,000).
        "maxnumber": None,
        # JSON-encoded translation strings for customization.
        "strings": None,
        # Automatically re-fetch and re-validate when the challenge expires
        # (default: true).
        "refetchonexpire": None,
        # Number of workers for Proof of Work (PoW).
        # Default: navigator.hardwareConcurrency or 8 (max value: 16).
        "workers": None,
        # URL of the Worker script (default: ./worker.js, only for external builds).
        "workerurl": None,
        # Print log messages in the console (for debugging).
        "debug": None,
        # Causes verification to always fail with a "mock" error.
        "mockerror": None,
        # Generates a “mock” challenge within the widget, bypassing the request to
        # challengeurl.
        "test": None,
    }

    def __init__(self, **kwargs):
        """Initialize the ALTCHA widget with configurable options."""
        super().__init__()
        self.options = {
            key: kwargs.get(key, self.default_options[key]) for key in self.default_options
        }

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["altcha_options"] = self.options  # Pass options to template
        return context


class AltchaField(forms.Field):
    widget = AltchaWidget
    default_error_messages = {
        "error": _("Failed to process CAPTCHA token"),
        "invalid": _("Invalid CAPTCHA token."),
        "required": _("Altcha CAPTCHA token is missing."),
    }

    # TODO: This is only called once on Form declaration.
    # Making the challenge always the same.
    def __init__(self, *args, **kwargs):
        challengeurl = kwargs.pop("challengeurl", None)
        challengejson = kwargs.pop("challengejson", None)

        # If no ``challengeurl`` is provided, auto-generate ``challengejson``
        if challengeurl is None and challengejson is None:
            challenge = get_altcha_challenge()
            challengejson = json.dumps(challenge.__dict__)

        # Prepare widget options
        widget_options = {
            "challengeurl": challengeurl,
            "challengejson": challengejson,
        }

        # Include any other ALTCHA options passed
        for key in AltchaWidget.default_options:
            if key not in widget_options:
                widget_options[key] = kwargs.pop(key, None)

        # Assign the updated widget
        kwargs["widget"] = AltchaWidget(**widget_options)
        super().__init__(*args, **kwargs)

    def validate(self, value):
        super().validate(value)

        if not value:
            raise forms.ValidationError(self.error_messages["required"], code="required")

        try:
            # Verify the Altcha payload using the token and the secret HMAC key
            verified, error = altcha.verify_solution(
                payload=value,
                hmac_key=ALTCHA_HMAC_KEY,
                check_expires=False,
            )
        except Exception:  # TODO: Catch specific exception
            raise forms.ValidationError(self.error_messages["error"], code="error")

        if not verified:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
