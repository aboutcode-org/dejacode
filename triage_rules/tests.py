from pathlib import Path
from types import SimpleNamespace

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from component_catalog.models import Package
from component_catalog.tests import make_package
from dje.models import Dataspace
from product_portfolio.models import Product
from product_portfolio.tests import make_product
from triage_rules.engine import DecisionPointEvaluator
from triage_rules.engine import EvaluationEngine
from triage_rules.engine import RuleMatcher
from triage_rules.models import DecisionPoint
from triage_rules.models import ExpectedValue
from triage_rules.models import Rule
from triage_rules.models import RuleCondition
from triage_rules.models import Ruleset
from triage_rules.models import TriageDecision
from vulnerabilities.models import Vulnerability
from vulnerabilities.tests import make_vulnerability
from reporting.models import Filter
from reporting.models import Query


class BaseTriageRulesTestCase(TestCase):
    def setUp(self):
        self.dataspace = Dataspace.objects.create(name="nexB")
        self.package = make_package(
            self.dataspace,
            filename="package-match.tar.gz",
        )
        self.other_package = make_package(
            self.dataspace,
            filename="package-other.tar.gz",
        )
        self.vulnerability = make_vulnerability(
            self.dataspace,
            vulnerability_id="CVE-2026-0001",
            risk_score=9.2,
            affecting=self.package,
        )
        self.other_vulnerability = make_vulnerability(
            self.dataspace,
            vulnerability_id="CVE-2026-0002",
            risk_score=2.5,
            affecting=self.other_package,
        )
        self.product = make_product(
            self.dataspace,
            name="Product Match",
            inventory=[self.package],
        )
        self.other_product = make_product(
            self.dataspace,
            name="Product Other",
            inventory=[self.other_package],
        )

    def make_query(self, name, model, field_name, lookup, value):
        query = Query.objects.create(
            dataspace=self.dataspace,
            name=name,
            content_type=ContentType.objects.get_for_model(model),
            operator="and",
        )
        Filter.objects.create(
            dataspace=self.dataspace,
            query=query,
            field_name=field_name,
            lookup=lookup,
            value=value,
        )
        return query

    def make_decision_point(self, name, target, query):
        return DecisionPoint.objects.create(
            name=name,
            target=target,
            query=query,
        )

    def make_decision(self, name):
        return TriageDecision.objects.create(
            name=name,
            action=TriageDecision.ACTION_UPGRADE,
            timeline_days=7,
        )


class RuleMatcherTest(BaseTriageRulesTestCase):
    def test_matches_respects_expected_values(self):
        package_query = self.make_query(
            name="Rule matcher package query",
            model=Package,
            field_name="filename",
            lookup="exact",
            value=self.package.filename,
        )
        vulnerability_query = self.make_query(
            name="Rule matcher vulnerability query",
            model=Vulnerability,
            field_name="risk_score",
            lookup="gte",
            value="8.0",
        )
        package_dp = self.make_decision_point(
            name="high_risk",
            target=DecisionPoint.TARGET_PACKAGE,
            query=package_query,
        )
        vulnerability_dp = self.make_decision_point(
            name="reachable",
            target=DecisionPoint.TARGET_VULNERABILITY,
            query=vulnerability_query,
        )
        rule = Rule.objects.create(
            ruleset=Ruleset.objects.create(name="Rule matcher ruleset"),
            name="Rule matcher rule",
            priority=1,
            decision=self.make_decision("rule-matcher-decision"),
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=package_dp,
            expected=ExpectedValue.TRUE,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=vulnerability_dp,
            expected=ExpectedValue.FALSE,
        )

        self.assertTrue(
            RuleMatcher.matches(
                rule,
                {
                    "high_risk": True,
                    "reachable": False,
                },
            )
        )
        self.assertFalse(
            RuleMatcher.matches(
                rule,
                {
                    "high_risk": False,
                    "reachable": False,
                },
            )
        )


class DecisionPointEvaluatorTest(BaseTriageRulesTestCase):
    def test_evaluate_matches_any_package_in_product(self):
        query = self.make_query(
            name="Package evaluator query",
            model=Package,
            field_name="filename",
            lookup="exact",
            value=self.package.filename,
        )
        decision_point = self.make_decision_point(
            name="package_match",
            target=DecisionPoint.TARGET_PACKAGE,
            query=query,
        )
        evaluator = DecisionPointEvaluator(
            product=self.product,
        )

        self.assertTrue(evaluator.evaluate(decision_point))

        other_evaluator = DecisionPointEvaluator(
            product=self.other_product,
        )

        self.assertFalse(other_evaluator.evaluate(decision_point))

    def test_evaluate_matches_any_vulnerability_in_product(self):
        query = self.make_query(
            name="Vulnerability evaluator query",
            model=Vulnerability,
            field_name="risk_score",
            lookup="gte",
            value="8.0",
        )
        decision_point = self.make_decision_point(
            name="vulnerability_match",
            target=DecisionPoint.TARGET_VULNERABILITY,
            query=query,
        )
        evaluator = DecisionPointEvaluator(
            product=self.product,
        )

        self.assertTrue(evaluator.evaluate(decision_point))

        other_evaluator = DecisionPointEvaluator(
            product=self.other_product,
        )

        self.assertFalse(other_evaluator.evaluate(decision_point))

    def test_evaluate_matches_direct_product_vulnerability(self):
        direct_vulnerability = make_vulnerability(
            self.dataspace,
            vulnerability_id="CVE-2026-0003",
            risk_score=9.8,
            affecting=self.product,
        )
        query = self.make_query(
            name="Direct product vulnerability evaluator query",
            model=Vulnerability,
            field_name="vulnerability_id",
            lookup="exact",
            value=direct_vulnerability.vulnerability_id,
        )
        decision_point = self.make_decision_point(
            name="direct_product_vulnerability_match",
            target=DecisionPoint.TARGET_VULNERABILITY,
            query=query,
        )

        self.assertTrue(
            DecisionPointEvaluator(product=self.product).evaluate(decision_point)
        )
        self.assertFalse(
            DecisionPointEvaluator(product=self.other_product).evaluate(decision_point)
        )

    def test_evaluate_matches_product_target_once(self):
        query = self.make_query(
            name="Product evaluator query",
            model=Product,
            field_name="name",
            lookup="exact",
            value=self.product.name,
        )
        decision_point = self.make_decision_point(
            name="product_match",
            target=DecisionPoint.TARGET_PRODUCT,
            query=query,
        )
        evaluator = DecisionPointEvaluator(
            product=self.product,
        )

        self.assertTrue(evaluator.evaluate(decision_point))

        other_evaluator = DecisionPointEvaluator(
            product=self.other_product,
        )

        self.assertFalse(other_evaluator.evaluate(decision_point))

    def test_evaluate_rejects_unknown_target(self):
        evaluator = DecisionPointEvaluator(
            product=self.product,
        )

        with self.assertRaisesMessage(
            ValueError,
            "Unknown target unknown",
        ):
            evaluator.evaluate(
                SimpleNamespace(
                    target="unknown",
                    query=None,
                )
            )


class EvaluationEngineIntegrationTest(BaseTriageRulesTestCase):

    def test_evaluate_builds_vector_for_product_package_and_vulnerability_targets(self):
        package_query = self.make_query(
            name="Package filename match",
            model=Package,
            field_name="filename",
            lookup="exact",
            value=self.package.filename,
        )
        vulnerability_query = self.make_query(
            name="Critical vulnerability",
            model=Vulnerability,
            field_name="risk_score",
            lookup="gte",
            value="8.0",
        )
        product_query = self.make_query(
            name="Product name match",
            model=Product,
            field_name="name",
            lookup="exact",
            value=self.product.name,
        )
        package_dp = self.make_decision_point(
            name="matching_package",
            target=DecisionPoint.TARGET_PACKAGE,
            query=package_query,
        )
        vulnerability_dp = self.make_decision_point(
            name="critical_vulnerability",
            target=DecisionPoint.TARGET_VULNERABILITY,
            query=vulnerability_query,
        )
        product_dp = self.make_decision_point(
            name="matching_product",
            target=DecisionPoint.TARGET_PRODUCT,
            query=product_query,
        )
        decision = self.make_decision("upgrade-now")
        ruleset = Ruleset.objects.create(
            name="Security rules",
            precedence=100,
            default_decision=None,
        )
        rule = Rule.objects.create(
            ruleset=ruleset,
            name="Upgrade immediately",
            priority=10,
            decision=decision,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=package_dp,
            expected=ExpectedValue.TRUE,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=vulnerability_dp,
            expected=ExpectedValue.TRUE,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=product_dp,
            expected=ExpectedValue.TRUE,
        )

        result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[ruleset],
        )

        self.assertEqual(decision, result.decision)
        self.assertEqual(
            {
                "matching_package": True,
                "critical_vulnerability": True,
                "matching_product": True,
            },
            result.vector,
        )

        other_result = EvaluationEngine().evaluate(
            product=self.other_product,
            rulesets=[ruleset],
        )

        self.assertIsNone(other_result.decision)
        self.assertEqual(
            {
                "matching_package": False,
                "critical_vulnerability": False,
                "matching_product": False,
            },
            other_result.vector,
        )

    def test_evaluate_uses_higher_precedence_ruleset_winner_for_product(self):
        package_query = self.make_query(
            name="Package filename match for precedence",
            model=Package,
            field_name="filename",
            lookup="exact",
            value=self.package.filename,
        )
        vulnerability_query = self.make_query(
            name="High risk vulnerability for precedence",
            model=Vulnerability,
            field_name="risk_score",
            lookup="gte",
            value="8.0",
        )
        package_dp = self.make_decision_point(
            name="precedence_package_match",
            target=DecisionPoint.TARGET_PACKAGE,
            query=package_query,
        )
        vulnerability_dp = self.make_decision_point(
            name="precedence_vulnerability_match",
            target=DecisionPoint.TARGET_VULNERABILITY,
            query=vulnerability_query,
        )
        low_precedence_decision = self.make_decision("forensics")
        high_precedence_decision = TriageDecision.objects.create(
            name="upgrade",
            action=TriageDecision.ACTION_REACHABILITY,
            timeline_days=2,
        )
        low_precedence_ruleset = Ruleset.objects.create(
            name="Fallback rules",
            precedence=10,
            default_decision=low_precedence_decision,
        )
        high_precedence_ruleset = Ruleset.objects.create(
            name="Priority rules",
            precedence=100,
            default_decision=None,
        )
        rule = Rule.objects.create(
            ruleset=high_precedence_ruleset,
            name="Priority upgrade",
            priority=1,
            decision=high_precedence_decision,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=package_dp,
            expected=ExpectedValue.TRUE,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=vulnerability_dp,
            expected=ExpectedValue.TRUE,
        )

        result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[
                low_precedence_ruleset,
                high_precedence_ruleset,
            ],
        )

        self.assertEqual(high_precedence_decision, result.decision)

    def test_evaluate_returns_default_decision_when_no_rule_matches(self):
        package_query = self.make_query(
            name="No package match",
            model=Package,
            field_name="filename",
            lookup="exact",
            value="missing-package.tar.gz",
        )
        package_dp = self.make_decision_point(
            name="no_package_match",
            target=DecisionPoint.TARGET_PACKAGE,
            query=package_query,
        )
        default_decision = self.make_decision("default-decision")
        ruleset = Ruleset.objects.create(
            name="Defaulted rules",
            precedence=100,
            default_decision=default_decision,
        )
        rule = Rule.objects.create(
            ruleset=ruleset,
            name="Never matches",
            priority=1,
            decision=self.make_decision("non-default-decision"),
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=package_dp,
            expected=ExpectedValue.TRUE,
        )

        result = EvaluationEngine().evaluate(
            product=self.other_product,
            rulesets=[ruleset],
        )

        self.assertEqual(default_decision, result.decision)
        self.assertEqual(
            {
                "no_package_match": False,
            },
            result.vector,
        )

    def test_evaluate_uses_lowest_priority_matching_rule_within_ruleset(self):
        product_query = self.make_query(
            name="Priority product match",
            model=Product,
            field_name="name",
            lookup="exact",
            value=self.product.name,
        )
        product_dp = self.make_decision_point(
            name="priority_product_match",
            target=DecisionPoint.TARGET_PRODUCT,
            query=product_query,
        )
        ruleset = Ruleset.objects.create(
            name="Priority ruleset",
            precedence=100,
        )
        first_decision = self.make_decision("first-priority-decision")
        second_decision = self.make_decision("second-priority-decision")
        first_rule = Rule.objects.create(
            ruleset=ruleset,
            name="First match wins",
            priority=1,
            decision=first_decision,
        )
        second_rule = Rule.objects.create(
            ruleset=ruleset,
            name="Second match loses",
            priority=10,
            decision=second_decision,
        )
        RuleCondition.objects.create(
            rule=first_rule,
            decision_point=product_dp,
            expected=ExpectedValue.TRUE,
        )
        RuleCondition.objects.create(
            rule=second_rule,
            decision_point=product_dp,
            expected=ExpectedValue.TRUE,
        )

        result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[ruleset],
        )

        self.assertEqual(first_decision, result.decision)

    def test_evaluate_ignores_disabled_decision_points(self):
        package_query = self.make_query(
            name="Disabled package query",
            model=Package,
            field_name="filename",
            lookup="exact",
            value=self.package.filename,
        )
        product_query = self.make_query(
            name="Enabled product query",
            model=Product,
            field_name="name",
            lookup="exact",
            value=self.product.name,
        )
        disabled_package_dp = self.make_decision_point(
            name="disabled_package_match",
            target=DecisionPoint.TARGET_PACKAGE,
            query=package_query,
        )
        disabled_package_dp.enabled = False
        disabled_package_dp.save()
        enabled_product_dp = self.make_decision_point(
            name="enabled_product_match",
            target=DecisionPoint.TARGET_PRODUCT,
            query=product_query,
        )
        ruleset = Ruleset.objects.create(
            name="Disabled decision point ruleset",
            precedence=100,
        )
        decision = self.make_decision("enabled-product-decision")
        rule = Rule.objects.create(
            ruleset=ruleset,
            name="Ignore disabled point",
            priority=1,
            decision=decision,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=disabled_package_dp,
            expected=ExpectedValue.FALSE,
        )
        RuleCondition.objects.create(
            rule=rule,
            decision_point=enabled_product_dp,
            expected=ExpectedValue.TRUE,
        )

        result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[ruleset],
        )

        self.assertEqual(decision, result.decision)
        self.assertEqual(
            {
                "enabled_product_match": True,
            },
            result.vector,
        )

    def test_evaluate_ignores_disabled_rulesets(self):
        product_query = self.make_query(
            name="Disabled ruleset product query",
            model=Product,
            field_name="name",
            lookup="exact",
            value=self.product.name,
        )
        product_dp = self.make_decision_point(
            name="disabled_ruleset_product_match",
            target=DecisionPoint.TARGET_PRODUCT,
            query=product_query,
        )
        enabled_decision = self.make_decision("enabled-ruleset-decision")
        disabled_decision = self.make_decision("disabled-ruleset-decision")
        enabled_ruleset = Ruleset.objects.create(
            name="Enabled ruleset",
            precedence=10,
            default_decision=enabled_decision,
        )
        disabled_ruleset = Ruleset.objects.create(
            name="Disabled ruleset",
            precedence=100,
            default_decision=disabled_decision,
            enabled=False,
        )
        disabled_rule = Rule.objects.create(
            ruleset=disabled_ruleset,
            name="Disabled ruleset match",
            priority=1,
            decision=disabled_decision,
        )
        RuleCondition.objects.create(
            rule=disabled_rule,
            decision_point=product_dp,
            expected=ExpectedValue.TRUE,
        )

        result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[enabled_ruleset, disabled_ruleset],
        )

        self.assertEqual(enabled_decision, result.decision)

    def test_get_all_decision_points_deduplicates_shared_real_decision_points(self):
        shared_query = self.make_query(
            name="Shared package query",
            model=Package,
            field_name="filename",
            lookup="exact",
            value=self.package.filename,
        )
        shared_decision_point = self.make_decision_point(
            name="shared_point",
            target=DecisionPoint.TARGET_PACKAGE,
            query=shared_query,
        )
        ruleset_one = Ruleset.objects.create(
            name="Ruleset one",
            precedence=10,
        )
        ruleset_two = Ruleset.objects.create(
            name="Ruleset two",
            precedence=20,
        )
        rule_one = Rule.objects.create(
            ruleset=ruleset_one,
            name="Rule one",
            priority=1,
            decision=self.make_decision("decision-one"),
        )
        rule_two = Rule.objects.create(
            ruleset=ruleset_two,
            name="Rule two",
            priority=1,
            decision=self.make_decision("decision-two"),
        )
        RuleCondition.objects.create(
            rule=rule_one,
            decision_point=shared_decision_point,
            expected=ExpectedValue.TRUE,
        )
        RuleCondition.objects.create(
            rule=rule_two,
            decision_point=shared_decision_point,
            expected=ExpectedValue.FALSE,
        )

        decision_points = EvaluationEngine.get_all_decision_points(
            [ruleset_one, ruleset_two]
        )

        self.assertEqual([shared_decision_point], decision_points)


class PolicyLoaderTest(BaseTriageRulesTestCase):
    data = Path(__file__).parent / "tests" / "data"

    def test_load_policy_yaml_creates_reporting_queries_and_triage_objects(self):
        from triage_rules.loader import load_policy_yaml

        loaded = load_policy_yaml(
            self.data / "sample_policy.yaml",
            dataspace=self.dataspace,
        )

        self.assertIn("upgrade-now", loaded["decisions"])
        self.assertIn("matching_package", loaded["decision_points"])
        self.assertIn("security-policy", loaded["rulesets"])

        package_dp = loaded["decision_points"]["matching_package"]
        self.assertEqual(DecisionPoint.TARGET_PACKAGE, package_dp.target)
        self.assertEqual(1, package_dp.query.filters.count())
        self.assertEqual(
            "filename",
            package_dp.query.filters.get().field_name,
        )

        ruleset = loaded["rulesets"]["security-policy"]
        rule = ruleset.rules.get()
        self.assertEqual("Upgrade immediately", rule.name)
        self.assertEqual(3, rule.conditions.count())

    def test_load_policy_yaml_end_to_end_with_engine(self):
        from triage_rules.loader import load_policy_yaml

        loaded = load_policy_yaml(
            self.data / "sample_policy.yaml",
            dataspace=self.dataspace,
        )
        ruleset = loaded["rulesets"]["security-policy"]
        decision = loaded["decisions"]["upgrade-now"]

        result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[ruleset],
        )

        self.assertEqual(decision, result.decision)
        self.assertEqual(
            {
                "matching_package": True,
                "critical_vulnerability": True,
                "matching_product": True,
            },
            result.vector,
        )

    def test_load_policy_yaml_is_idempotent(self):
        from triage_rules.loader import load_policy_yaml

        path = self.data / "sample_policy.yaml"
        first = load_policy_yaml(path, dataspace=self.dataspace)
        second = load_policy_yaml(path, dataspace=self.dataspace)

        self.assertEqual(
            first["rulesets"]["security-policy"].pk,
            second["rulesets"]["security-policy"].pk,
        )
        self.assertEqual(1, Ruleset.objects.filter(name="security-policy").count())
        self.assertEqual(1, first["rulesets"]["security-policy"].rules.count())

    def test_comprehensive_policy_load_store_and_evaluate_end_to_end(self):
        from product_portfolio.tests import make_product_package
        from triage_rules.loader import load_policy_yaml

        loaded = load_policy_yaml(
            self.data / "comprehensive_policy.yaml",
            dataspace=self.dataspace,
        )

        self.assertEqual(4, TriageDecision.objects.count())
        self.assertEqual(9, DecisionPoint.objects.count())
        self.assertEqual(9, Query.objects.filter(dataspace=self.dataspace).count())
        self.assertEqual(9, Filter.objects.filter(dataspace=self.dataspace).count())
        self.assertEqual(
            2,
            Ruleset.objects.filter(
                name__in=["critical-response", "baseline-response"]
            ).count(),
        )
        self.assertEqual(4, Rule.objects.count())
        self.assertEqual(14, RuleCondition.objects.count())

        critical_ruleset = loaded["rulesets"]["critical-response"]
        baseline_ruleset = loaded["rulesets"]["baseline-response"]
        upgrade_decision = loaded["decisions"]["upgrade-immediately"]
        reachability_decision = loaded["decisions"]["reachability-analysis"]
        downgrade_decision = loaded["decisions"]["downgrade-risk"]
        forensics_decision = loaded["decisions"]["forensics-review"]

        legacy_package = make_package(
            self.dataspace,
            filename="legacy-lib.tar.gz",
            download_url="https://example.com/legacy-lib.tar.gz",
        )
        self.package.download_url = "http://example.com/package-match.tar.gz"
        self.package.save()
        make_product_package(self.product, package=legacy_package)

        make_vulnerability(
            self.dataspace,
            vulnerability_id="CVE-2026-0003",
            risk_score=6.5,
            exploitability=2.0,
            affecting=self.package,
        )
        make_vulnerability(
            self.dataspace,
            vulnerability_id="CVE-2026-0004",
            risk_score=5.0,
            affecting=self.product,
        )

        production_result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[critical_ruleset, baseline_ruleset],
        )

        self.assertEqual(upgrade_decision, production_result.decision)
        self.assertEqual(
            {
                "watched_package": True,
                "legacy_package_present": True,
                "package_with_download_url": True,
                "critical_vulnerability": True,
                "known_exploit_vulnerability": True,
                "low_risk_vulnerability": False,
                "direct_product_vulnerability": True,
                "production_product": True,
                "non_production_product": False,
            },
            production_result.vector,
        )

        other_product_result = EvaluationEngine().evaluate(
            product=self.other_product,
            rulesets=[critical_ruleset, baseline_ruleset],
        )

        self.assertEqual(reachability_decision, other_product_result.decision)
        self.assertEqual(
            {
                "watched_package": False,
                "legacy_package_present": False,
                "package_with_download_url": False,
                "critical_vulnerability": False,
                "known_exploit_vulnerability": False,
                "low_risk_vulnerability": True,
                "direct_product_vulnerability": False,
                "production_product": False,
                "non_production_product": True,
            },
            other_product_result.vector,
        )

        self.vulnerability.delete()
        exploit_only_result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[critical_ruleset],
        )

        self.assertEqual(reachability_decision, exploit_only_result.decision)
        self.assertTrue(exploit_only_result.vector["known_exploit_vulnerability"])
        self.assertFalse(exploit_only_result.vector["critical_vulnerability"])
        self.assertTrue(exploit_only_result.vector["watched_package"])

        self.product.productpackages.filter(
            package=self.package,
        ).delete()

        legacy_result = EvaluationEngine().evaluate(
            product=self.product,
            rulesets=[baseline_ruleset],
        )

        self.assertEqual(forensics_decision, legacy_result.decision)
        self.assertTrue(legacy_result.vector["legacy_package_present"])
        self.assertTrue(legacy_result.vector["production_product"])
        self.assertTrue(legacy_result.vector["direct_product_vulnerability"])
        self.assertNotIn("watched_package", legacy_result.vector)

        low_risk_only_result = EvaluationEngine().evaluate(
            product=self.other_product,
            rulesets=[baseline_ruleset],
        )

        self.assertEqual(downgrade_decision, low_risk_only_result.decision)
        self.assertTrue(low_risk_only_result.vector["low_risk_vulnerability"])
        self.assertFalse(low_risk_only_result.vector["critical_vulnerability"])
