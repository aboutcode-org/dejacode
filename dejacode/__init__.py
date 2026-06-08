#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import os
import shutil
import subprocess
import sys
import warnings
from contextlib import suppress
from pathlib import Path

VERSION = "5.8.0"

PROJECT_DIR = Path(__file__).resolve().parent
ROOT_DIR = PROJECT_DIR.parent


def get_version(version):
    """Return the version including the git describe tag when available."""
    # The codebase is a git clone
    if git_describe := get_git_describe_from_local_checkout():
        return git_describe

    # The codebase is an extracted git archive
    if git_describe := get_git_describe_from_version_file():
        return git_describe

    return version


def run_command_safely(command_args):
    """
    Execute an external command and return its stdout.

    Runs without a shell (shell=False) to prevent injection vulnerabilities.

    Usage notes:
    - Provide the command as a list of arguments.
    - Use full executable paths to avoid ambiguity.
    - Use the "--option=value" form, or split it as two list entries
      ["--option", "value"], but never join an option and its value in a
      single entry ("--option value").
    - Sanitize and validate any user input before passing it in.

    Raise a SubprocessError if the exit code is non-zero.
    """
    completed_process = subprocess.run(  # noqa: S603
        command_args,
        capture_output=True,
        text=True,
    )
    if completed_process.returncode:
        error_msg = (
            f'Error while executing cmd="{completed_process.args}": '
            f'"{completed_process.stderr.strip()}"'
        )
        raise subprocess.SubprocessError(error_msg)
    return completed_process.stdout


def get_git_describe_from_local_checkout():
    """
    Return the git describe tag from the local checkout.
    This will only provide a result when the codebase is a git clone.
    """
    git_executable = shutil.which("git")
    if not git_executable:
        return

    with suppress(subprocess.SubprocessError):
        git_describe = run_command_safely([git_executable, "describe", "--tags", "--always"])
        return git_describe.strip()


def get_git_describe_from_version_file(version_file_location=ROOT_DIR / ".VERSION"):
    """
    Return the git describe tag from the ".VERSION" file.
    This will only provide a result when the codebase is an extracted git archive
    """
    try:
        version = version_file_location.read_text().strip()
    except (FileNotFoundError, UnicodeDecodeError):
        return

    if version and version.startswith("v"):
        return version


__version__ = get_version(VERSION)


# Turn off the warnings for the following modules.
warnings.filterwarnings("ignore", module="cyclonedx")
warnings.filterwarnings("ignore", module="clamd")
warnings.filterwarnings("ignore", category=FutureWarning, module="rq_scheduler.utils")
warnings.filterwarnings("ignore", category=FutureWarning, module="django.forms.formsets")


def command_line():
    """Command line entry point."""
    from django.core.management import execute_from_command_line

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dejacode.settings")
    execute_from_command_line(sys.argv)
