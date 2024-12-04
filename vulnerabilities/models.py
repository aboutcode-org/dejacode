#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import decimal
import logging

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from cyclonedx.model import vulnerability as cdx_vulnerability

from dje.fields import JSONListField
from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import HistoryDateFieldsMixin
from dje.models import HistoryUserFieldsMixin

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

    def order_by_risk(self):
        return self.order_by(
            models.F("risk_score").desc(nulls_last=True),
            models.F("weighted_severity").desc(nulls_last=True),
            models.F("exploitability").desc(nulls_last=True),
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
    resource_url = models.URLField(
        _("Resource URL"),
        max_length=1024,
        blank=True,
        help_text=_("URL of the data source for this Vulnerability."),
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
    EXPLOITABILITY_CHOICES = [
        (0.5, _("No exploits known")),
        (1.0, _("Potential exploits")),
        (2.0, _("Known exploits")),
    ]
    exploitability = models.DecimalField(
        null=True,
        blank=True,
        max_digits=2,
        decimal_places=1,
        choices=EXPLOITABILITY_CHOICES,
        help_text=_(
            "Exploitability refers to the potential or probability of a software "
            "package vulnerability being exploited by malicious actors to compromise "
            "systems, applications, or networks. "
            "It is determined automatically by discovery of exploits."
        ),
    )
    weighted_severity = models.DecimalField(
        null=True,
        blank=True,
        max_digits=3,
        decimal_places=1,
        help_text=_(
            "Weighted severity is the highest value calculated by multiplying each "
            "severity by its corresponding weight, divided by 10."
        ),
    )
    risk_score = models.DecimalField(
        null=True,
        blank=True,
        max_digits=3,
        decimal_places=1,
        help_text=_(
            "Risk score from 0.0 to 10.0, with higher values indicating greater "
            "vulnerability risk. "
            "This score is the maximum of the weighted severity multiplied by "
            "exploitability, capped at 10."
        ),
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

    @classmethod
    def create_from_data(cls, dataspace, data, validate=False, affecting=None):
        instance = super().create_from_data(user=dataspace, data=data, validate=False)

        if affecting:
            instance.add_affected(affecting)

        return instance

    def as_cyclonedx(self, affected_instances, analysis=None):
        affects = [
            cdx_vulnerability.BomTarget(ref=instance.cyclonedx_bom_ref)
            for instance in affected_instances
        ]

        analysis = analysis.as_cyclonedx() if analysis else None

        source = cdx_vulnerability.VulnerabilitySource(
            name="VulnerableCode",
            url=self.resource_url,
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
            analysis=analysis,
        )


class VulnerabilityAnalysisMixin(models.Model):
    """Aligned with the cyclonedx.model.vulnerability.VulnerabilityAnalysis"""

    # cyclonedx.model.impact_analysis.ImpactAnalysisState
    class State(models.TextChoices):
        RESOLVED = "resolved"
        RESOLVED_WITH_PEDIGREE = "resolved_with_pedigree"
        EXPLOITABLE = "exploitable"
        IN_TRIAGE = "in_triage"
        FALSE_POSITIVE = "false_positive"
        NOT_AFFECTED = "not_affected"

    # cyclonedx.model.impact_analysis.ImpactAnalysisJustification
    class Justification(models.TextChoices):
        CODE_NOT_PRESENT = "code_not_present"
        CODE_NOT_REACHABLE = "code_not_reachable"
        PROTECTED_AT_PERIMETER = "protected_at_perimeter"
        PROTECTED_AT_RUNTIME = "protected_at_runtime"
        PROTECTED_BY_COMPILER = "protected_by_compiler"
        PROTECTED_BY_MITIGATING_CONTROL = "protected_by_mitigating_control"
        REQUIRES_CONFIGURATION = "requires_configuration"
        REQUIRES_DEPENDENCY = "requires_dependency"
        REQUIRES_ENVIRONMENT = "requires_environment"

    # cyclonedx.model.impact_analysis.ImpactAnalysisResponse
    class Response(models.TextChoices):
        CAN_NOT_FIX = "can_not_fix"
        ROLLBACK = "rollback"
        UPDATE = "update"
        WILL_NOT_FIX = "will_not_fix"
        WORKAROUND_AVAILABLE = "workaround_available"

    state = models.CharField(
        max_length=25,
        blank=True,
        choices=State.choices,
        help_text=_(
            "Declares the current state of an occurrence of a vulnerability, "
            "after automated or manual analysis."
        ),
    )
    justification = models.CharField(
        max_length=35,
        blank=True,
        choices=Justification.choices,
        help_text=_("The rationale of why the impact analysis state was asserted."),
    )
    responses = ArrayField(
        models.CharField(
            max_length=20,
            choices=Response.choices,
        ),
        blank=True,
        null=True,
        help_text=_(
            "A response to the vulnerability by the manufacturer, supplier, or project "
            "responsible for the affected component or service. "
            "More than one response is allowed. "
            "Responses are strongly encouraged for vulnerabilities where the analysis "
            "state is exploitable."
        ),
    )
    detail = models.TextField(
        blank=True,
        help_text=_(
            "Detailed description of the impact including methods used during assessment. "
            "If a vulnerability is not exploitable, this field should include specific "
            "details on why the component or service is not impacted by this vulnerability."
        ),
    )
    first_issued = models.DateTimeField(
        auto_now_add=True,
        help_text=_("The date and time (timestamp) when the analysis was first issued."),
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text=_("The date and time (timestamp) when the analysis was last updated."),
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # At least one of those fields must be provided.
        main_fields = [
            self.state,
            self.justification,
            self.responses,
            self.detail,
        ]
        if not any(main_fields):
            raise ValueError(
                "At least one of state, justification, responses or detail must be provided."
            )

        super().save(*args, **kwargs)

    def as_cyclonedx(self):
        state = None
        if self.state:
            state = cdx_vulnerability.ImpactAnalysisState(self.state)

        justification = None
        if self.justification:
            justification = cdx_vulnerability.ImpactAnalysisJustification(self.justification)

        return cdx_vulnerability.VulnerabilityAnalysis(
            state=state,
            justification=justification,
            responses=self.responses,
            detail=self.detail,
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
    # Based on vulnerablecode.vulnerabilities.models.Package
    risk_score = models.DecimalField(
        null=True,
        blank=True,
        max_digits=3,
        decimal_places=1,
        help_text=_(
            "Risk score between 0.0 and 10.0, where higher values "
            "indicate greater vulnerability risk for the package."
        ),
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


class VulnerabilityAnalysis(
    VulnerabilityAnalysisMixin,
    HistoryUserFieldsMixin,
    DataspacedModel,
):
    product_package = models.ForeignKey(
        to="product_portfolio.ProductPackage",
        on_delete=models.CASCADE,
        related_name="vulnerability_analyses",
        help_text=_("The ProductPackage relationship being analyzed."),
    )
    vulnerability = models.ForeignKey(
        to="vulnerabilities.Vulnerability",
        on_delete=models.CASCADE,
        related_name="vulnerability_analyses",
        help_text=_("The vulnerability being analyzed in the context of the ProductPackage."),
    )
    # Shortcut fields to simplify QuerySets filtering
    product = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.CASCADE,
        related_name="vulnerability_analyses",
    )
    package = models.ForeignKey(
        to="component_catalog.Package",
        on_delete=models.CASCADE,
        related_name="vulnerability_analyses",
    )

    class Meta:
        unique_together = (("product_package", "vulnerability"), ("dataspace", "uuid"))
        indexes = [
            models.Index(fields=["state"]),
            models.Index(fields=["justification"]),
        ]

    def __str__(self):
        return f"{self.vulnerability} analysis"

    def save(self, *args, **kwargs):
        """Set the product and package fields values from the product_package FK."""
        self.product_id = self.product_package.product_id
        self.package_id = self.product_package.package_id
        super().save(*args, **kwargs)

    def propagate(self, product_uuid, user):
        """Propagate this Analysis to another Product."""
        from product_portfolio.models import ProductPackage

        # Get the equivalent ProductPackage in the target product.
        try:
            product_package = ProductPackage.objects.get(
                product__uuid=product_uuid,
                package=self.package,
                dataspace=self.dataspace,
            )
        except models.ObjectDoesNotExist:
            return

        target_analysis_base_data = {
            "product_package": product_package,
            "vulnerability": self.vulnerability,
            "dataspace": self.dataspace,
        }

        if VulnerabilityAnalysis.objects.filter(**target_analysis_base_data).exists():
            return  # Update not yet supported.

        target_analysis = VulnerabilityAnalysis(
            **target_analysis_base_data,
            created_by=user,
            last_modified_by=user,
        )

        fields_to_clone = [
            "state",
            "justification",
            "responses",
            "detail",
        ]
        for field_name in fields_to_clone:
            field_value = getattr(self, field_name, None)
            if field_value is not None:
                setattr(target_analysis, field_name, field_value)

        target_analysis.save()
        return target_analysis
