#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from django import forms
from django.forms.widgets import HiddenInput
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

# TODO: Add as a dependency
import altcha
from altcha import ChallengeOptions
from altcha import create_challenge

ALTCHA_HMAC_KEY = "your-altcha-hmac-key"


class AltchaWidget(HiddenInput):
    template_name = "widgets/altcha.html"
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

    def __init__(self, *args, **kwargs):
        widget_options = {key: kwargs.pop(key, None) for key in AltchaWidget.default_options}
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


def get_altcha_challenge():
    # Create the challenge using your options
    challenge = create_challenge(
        ChallengeOptions(
            hmac_key=ALTCHA_HMAC_KEY,
            max_number=50000,
        )
    )
    return challenge


@require_GET
def get_altcha_challenge_view(request):
    try:
        challenge = get_altcha_challenge()
        return JsonResponse(challenge.__dict__)
    except Exception as e:
        return JsonResponse({"error": f"Failed to create challenge: {str(e)}"}, status=500)
