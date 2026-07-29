from django.db import models

from reporting.models import Query


class DecisionPoint(models.Model):
    """
    A reusable boolean predicate.

    Example:
        Name: High Risk Vulnerability

        Query:
            risk_score >= 8
            exploitability >= 2

    During evaluation this resolves to True or False.
    """

    TARGET_PACKAGE = "package"
    TARGET_VULNERABILITY = "vulnerability"
    TARGET_PRODUCT = "product"

    TARGET_CHOICES = (
        (TARGET_PACKAGE, "Package"),
        (TARGET_VULNERABILITY, "Vulnerability"),
        (TARGET_PRODUCT, "Product"),
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(blank=True)

    target = models.CharField(
        max_length=20,
        choices=TARGET_CHOICES,
    )

    query = models.ForeignKey(
        Query,
        on_delete=models.CASCADE,
        related_name="decision_points",
    )

    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class TriageDecision(models.Model):
    """
    The outcome produced by a matching rule.
    """

    ACTION_UPGRADE = "upgrade"
    ACTION_DOWNGRADE = "downgrade"
    ACTION_REACHABILITY = "reachability"
    ACTION_FORENSICS = "forensics"

    ACTION_CHOICES = (
        (ACTION_UPGRADE, "Upgrade"),
        (ACTION_DOWNGRADE, "Downgrade"),
        (ACTION_REACHABILITY, "Reachability Analysis"),
        (ACTION_FORENSICS, "Forensic Analysis"),
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
    )

    timeline_days = models.PositiveIntegerField()

    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Ruleset(models.Model):
    """
    Collection of Rules.

    Multiple Rulesets can be assigned to a Product.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(blank=True)

    precedence = models.PositiveIntegerField(
        default=100,
    )

    default_decision = models.ForeignKey(
        TriageDecision,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = (
            "-precedence",
            "name",
        )

    def __str__(self):
        return self.name


class Rule(models.Model):
    """
    Maps a set of DecisionPoint values to a Decision.
    """

    ruleset = models.ForeignKey(
        Ruleset,
        on_delete=models.CASCADE,
        related_name="rules",
    )

    name = models.CharField(
        max_length=100,
    )

    priority = models.PositiveIntegerField(
        default=100,
        help_text="Lower values are evaluated first.",
    )

    decision = models.ForeignKey(
        TriageDecision,
        on_delete=models.PROTECT,
        related_name="rules",
    )

    class Meta:
        ordering = (
            "priority",
            "id",
        )

    def __str__(self):
        return f"{self.ruleset} :: {self.name}"


class ExpectedValue(models.IntegerChoices):
    FALSE = 0, "False"
    TRUE = 1, "True"


class RuleCondition(models.Model):
    """
    Represents one column inside a decision table.

    Example

        Rule:
            Upgrade Immediately

        High Risk = TRUE
        Known Exploit = TRUE
        Reachable = FALSE
    """

    FALSE = 0, "False"
    TRUE = 1, "True"

    rule = models.ForeignKey(
        Rule,
        on_delete=models.CASCADE,
        related_name="conditions",
    )

    decision_point = models.ForeignKey(
        DecisionPoint,
        on_delete=models.CASCADE,
    )

    expected = models.PositiveSmallIntegerField(
        choices=ExpectedValue.choices,
    )

    class Meta:
        unique_together = (
            "rule",
            "decision_point",
        )

    def __str__(self):
        return f"{self.decision_point.name} = {self.expected}"
