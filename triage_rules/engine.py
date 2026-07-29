import operator
from functools import reduce

from django.db.models import Q

from product_portfolio.models import Product
from triage_rules.models import DecisionPoint
from triage_rules.models import ExpectedValue


class DecisionPointEvaluator:

    def __init__(self, product, user=None):

        self.product = product
        self.user = user

    def evaluate(self, decision_point):

        target = decision_point.target

        if target == DecisionPoint.TARGET_PACKAGE:
            queryset = decision_point.query.get_qs(user=self.user)
            return queryset.filter(
                pk__in=self.product.all_packages.values("pk")
            ).exists()

        if target == DecisionPoint.TARGET_VULNERABILITY:
            queryset = decision_point.query.get_qs(user=self.user)
            return queryset.filter(
                Q(pk__in=self.product.get_vulnerability_qs().values("pk"))
                | Q(pk__in=self.product.affected_by_vulnerabilities.values("pk"))
            ).exists()

        if target == DecisionPoint.TARGET_PRODUCT:
            return self._product_matches_query(decision_point.query)

        raise ValueError(f"Unknown target {target}")

    def _product_matches_query(self, query):
        q_objects = []
        for filter_ in query.filters.all():
            q_object = filter_.get_q(None, self.user)
            if q_object:
                q_objects.append(q_object)

        if not q_objects:
            return False

        queryset = Product.unsecured_objects.scope(self.product.dataspace).filter(
            pk=self.product.pk
        )
        operator_type = operator.or_ if query.operator == "or" else operator.and_
        return queryset.filter(reduce(operator_type, q_objects)).exists()


class RuleMatcher:

    @staticmethod
    def matches(rule, vector):
        """
        vector

        {
            dp_high_risk: True,
            dp_known_exploit: False
        }
        """

        for condition in rule.conditions.all():
            if not condition.decision_point.enabled:
                continue

            expected = condition.expected

            actual = vector[condition.decision_point.name]

            if expected == ExpectedValue.TRUE and not actual:
                return False

            if expected == ExpectedValue.FALSE and actual:
                return False

        return True


class RulesetEvaluator:

    def __init__(self, ruleset):

        self.ruleset = ruleset

    def evaluate(self, vector):

        rules = self.ruleset.rules.prefetch_related(
            "conditions",
            "decision",
        ).order_by("priority")

        for rule in rules:

            if RuleMatcher.matches(
                rule,
                vector,
            ):
                return rule.decision

        return self.ruleset.default_decision


class EvaluationEngine:
    """
    Public entry point.

    engine = EvaluationEngine()

    decision = engine.evaluate(
        product,
        rulesets,
    )
    """

    def evaluate(self, product, rulesets, user=None):

        decision_point_evaluator = DecisionPointEvaluator(
            product,
            user=user,
        )

        vector = {}

        decision_points = self.get_all_decision_points(rulesets)

        for dp in decision_points:

            vector[dp.name] = decision_point_evaluator.evaluate(dp)

        winning = None

        winning_precedence = -1

        for ruleset in rulesets:
            if not ruleset.enabled:
                continue

            decision = RulesetEvaluator(ruleset).evaluate(vector)

            if winning is None or ruleset.precedence > winning_precedence:
                winning = decision
                winning_precedence = ruleset.precedence

        return EvaluationResult(
            decision=winning,
            decision_vector=vector,
        )

    @staticmethod
    def get_all_decision_points(rulesets):

        seen = {}

        for ruleset in rulesets:
            if not ruleset.enabled:
                continue

            for rule in ruleset.rules.prefetch_related("conditions__decision_point"):

                for condition in rule.conditions.all():
                    dp = condition.decision_point
                    if not dp.enabled:
                        continue

                    seen[dp.id] = dp

        return list(seen.values())


class EvaluationResult:

    def __init__(self, decision, decision_vector):
        self.decision = decision
        self.vector = decision_vector

    def __repr__(self):
        return (
            f"<EvaluationResult " f"decision={self.decision} " f"vector={self.vector}>"
        )
