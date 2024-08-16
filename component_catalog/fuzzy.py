#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import operator
import re
from difflib import SequenceMatcher
from functools import reduce

from django.db import models

import django_filters


class FuzzyPackageNameSearch(django_filters.CharFilter):
    threshold = 0.4
    help_text = "Fuzzy matching on the name."

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", self.help_text)
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value:
            return qs

        search_values = self.create_search_names(value)
        or_queries = [models.Q(filename__icontains=value)
                      for value in search_values]
        if or_queries:
            potential_packages = qs.filter(reduce(operator.or_, or_queries))
            pks = list(self.fuzzy_match_packages(
                value, potential_packages, self.threshold))
            # Duplicated query since the output need to be a QuerySet instance while
            # fuzzy_match_packages() function return an iterable.
            qs = qs.filter(pk__in=pks)

        return qs

    @staticmethod
    def create_search_names(filename):
        version_extension_pattern = r"[-_](\d.+)\.\w+|\.\w+"
        split_filename = re.split(version_extension_pattern, filename)
        basename = split_filename[0]
        # We are assuming that the regex pattern did its job and the second
        # element in the list is either a version number or None. None is a
        # possible value because when there is no version number in the package
        # name, the regex splits on the file extension but does not capture it,
        # so the second element in the list is None.

        if len(split_filename) > 2 and split_filename[1]:
            version = split_filename[1]
            basename_version = basename + " " + version
            return filename, basename_version, basename
        else:
            return filename, basename

    @staticmethod
    def fuzzy_match_packages(filename, potential_packages, threshold):
        """
        For every Package that may be a potential match, the Package filename is
        compared to the initial package filename that the user queried DejaCode with.

        If the ratio of similarity of a Package's filename when compared to the initial
        package name is above the user provided threshold, that Package is yielded.
        """
        for package in potential_packages:
            ratio = SequenceMatcher(None, filename, package.filename).ratio()
            if ratio > threshold:
                yield package.pk
