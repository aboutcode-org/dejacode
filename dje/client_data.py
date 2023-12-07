#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#


def add_client_data(request, **kwargs):
    """
    Set values on the request, to be available in the JavaScript client data object.
    On the client side, the values are accessible through ``NEXB.client_data``.
    """
    if not hasattr(request, 'client_data'):
        request.client_data = {}
    request.client_data.update(kwargs)


def client_data_context_processor(request):
    client_data = getattr(request, 'client_data', {})
    return {'client_data': client_data}
