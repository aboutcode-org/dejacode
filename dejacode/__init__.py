#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import os
import sys
import warnings

VERSION = "5.1.0-dev"
__version__ = VERSION

# Turn off the warnings for the following modules.
warnings.filterwarnings("ignore", module="cyclonedx")


def command_line():
    """Command line entry point."""
    from django.core.management import execute_from_command_line

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dejacode.settings")
    execute_from_command_line(sys.argv)
