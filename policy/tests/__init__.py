#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.contrib.contenttypes.models import ContentType

from dje.tests import make_string
from policy.models import AssociatedPolicy
from policy.models import UsagePolicy


def make_usage_policy(dataspace, model, **data):
    """Create a policy for test purposes."""
    if "label" not in data:
        data["label"] = f"policy-{make_string(10)}"

    policy = UsagePolicy.objects.create(
        dataspace=dataspace,
        content_type=ContentType.objects.get_for_model(model),
        icon="icon",
        **data,
    )

    return policy


def make_associated_policy(from_policy, to_policy):
    return AssociatedPolicy.objects.create(
        from_policy=from_policy,
        to_policy=to_policy,
        dataspace=from_policy.dataspace,
    )
