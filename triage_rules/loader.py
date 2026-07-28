from pathlib import Path

import yaml
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from reporting.models import Filter
from reporting.models import Query
from triage_rules.models import DecisionPoint
from triage_rules.models import ExpectedValue
from triage_rules.models import Rule
from triage_rules.models import RuleCondition
from triage_rules.models import Ruleset
from triage_rules.models import TriageDecision

TARGET_MODELS = {
    DecisionPoint.TARGET_PACKAGE: ("component_catalog", "package"),
    DecisionPoint.TARGET_VULNERABILITY: ("vulnerabilities", "vulnerability"),
    DecisionPoint.TARGET_PRODUCT: ("product_portfolio", "product"),
}

EXPECTED_VALUES = {
    "true": ExpectedValue.TRUE,
    "false": ExpectedValue.FALSE,
    "1": ExpectedValue.TRUE,
    "0": ExpectedValue.FALSE,
    1: ExpectedValue.TRUE,
    0: ExpectedValue.FALSE,
    True: ExpectedValue.TRUE,
    False: ExpectedValue.FALSE,
}


class PolicyLoadError(Exception):
    pass


def load_policy_yaml(source, dataspace):
    """
    Load a triage policy YAML file into concrete model objects.

    Expected top-level keys:
      - decisions
      - decision_points
      - rulesets

    ``source`` may be a file path, Path, or already-parsed dict.
    """
    if isinstance(source, dict):
        data = source
    else:
        path = Path(source)
        data = yaml.safe_load(path.read_text())

    if not isinstance(data, dict):
        raise PolicyLoadError("Policy YAML must define a mapping at the top level.")

    with transaction.atomic():
        decisions = _load_decisions(data.get("decisions") or {}, dataspace)
        decision_points = _load_decision_points(
            data.get("decision_points") or {},
            dataspace,
        )
        rulesets = _load_rulesets(
            data.get("rulesets") or {},
            dataspace,
            decisions=decisions,
            decision_points=decision_points,
        )

    return {
        "decisions": decisions,
        "decision_points": decision_points,
        "rulesets": rulesets,
    }


def _load_decisions(decisions_data, dataspace):
    decisions = {}

    for name, config in decisions_data.items():
        if not isinstance(config, dict):
            raise PolicyLoadError(f"Decision '{name}' must be a mapping.")

        action = config.get("action")
        if action not in dict(TriageDecision.ACTION_CHOICES):
            raise PolicyLoadError(
                f"Decision '{name}' has invalid action '{action}'."
            )

        timeline_days = config.get("timeline_days")
        if timeline_days is None:
            raise PolicyLoadError(
                f"Decision '{name}' requires 'timeline_days'."
            )

        decision, _ = TriageDecision.objects.update_or_create(
            name=name,
            defaults={
                "action": action,
                "timeline_days": timeline_days,
                "description": config.get("description", ""),
            },
        )
        decisions[name] = decision

    return decisions


def _load_decision_points(decision_points_data, dataspace):
    decision_points = {}

    for name, config in decision_points_data.items():
        if not isinstance(config, dict):
            raise PolicyLoadError(f"Decision point '{name}' must be a mapping.")

        target = config.get("target")
        if target not in TARGET_MODELS:
            raise PolicyLoadError(
                f"Decision point '{name}' has invalid target '{target}'."
            )

        query_config = config.get("query")
        if not isinstance(query_config, dict):
            raise PolicyLoadError(
                f"Decision point '{name}' requires a 'query' mapping."
            )

        query = _load_query(
            query_config,
            dataspace=dataspace,
            target=target,
            default_name=f"triage:{name}",
        )

        decision_point, _ = DecisionPoint.objects.update_or_create(
            name=name,
            defaults={
                "target": target,
                "query": query,
                "description": config.get("description", ""),
                "enabled": config.get("enabled", True),
            },
        )
        decision_points[name] = decision_point

    return decision_points


def _load_query(query_config, dataspace, target, default_name):
    app_label, model_name = TARGET_MODELS[target]
    model = apps.get_model(app_label, model_name)
    content_type = ContentType.objects.get_for_model(model)

    query_name = query_config.get("name", default_name)
    operator = query_config.get("operator", "and")
    if operator not in dict(Query.OPERATOR_CHOICES):
        raise PolicyLoadError(
            f"Query '{query_name}' has invalid operator '{operator}'."
        )

    query, _ = Query.objects.update_or_create(
        dataspace=dataspace,
        name=query_name,
        defaults={
            "description": query_config.get("description", ""),
            "content_type": content_type,
            "operator": operator,
        },
    )

    filters_data = query_config.get("filters") or []
    if not filters_data:
        raise PolicyLoadError(f"Query '{query_name}' requires at least one filter.")

    query.filters.all().delete()
    for filter_config in filters_data:
        _load_filter(query, filter_config, dataspace)

    return query


def _load_filter(query, filter_config, dataspace):
    if not isinstance(filter_config, dict):
        raise PolicyLoadError("Each query filter must be a mapping.")

    field_name = filter_config.get("field") or filter_config.get("field_name")
    if not field_name:
        raise PolicyLoadError("Each query filter requires 'field'.")

    lookup = filter_config.get("lookup", "exact")
    if lookup not in dict(Filter.LOOKUP_CHOICES):
        raise PolicyLoadError(
            f"Filter on '{field_name}' has invalid lookup '{lookup}'."
        )

    Filter.objects.create(
        dataspace=dataspace,
        query=query,
        field_name=field_name,
        lookup=lookup,
        value=str(filter_config.get("value", "")),
        negate=filter_config.get("negate", False),
        runtime_parameter=filter_config.get("runtime_parameter", False),
    )


def _load_rulesets(rulesets_data, dataspace, decisions, decision_points):
    rulesets = {}

    for name, config in rulesets_data.items():
        if not isinstance(config, dict):
            raise PolicyLoadError(f"Ruleset '{name}' must be a mapping.")

        default_decision_name = config.get("default_decision")
        default_decision = None
        if default_decision_name:
            default_decision = decisions.get(default_decision_name)
            if default_decision is None:
                raise PolicyLoadError(
                    f"Ruleset '{name}' references unknown decision "
                    f"'{default_decision_name}'."
                )

        ruleset, _ = Ruleset.objects.update_or_create(
            name=name,
            defaults={
                "description": config.get("description", ""),
                "precedence": config.get("precedence", 100),
                "default_decision": default_decision,
                "enabled": config.get("enabled", True),
            },
        )

        ruleset.rules.all().delete()
        for rule_config in config.get("rules") or []:
            _load_rule(
                ruleset=ruleset,
                rule_config=rule_config,
                decisions=decisions,
                decision_points=decision_points,
            )

        rulesets[name] = ruleset

    return rulesets


def _load_rule(ruleset, rule_config, decisions, decision_points):
    if not isinstance(rule_config, dict):
        raise PolicyLoadError(f"Rule in ruleset '{ruleset.name}' must be a mapping.")

    rule_name = rule_config.get("name")
    if not rule_name:
        raise PolicyLoadError(
            f"Each rule in ruleset '{ruleset.name}' requires 'name'."
        )

    decision_name = rule_config.get("decision")
    decision = decisions.get(decision_name)
    if decision is None:
        raise PolicyLoadError(
            f"Rule '{rule_name}' references unknown decision '{decision_name}'."
        )

    rule = Rule.objects.create(
        ruleset=ruleset,
        name=rule_name,
        priority=rule_config.get("priority", 100),
        decision=decision,
    )

    conditions_data = rule_config.get("conditions") or {}
    for decision_point_name, expected_value in _iter_conditions(conditions_data):
        decision_point = decision_points.get(decision_point_name)
        if decision_point is None:
            raise PolicyLoadError(
                f"Rule '{rule_name}' references unknown decision point "
                f"'{decision_point_name}'."
            )

        expected = _parse_expected(expected_value, decision_point_name)
        RuleCondition.objects.create(
            rule=rule,
            decision_point=decision_point,
            expected=expected,
        )

    return rule


def _iter_conditions(conditions_data):
    if isinstance(conditions_data, dict):
        return conditions_data.items()

    if isinstance(conditions_data, list):
        items = []
        for condition in conditions_data:
            if not isinstance(condition, dict):
                raise PolicyLoadError("Each rule condition must be a mapping.")
            decision_point_name = condition.get("decision_point")
            if not decision_point_name:
                raise PolicyLoadError(
                    "List-style rule conditions require 'decision_point'."
                )
            items.append(
                (decision_point_name, condition.get("expected"))
            )
        return items

    raise PolicyLoadError("Rule conditions must be a mapping or list.")


def _parse_expected(value, decision_point_name):
    if value is None:
        raise PolicyLoadError(
            f"Decision point '{decision_point_name}' is missing an expected value."
        )

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in EXPECTED_VALUES:
            return EXPECTED_VALUES[normalized]

    if value in EXPECTED_VALUES:
        return EXPECTED_VALUES[value]

    raise PolicyLoadError(
        f"Decision point '{decision_point_name}' has invalid expected value "
        f"'{value}'. Use true or false."
    )
