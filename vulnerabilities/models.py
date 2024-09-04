#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import decimal
import logging

from django.db import models
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from cyclonedx.model import vulnerability as cdx_vulnerability

from dje.fields import JSONListField
from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import HistoryDateFieldsMixin

logger = logging.getLogger("dje")


class VulnerabilityQuerySet(DataspacedQuerySet):
    def with_affected_products_count(self):
        """Annotate the QuerySet with the affected_products_count."""
        return self.annotate(
            affected_products_count=Count(
                "affected_packages__productpackages__product", distinct=True
            ),
        )

    def with_affected_packages_count(self):
        """Annotate the QuerySet with the affected_packages_count."""
        return self.annotate(
            affected_packages_count=Count("affected_packages", distinct=True),
        )


class Vulnerability(HistoryDateFieldsMixin, DataspacedModel):
    """
    A software vulnerability with a unique identifier and alternate aliases.

    Adapted from the VulnerableCode models at
    https://github.com/nexB/vulnerablecode/blob/main/vulnerabilities/models.py#L164

    Note that this model implements the HistoryDateFieldsMixin but not the
    HistoryUserFieldsMixin as the Vulnerability records are usually created
    automatically on object addition or during schedule tasks.
    """

    # The first set of fields are storing data as fetched from VulnerableCode
    vulnerability_id = models.CharField(
        max_length=20,
        help_text=_(
            "A unique identifier for the vulnerability, prefixed with 'VCID-'. "
            "For example, 'VCID-2024-0001'."
        ),
    )
    summary = models.TextField(
        help_text=_("A brief summary of the vulnerability, outlining its nature and impact."),
        blank=True,
    )
    aliases = JSONListField(
        blank=True,
        help_text=_(
            "A list of aliases for this vulnerability, such as CVE identifiers "
            "(e.g., 'CVE-2017-1000136')."
        ),
    )
    references = JSONListField(
        blank=True,
        help_text=_(
            "A list of references for this vulnerability. Each reference includes a "
            "URL, an optional reference ID, scores, and the URL for further details. "
        ),
    )
    fixed_packages = JSONListField(
        blank=True,
        help_text=_("A list of packages that are not affected by this vulnerability."),
    )
    fixed_packages_count = models.GeneratedField(
        expression=models.Func(models.F("fixed_packages"), function="jsonb_array_length"),
        output_field=models.IntegerField(),
        db_persist=True,
    )
    min_score = models.FloatField(
        null=True,
        blank=True,
        help_text=_("The minimum score of the range."),
    )
    max_score = models.FloatField(
        null=True,
        blank=True,
        help_text=_("The maximum score of the range."),
    )

    objects = DataspacedManager.from_queryset(VulnerabilityQuerySet)()

    class Meta:
        verbose_name_plural = "Vulnerabilities"
        unique_together = (("dataspace", "vulnerability_id"), ("dataspace", "uuid"))
        indexes = [
            models.Index(fields=["vulnerability_id"]),
        ]

    def __str__(self):
        return self.vulnerability_id

    @property
    def vcid(self):
        return self.vulnerability_id

    def add_affected(self, instances):
        """
        Assign the ``instances`` (Package or Component) as affected to this
        vulnerability.
        """
        from component_catalog.models import Component
        from component_catalog.models import Package

        if not isinstance(instances, list):
            instances = [instances]

        for instance in instances:
            if isinstance(instance, Package):
                self.add_affected_packages([instance])
            if isinstance(instance, Component):
                self.add_affected_components([instance])

    def add_affected_packages(self, packages):
        """Assign the ``packages`` as affected to this vulnerability."""
        through_defaults = {"dataspace_id": self.dataspace_id}
        self.affected_packages.add(*packages, through_defaults=through_defaults)

    def add_affected_components(self, components):
        """Assign the ``components`` as affected to this vulnerability."""
        through_defaults = {"dataspace_id": self.dataspace_id}
        self.affected_components.add(*components, through_defaults=through_defaults)

    @staticmethod
    def range_to_values(self, range_str):
        try:
            min_score, max_score = range_str.split("-")
            return float(min_score.strip()), float(max_score.strip())
        except Exception:
            return

    @classmethod
    def create_from_data(cls, dataspace, data, validate=False, affecting=None):
        # Computing the min_score and max_score from the `references` as those data
        # are not provided by the VulnerableCode API.
        # https://github.com/aboutcode-org/vulnerablecode/issues/1573
        # severity_range_score = data.get("severity_range_score")
        # if severity_range_score:
        #     min_score, max_score = self.range_to_values(severity_range_score)
        #     data["min_score"] = min_score
        #     data["max_score"] = max_score

        severities = [
            score for reference in data.get("references") for score in reference.get("scores", [])
        ]
        if scores := cls.get_severity_scores(severities):
            data["min_score"] = min(scores)
            data["max_score"] = max(scores)

        instance = super().create_from_data(user=dataspace, data=data, validate=False)

        if affecting:
            instance.add_affected(affecting)

        return instance

    @staticmethod
    def get_severity_scores(severities):
        score_map = {
            "low": [0.1, 3],
            "moderate": [4.0, 6.9],
            "medium": [4.0, 6.9],
            "high": [7.0, 8.9],
            "important": [7.0, 8.9],
            "critical": [9.0, 10.0],
        }

        consolidated_scores = []
        for severity in severities:
            score = severity.get("value")
            try:
                consolidated_scores.append(float(score))
            except ValueError:
                if score_range := score_map.get(score.lower(), None):
                    consolidated_scores.extend(score_range)

        return consolidated_scores

    def as_cyclonedx(self, affected_instances):
        affects = [
            cdx_vulnerability.BomTarget(ref=instance.cyclonedx_bom_ref)
            for instance in affected_instances
        ]

        source_url = f"https://public.vulnerablecode.io/vulnerabilities/{self.vulnerability_id}"
        source = cdx_vulnerability.VulnerabilitySource(
            name="VulnerableCode",
            url=source_url,
        )

        references = []
        ratings = []
        for reference in self.references:
            reference_source = cdx_vulnerability.VulnerabilitySource(
                url=reference.get("reference_url"),
            )
            references.append(
                cdx_vulnerability.VulnerabilityReference(
                    id=reference.get("reference_id"),
                    source=reference_source,
                )
            )

            for score_entry in reference.get("scores", []):
                # CycloneDX only support a float value for the score field,
                # where on the VulnerableCode data it can be either a score float value
                # or a severity string value.
                score_value = score_entry.get("value")
                try:
                    score = decimal.Decimal(score_value)
                    severity = None
                except decimal.DecimalException:
                    score = None
                    severity = getattr(
                        cdx_vulnerability.VulnerabilitySeverity,
                        score_value.upper(),
                        None,
                    )

                ratings.append(
                    cdx_vulnerability.VulnerabilityRating(
                        source=reference_source,
                        score=score,
                        severity=severity,
                        vector=score_entry.get("scoring_elements"),
                    )
                )

        return cdx_vulnerability.Vulnerability(
            id=self.vulnerability_id,
            source=source,
            description=self.summary,
            affects=affects,
            references=sorted(references),
            ratings=ratings,
        )


class AffectedByVulnerabilityRelationship(DataspacedModel):
    vulnerability = models.ForeignKey(
        to="vulnerabilities.Vulnerability",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True


class AffectedByVulnerabilityMixin(models.Model):
    """Add the `vulnerability` many to many field."""

    affected_by_vulnerabilities = models.ManyToManyField(
        to="vulnerabilities.Vulnerability",
        related_name="affected_%(class)ss",
        help_text=_("Vulnerabilities affecting this object."),
    )

    class Meta:
        abstract = True

    @property
    def is_vulnerable(self):
        return self.affected_by_vulnerabilities.exists()

    def get_entry_for_package(self, vulnerablecode):
        if not self.package_url:
            return

        vulnerable_packages = vulnerablecode.get_vulnerabilities_by_purl(
            self.package_url,
            timeout=10,
        )

        if vulnerable_packages:
            affected_by_vulnerabilities = vulnerable_packages[0].get("affected_by_vulnerabilities")
            return affected_by_vulnerabilities

    def get_entry_for_component(self, vulnerablecode):
        if not self.cpe:
            return

        # Support for Component is paused as the CPES endpoint do not work properly.
        # https://github.com/aboutcode-org/vulnerablecode/issues/1557
        # vulnerabilities = vulnerablecode.get_vulnerabilities_by_cpe(self.cpe, timeout=10)

    def get_entry_from_vulnerablecode(self):
        from component_catalog.models import Component
        from component_catalog.models import Package
        from dejacode_toolkit.vulnerablecode import VulnerableCode

        dataspace = self.dataspace
        vulnerablecode = VulnerableCode(dataspace)

        is_vulnerablecode_enabled = all(
            [
                vulnerablecode.is_configured(),
                dataspace.enable_vulnerablecodedb_access,
            ]
        )
        if not is_vulnerablecode_enabled:
            return

        if isinstance(self, Component):
            return self.get_entry_for_component(vulnerablecode)
        elif isinstance(self, Package):
            return self.get_entry_for_package(vulnerablecode)

    def fetch_vulnerabilities(self):
        affected_by_vulnerabilities = self.get_entry_from_vulnerablecode()
        if affected_by_vulnerabilities:
            self.create_vulnerabilities(vulnerabilities_data=affected_by_vulnerabilities)

    def create_vulnerabilities(self, vulnerabilities_data):
        vulnerabilities = []
        vulnerability_qs = Vulnerability.objects.scope(self.dataspace)

        for vulnerability_data in vulnerabilities_data:
            vulnerability_id = vulnerability_data["vulnerability_id"]
            vulnerability = vulnerability_qs.get_or_none(vulnerability_id=vulnerability_id)
            if not vulnerability:
                vulnerability = Vulnerability.create_from_data(
                    dataspace=self.dataspace,
                    data=vulnerability_data,
                )
            vulnerabilities.append(vulnerability)

        through_defaults = {"dataspace_id": self.dataspace_id}
        self.affected_by_vulnerabilities.add(*vulnerabilities, through_defaults=through_defaults)
