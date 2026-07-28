# Triage Rules

Product-centric policy evaluation for DejaCode. A **Product** is evaluated against
configurable rules; the engine returns a single **triage decision** (upgrade,
downgrade, reachability analysis, or forensics) plus a boolean **decision vector**
showing which predicates matched.

Policies can be defined in YAML and loaded into the database. Decision-point
predicates reuse the existing `reporting.Query` and `reporting.Filter` models.

## Contents

- [Architecture](#architecture)
- [Data model](#data-model)
- [Evaluation engine](#evaluation-engine)
- [Policy loader](#policy-loader)
- [YAML policy format](#yaml-policy-format)
- [Usage](#usage)
- [Tests](#tests)
- [Current limitations](#current-limitations)
- [Open design questions](#open-design-questions)

## Architecture

```
Policy YAML
    │
    ▼
loader.py ──► TriageDecision, DecisionPoint, Ruleset, Rule, RuleCondition
              └── reporting.Query + reporting.Filter (per decision point)

Product + assigned Rulesets
    │
    ▼
engine.py ──► DecisionPointEvaluator (build vector)
              └── RulesetEvaluator + RuleMatcher (pick decision)
    │
    ▼
EvaluationResult(decision, vector)
```

Evaluation is **product-centric**: one product in, one product-level decision out.
Package and vulnerability decision points use **existential** semantics today
(`True` if **any** matching package or vulnerability exists in the product).

## Data model

### DecisionPoint

Reusable boolean predicate evaluated against a product.

| Field | Description |
|-------|-------------|
| `name` | Unique key; appears in the evaluation vector |
| `target` | `package`, `vulnerability`, or `product` |
| `query` | FK to `reporting.Query` (filter logic via `Filter` rows) |
| `enabled` | Disabled points are skipped |

### TriageDecision

Outcome label when a rule matches.

| Field | Description |
|-------|-------------|
| `name` | Unique label (e.g. `upgrade-immediately`) |
| `action` | `upgrade`, `downgrade`, `reachability`, `forensics` |
| `timeline_days` | Recommended response window |
| `description` | Optional text |

### Ruleset

Collection of rules. Multiple rulesets can be evaluated for one product; the
ruleset with the **highest `precedence`** wins.

| Field | Description |
|-------|-------------|
| `precedence` | Higher value wins across rulesets |
| `default_decision` | Used when no rule in the ruleset matches |
| `enabled` | Disabled rulesets are ignored |

### Rule

One row in a decision table inside a ruleset.

| Field | Description |
|-------|-------------|
| `priority` | Lower values are evaluated first |
| `decision` | `TriageDecision` returned when this rule matches |

### RuleCondition

One column in a decision table row.

| Field | Description |
|-------|-------------|
| `decision_point` | Which predicate to check |
| `expected` | `TRUE` (1) or `FALSE` (0) |

There is no wildcard / `ANY` value; every condition is strictly true or false.

### Relationship to reporting

Each `DecisionPoint` owns a `reporting.Query` with one or more `reporting.Filter`
rows:

```text
Query
  ├── content_type  → Package, Vulnerability, or Product
  ├── operator      → and | or
  └── filters[]
        ├── field_name
        ├── lookup    → exact, gte, icontains, …
        ├── value
        └── negate    → optional
```

This reuses DejaCode reporting queries so the same filters work in triage and in
reports.

## Evaluation engine

Module: `triage_rules/engine.py`

### Entry point

```python
from triage_rules.engine import EvaluationEngine

engine = EvaluationEngine()
result = engine.evaluate(product, rulesets, user=None)

result.decision   # TriageDecision or None
result.vector     # {"decision_point_name": True/False, ...}
```

### Evaluation flow

1. **Collect decision points** — gather every `DecisionPoint` referenced by rule
   conditions in the enabled rulesets (skip disabled decision points).

2. **Build decision vector** — for each decision point, evaluate `True`/`False`:

   | Target | Current semantics |
   |--------|-------------------|
   | `package` | `True` if **any** package in `product.all_packages` matches the query |
   | `vulnerability` | `True` if **any** vulnerability from package-linked vulns **or** `product.affected_by_vulnerabilities` matches |
   | `product` | `True` if the product itself matches the query filters |

3. **Evaluate each ruleset** — walk rules in ascending `priority`; first matching
   rule wins, otherwise use `default_decision`.

4. **Pick winning ruleset** — among enabled rulesets, the highest `precedence`
   supplies the final `decision`.

### Rule matching

For each `RuleCondition` on a rule:

- Skip if the decision point is disabled.
- If `expected == TRUE` and vector value is `False` → rule does not match.
- If `expected == FALSE` and vector value is `True` → rule does not match.

### User context

`user` is passed to `Query.get_qs(user=...)` for package and vulnerability
queries so secured reporting behavior applies when a user is provided.

Product-targeted decision points evaluate the current product via
`Product.unsecured_objects` because the default Product manager returns an empty
queryset without a user.

## Policy loader

Module: `triage_rules/loader.py`

### Entry point

```python
from triage_rules.loader import load_policy_yaml

loaded = load_policy_yaml("path/to/policy.yaml", dataspace=dataspace)

loaded["decisions"]        # dict name → TriageDecision
loaded["decision_points"]  # dict name → DecisionPoint
loaded["rulesets"]         # dict name → Ruleset
```

`source` may be a file path, `Path`, or an already-parsed dict.

Loads run inside `transaction.atomic()`. Reloading the same YAML updates objects
in place (`update_or_create` for decisions, decision points, and rulesets; rules
are replaced on ruleset reload).

### Load order

1. `TriageDecision`
2. `DecisionPoint` (+ `Query` + `Filter`)
3. `Ruleset` → `Rule` → `RuleCondition`

## YAML policy format

### Minimal example

See `tests/data/sample_policy.yaml`.

```yaml
decisions:
  upgrade-now:
    action: upgrade
    timeline_days: 7
    description: Upgrade affected packages immediately.

  forensics:
    action: forensics
    timeline_days: 30

decision_points:
  matching_package:
    target: package
    query:
      operator: and
      filters:
        - field: filename
          lookup: exact
          value: package-match.tar.gz

  critical_vulnerability:
    target: vulnerability
    query:
      filters:
        - field: risk_score
          lookup: gte
          value: "8.0"

  matching_product:
    target: product
    query:
      filters:
        - field: name
          lookup: exact
          value: Product Match

rulesets:
  security-policy:
    precedence: 100
    default_decision: forensics
    enabled: true
    rules:
      - name: Upgrade immediately
        priority: 10
        decision: upgrade-now
        conditions:
          matching_package: true
          critical_vulnerability: true
          matching_product: true
```

### Comprehensive example

See `tests/data/comprehensive_policy.yaml` (9 decision points, 2 rulesets, 4
rules).

### Field reference

**`decisions`**

| Key | Required | Description |
|-----|----------|-------------|
| `action` | yes | `upgrade`, `downgrade`, `reachability`, `forensics` |
| `timeline_days` | yes | Integer |
| `description` | no | Text |

**`decision_points`**

| Key | Required | Description |
|-----|----------|-------------|
| `target` | yes | `package`, `vulnerability`, `product` |
| `query` | yes | Query definition (see below) |
| `description` | no | Text |
| `enabled` | no | Default `true` |

**`query`**

| Key | Required | Description |
|-----|----------|-------------|
| `filters` | yes | List of filter dicts |
| `operator` | no | `and` (default) or `or` |
| `name` | no | Query name; default `triage:{decision_point_name}` |
| `description` | no | Text |

**Filter dict**

| Key | Required | Description |
|-----|----------|-------------|
| `field` or `field_name` | yes | Model field path |
| `lookup` | no | Default `exact` |
| `value` | no | Filter value (string) |
| `negate` | no | Default `false` |

**`rulesets`**

| Key | Required | Description |
|-----|----------|-------------|
| `precedence` | no | Default `100` |
| `default_decision` | no | Decision name |
| `enabled` | no | Default `true` |
| `rules` | no | List of rules |

**Rule**

| Key | Required | Description |
|-----|----------|-------------|
| `name` | yes | Rule label |
| `decision` | yes | Decision name |
| `priority` | no | Default `100` (lower = first) |
| `conditions` | no | Map or list (see below) |

**Conditions** — dict form:

```yaml
conditions:
  high_risk: true
  reachable: false
```

List form:

```yaml
conditions:
  - decision_point: high_risk
    expected: true
```

## Usage

### Load policy and evaluate

```python
from triage_rules.loader import load_policy_yaml
from triage_rules.engine import EvaluationEngine

loaded = load_policy_yaml("/path/to/policy.yaml", dataspace=product.dataspace)

rulesets = list(loaded["rulesets"].values())
result = EvaluationEngine().evaluate(product, rulesets, user=request.user)

if result.decision:
    print(result.decision.action, result.decision.timeline_days)
    print(result.vector)
```

### Run tests

```bash
.venv/bin/python manage.py test triage_rules --verbosity=2 --noinput
```

Ensure `triage_rules` is in `INSTALLED_APPS` (`dejacode/settings.py` →
`PROJECT_APPS`).

## Tests

| Area | Location |
|------|----------|
| Engine unit / integration | `tests.py` |
| Policy loader | `tests.py` → `PolicyLoaderTest` |
| Sample YAML | `tests/data/sample_policy.yaml` |
| Comprehensive E2E YAML | `tests/data/comprehensive_policy.yaml` |

The comprehensive E2E test loads a full policy, verifies DB objects (`Query`,
`Filter`, triage models), and runs multiple evaluation scenarios (upgrade,
reachability default, forensics, downgrade).

## Current limitations

- **No Product ↔ Ruleset assignment** — rulesets must be passed into
  `evaluate()` manually.
- **No persistence** — `EvaluationResult` is not stored on the product.
- **No admin UI** — models are not registered in Django admin yet.
- **No workflow hooks** — decisions do not create tickets or notifications.
- **Package/vulnerability aggregation is fixed to `any`** — see open questions.
- **Decisions are product-level only** — no per-package action lists yet.

## Open design questions

These need product decisions before the next implementation phase.

### Q1 — Package and vulnerability aggregation: `any` vs `all`?

**Current behavior:** package and vulnerability decision points use **any**
(existential) semantics.

| Mode | Meaning | Example |
|------|---------|---------|
| **any** (current) | At least one item matches | “Any package has critical risk” |
| **all** | Every item must match | “All packages use approved licenses” |

**Options:**

- **A.** Keep `any` only.
- **B.** Add `aggregation: any | all` on `DecisionPoint` for package/vulnerability
  targets (recommended if both are needed).
- **C.** Encode only via query design (limited for `all` cases).

**Recommendation:** add explicit `aggregation` on `DecisionPoint`, default `any`.

---

### Q2 — Decision scope: product label vs actionable targets?

**Current behavior:** one `TriageDecision` for the whole product. The engine does
not record which packages or vulnerabilities caused the match.

**Proposed split:**

| Action | Scope | Rationale |
|--------|-------|-----------|
| `upgrade` | Affected **packages** (optionally target version) | Inventory-specific remediation |
| `downgrade` | Affected **packages** | Same |
| `reachability` | **Product** | Analysis is product-wide |
| `forensics` | **Product** | Investigation is product-wide |

**Follow-up questions:**

1. Should `TriageDecision` include a **target version** for upgrade/downgrade?
2. One product label plus a list of affected packages, or one decision per package?
3. If multiple packages breach different predicates, same action for all or per-package actions?

**Recommendation:** keep one product-level decision as the primary label; extend
`EvaluationResult` with `affected_packages` / `affected_vulnerabilities` for
`upgrade`/`downgrade`; use product scope for `reachability` and `forensics`.

---

### Q3 — Should rulesets be assigned to products in the database?

**Current:** rulesets are passed at evaluation time.

**Question:** should `Product` have a M2M to `Ruleset` so evaluation is
`engine.evaluate(product)` without external lookup?

---

### Q4 — Should evaluation results be persisted?

**Current:** results are volatile.

**Question:** store last decision, vector, timestamp, and user on the product for
audit and UI?

---

### Q5 — Should evaluation always require a user?

**Current:** `user` is optional; product queries use `unsecured_objects`.

**Question:** in production, should evaluation always pass `user` for permission-aware
reporting queries?

---
