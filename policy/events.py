#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from notification.models import fire_webhooks

POLICY_EVENTS = {
    "policy.license_alert": "License-related policy rule violation detected or resolved.",
    "policy.security_alert": "Security-related policy rule violation detected or resolved.",
    "policy.compliance_alert": "Any policy rule violation detected or resolved.",
}


def fire_event(event_name, dataspace, payload):
    """Dispatch a policy event to all registered notification channels."""
    fire_webhooks(event_name, instance=None, dataspace=dataspace, payload_override=payload)
