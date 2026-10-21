"""Governance: who owns a metric, how trusted it is, and what may be queried.

Rules enforced here (not in the compiler, so policy can evolve
independently of SQL generation):

* certified metrics must have an owner, a description, and a tier of
  gold or silver — certification is a promise, and promises need owners;
* draft metrics are queryable only with ``allow_draft``;
* deprecated metrics are queryable only with ``allow_deprecated``, and
  deprecation should name a replacement;
* any metric without an owner is flagged, whatever its status.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import SemanticCatalog
from .errors import DeprecatedMetricError, DraftMetricError, GovernanceError
from .models import Metric, MetricStatus, Tier


@dataclass
class GovernanceIssue:
    metric: str
    rule: str
    detail: str

    def to_dict(self) -> dict:
        return {"metric": self.metric, "rule": self.rule, "detail": self.detail}


@dataclass
class GovernanceReport:
    issues: list[GovernanceIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def for_metric(self, name: str) -> list[GovernanceIssue]:
        return [i for i in self.issues if i.metric == name]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issue_count": len(self.issues),
                "issues": [i.to_dict() for i in self.issues]}


def check_metric(metric: Metric) -> list[GovernanceIssue]:
    issues: list[GovernanceIssue] = []
    if not metric.owner:
        issues.append(GovernanceIssue(
            metric.name, "owner_required", "metric has no owner"))
    if metric.status == MetricStatus.CERTIFIED:
        if not metric.description:
            issues.append(GovernanceIssue(
                metric.name, "certified_needs_description",
                "certified metric has no description"))
        if metric.tier == Tier.BRONZE:
            issues.append(GovernanceIssue(
                metric.name, "certified_needs_tier",
                "certified metric must be gold or silver tier"))
    if metric.status == MetricStatus.DEPRECATED and not metric.replaced_by:
        issues.append(GovernanceIssue(
            metric.name, "deprecation_needs_replacement",
            "deprecated metric does not name a replacement"))
    return issues


def audit_catalog(catalog: SemanticCatalog) -> GovernanceReport:
    issues: list[GovernanceIssue] = []
    for metric in catalog.list_metrics():
        issues.extend(check_metric(metric))
    return GovernanceReport(issues=issues)


def assert_queryable(metric: Metric, *, allow_draft: bool = False,
                     allow_deprecated: bool = False) -> None:
    """Gate a single metric for querying under the given opt-ins."""
    if metric.status == MetricStatus.DEPRECATED and not allow_deprecated:
        hint = f"; use {metric.replaced_by} instead" if metric.replaced_by else ""
        raise DeprecatedMetricError(
            f"metric {metric.name} is deprecated{hint} "
            f"(pass allow_deprecated to query it anyway)")
    if metric.status == MetricStatus.DRAFT and not allow_draft:
        raise DraftMetricError(
            f"metric {metric.name} is draft / uncertified "
            f"(pass allow_draft to query it anyway)")


def certify(metric: Metric) -> Metric:
    """Return a certified copy, refusing if it would break certification rules."""
    from dataclasses import replace
    candidate = replace(metric, status=MetricStatus.CERTIFIED)
    # check_metric on the candidate encodes the rules; any issue blocks.
    blocking = check_metric(candidate)
    if blocking:
        raise GovernanceError(
            f"cannot certify {metric.name}: "
            + "; ".join(f"{i.rule} ({i.detail})" for i in blocking))
    return candidate


def deprecate(metric: Metric, *, replaced_by: str) -> Metric:
    from dataclasses import replace
    if not replaced_by:
        raise GovernanceError("deprecation requires a replacement metric name")
    return replace(metric, status=MetricStatus.DEPRECATED, replaced_by=replaced_by)
