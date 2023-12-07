#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
import zipfile
from collections import defaultdict
from pathlib import Path

from django.core.management.base import CommandError

import requests
from defusedxml import ElementTree

from component_catalog.models import Component
from dje.management.commands import DataspacedCommand


class Command(DataspacedCommand):
    help = (
        "Collects CPEs from the official CPE dictionary and set the cpe field value "
        "when matches with DejaCode Components are found."
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "cpe_dictionary_location",
            help=(
                "Local path on the disk of an official CPE dictionary as XML.\n"
                "An URL pointing to a zipped XML is also supported, for example: "
                "https://nvd.nist.gov/feeds/xml/cpe/dictionary/official-cpe-dictionary_v2.3.xml.zip"
            ),
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        cpe_dictionary_location = options["cpe_dictionary_location"]

        if cpe_dictionary_location.startswith("http"):
            self.stdout.write("Downloading the CPE dictionary...")
            xml_content = self.load_cpe_from_url(url=cpe_dictionary_location)
        else:
            self.stdout.write("Loading the CPE dictionary from disk...")
            xml_content = self.load_cpe_from_disk(cpe_dictionary_location)

        self.stdout.write("Extracting the CPE names from XML content...")
        root = ElementTree.fromstring(xml_content)
        cpe_element_schema = "{http://scap.nist.gov/schema/cpe-extension/2.3}cpe23-item"

        cpe_names = []
        for child in root:
            for cpe23_item in child.findall(cpe_element_schema):
                cpe_name = cpe23_item.attrib.get("name")
                cpe_names.append(cpe_name)

        cpes_count = len(cpe_names)
        self.stdout.write(f"Building an index of {cpes_count} CPEs for matching...")
        cpe_index = self.build_cpe_index(cpe_names)

        component_updated_count = 0
        component_qs = Component.objects.scope(self.dataspace).filter(cpe="")

        self.stdout.write(
            f"Matching {component_qs.count()} Components from the DejaCode catalog "
            f"against the index of {cpes_count} CPEs..."
        )
        for component in component_qs:
            component_name = self.normalize_name(component.name)
            component_version = self.normalize_version(component.version)

            name_match = cpe_index.get(component_name)
            if name_match:
                version_match = name_match.get(component_version)

                if version_match:
                    component_updated_count += 1
                    Component.objects.filter(id=component.id).update(cpe=version_match)

        msg = f"{component_updated_count} Component(s) updated."
        self.stdout.write(self.style.SUCCESS(msg))

    @staticmethod
    def normalize_name(name):
        """
        Return a normalized name replacing empty spaces, the "-" char,
        and lowering the whole string.
        """
        return name.replace(" ", "_").replace("-", "_").lower()

    @staticmethod
    def normalize_version(version):
        """
        Return a normalized version replacing empty spaces, the "-" char,
        and lowering the whole string.
        Also, null version in the cpe system are declared with the '-' char,
        this is replaced by empty string representing null version on the DejaCode side.
        If the version ends with ".0", this bit is removed so we can match on version where
        the ".0" is not present on the cpe side or DejaCode side.
        For example: "3.2" on the cpe side will match "3.2.0" on the DejaCode side once the
        normalization is applied.
        """
        if version == "-":
            return ""

        return version.replace(" ", "_").replace("-", "_").lower().removesuffix(".0")

    @staticmethod
    def load_cpe_from_disk(cpe_dictionary_location):
        """Return the XML content of the file at `cpe_dictionary_location`."""
        cpe_dictionary_path = Path(cpe_dictionary_location)
        if not cpe_dictionary_path.exists():
            raise CommandError(f"{cpe_dictionary_location} not found.")

        xml_content = cpe_dictionary_path.read_text()
        return xml_content

    @staticmethod
    def load_cpe_from_url(url):
        """Return the XML content of the zipfile downloaded from `url`."""
        response = requests.get(url, timeout=10)

        try:
            response.raise_for_status()
        except requests.RequestException as e:
            raise CommandError(e)

        zip_document = zipfile.ZipFile(io.BytesIO(response.content))
        namelist = zip_document.namelist()

        if len(namelist) != 1 and not namelist[0].endswith("xml"):
            raise CommandError("CPE dictionary .xml file not found in .zip")

        xml_content = zip_document.read(name=namelist[0])
        return xml_content

    def build_cpe_index(self, cpe_names):
        """
        Build an index of CPEs as a dictionary keyed by `name`.
        Format:
        {
            'component_name': {
                'version_1': 'cpe',
                'version_2': 'cpe',
            }
        }
        """
        cpe_index = defaultdict(dict)

        for cpe in cpe_names:
            cpe_parts = cpe.split(":")
            _, name, version = cpe_parts[3], cpe_parts[4], cpe_parts[5]
            name = self.normalize_name(name)
            version = self.normalize_version(version)
            cpe_index[name][version] = cpe

        return cpe_index
