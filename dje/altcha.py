#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


from django import forms
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

# TODO: Add as a dependency
import altcha
from altcha import ChallengeOptions
from altcha import create_challenge
from django.forms.widgets import HiddenInput

ALTCHA_HMAC_KEY = "your-altcha-hmac-key"


class AltchaWidget(HiddenInput):
    template_name = "widgets/altcha.html"

    def __init__(self, challengeurl=None, floating=False, attrs=None):
        super().__init__(attrs)
        self.challengeurl = challengeurl
        self.floating = floating

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["challengeurl"] = self.challengeurl
        context["widget"]["floating"] = self.floating
        return context


class AltchaField(forms.Field):
    widget = AltchaWidget
    default_error_messages = {
        "error": _("Failed to process CAPTCHA token"),
        "invalid": _("Invalid CAPTCHA token."),
        "required": _("Altcha CAPTCHA token is missing."),
    }

    def __init__(self, challengeurl=None, floating=False, *args, **kwargs):
        kwargs["widget"] = AltchaWidget(challengeurl=challengeurl, floating=floating)
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
