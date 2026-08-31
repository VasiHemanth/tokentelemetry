"""Translate quota-service responses into deterministic menu-bar display data.

This module deliberately has no macOS or ``rumps`` dependency.  The app layer
owns rendering and actions; this layer owns the shared quota wording and the
single worst-window choice that must match the dashboard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Tuple

from harness_panels.base import QUOTA_CRITICAL_AT, QUOTA_LABELS, QUOTA_WARN_AT


PresentationState = Literal["loading", "ready", "no_data", "failure"]
Severity = Literal["ok", "warn", "crit"]

# Keep the dashboard's normalized names, including quota types that its panel
# map does not render. Unknown future resource keys still get a readable name.
RESOURCE_LABELS = {
    **QUOTA_LABELS,
    "spark": "Spark",
    "sparkWeekly": "Spark weekly",
    "credits": "Credits",
    "extraUsage": "Extra usage",
    "rateLimitResets": "Rate-limit resets",
    "onDemand": "On-demand",
}


@dataclass(frozen=True)
class QuotaWindow:
    """A consumption window that can participate in the menu-bar headline."""

    provider_id: str
    provider_name: str
    resource_id: str
    resource_label: str
    pct: float
    severity: Severity


@dataclass(frozen=True)
class MenuBarRow:
    """A single resource to render below its provider name in the menu."""

    provider_id: str
    provider_name: str
    plan: Optional[str]
    resource_id: str
    resource_label: str
    text: str
    pct: Optional[float]
    severity: Optional[Severity]


@dataclass(frozen=True)
class MenuBarPresentation:
    """Complete, renderer-agnostic state for the quota portion of the menu."""

    state: PresentationState
    title: str
    severity: Optional[Severity]
    worst_window: Optional[QuotaWindow]
    rows: Tuple[MenuBarRow, ...]
    not_supported_count: int
    failure_message: Optional[str]


def build_menu_presentation(
    response: Optional[Mapping[str, Any]],
    *,
    loading: bool = False,
    failure: Optional[str] = None,
) -> MenuBarPresentation:
    """Build deterministic display data from one ``QuotaService.collect`` result.

    ``loading`` and ``failure`` represent failures outside quota collection (for
    example, a timer callback). A response may contain both cached provider data
    and refresh errors; cached data remains useful, so it stays ``ready`` when
    at least one consumption window is available.
    """

    if loading:
        return _empty_presentation("loading")
    if failure:
        return _empty_presentation("failure", failure_message=failure)
    if response is None:
        return _empty_presentation("no_data")

    providers = response.get("providers")
    if not isinstance(providers, Mapping):
        return _empty_presentation("failure", failure_message="Quota data is unavailable.")

    not_supported_count = _not_supported_count(response.get("capabilities"))
    rows = []
    windows = []
    for provider_id, snapshot in sorted(providers.items(), key=lambda item: str(item[0])):
        if not isinstance(provider_id, str) or not isinstance(snapshot, Mapping):
            continue
        provider_name = _text(snapshot.get("displayName")) or provider_id
        plan = _text(snapshot.get("plan"))
        resources = snapshot.get("resources")
        if not isinstance(resources, Mapping):
            continue
        for resource_id, resource in sorted(resources.items(), key=lambda item: str(item[0])):
            if not isinstance(resource_id, str) or not isinstance(resource, Mapping):
                continue
            label = quota_resource_label(resource_id)
            pct = quota_percent(resource)
            severity = _severity(pct) if pct is not None else None
            text = _resource_text(resource, pct)
            if text is None:
                continue
            rows.append(MenuBarRow(
                provider_id=provider_id,
                provider_name=provider_name,
                plan=plan,
                resource_id=resource_id,
                resource_label=label,
                text=text,
                pct=pct,
                severity=severity,
            ))
            if pct is not None:
                windows.append(QuotaWindow(
                    provider_id=provider_id,
                    provider_name=provider_name,
                    resource_id=resource_id,
                    resource_label=label,
                    pct=pct,
                    severity=severity,
                ))

    worst = min(windows, key=lambda window: (-window.pct, window.provider_id, window.resource_id), default=None)
    if worst is None:
        message = _response_failure(response)
        if message:
            return MenuBarPresentation(
                state="failure",
                title="◔ Quota unavailable",
                severity=None,
                worst_window=None,
                rows=tuple(rows),
                not_supported_count=not_supported_count,
                failure_message=message,
            )
        return MenuBarPresentation(
            state="no_data",
            title="◔ No quota data",
            severity=None,
            worst_window=None,
            rows=tuple(rows),
            not_supported_count=not_supported_count,
            failure_message=None,
        )

    return MenuBarPresentation(
        state="ready",
        title=f"◔ {_rounded_percent(worst.pct)}%",
        severity=worst.severity,
        worst_window=worst,
        rows=tuple(rows),
        not_supported_count=not_supported_count,
        failure_message=None,
    )


def quota_resource_label(resource_id: str) -> str:
    """Return the dashboard's label for a normalized quota resource."""

    return RESOURCE_LABELS.get(resource_id, _humanize(resource_id))


def quota_percent(resource: Mapping[str, Any]) -> Optional[float]:
    """Return consumed percentage for resources with a real, positive ceiling."""

    used = _number(resource.get("used"))
    limit = _number(resource.get("limit"))
    if used is None or limit is None or limit <= 0:
        return None
    return min(100.0, max(0.0, used / limit * 100.0))


def _empty_presentation(state: PresentationState, failure_message: Optional[str] = None) -> MenuBarPresentation:
    titles = {
        "loading": "◔ Loading…",
        "no_data": "◔ No quota data",
        "failure": "◔ Quota unavailable",
    }
    return MenuBarPresentation(
        state=state,
        title=titles[state],
        severity=None,
        worst_window=None,
        rows=(),
        not_supported_count=0,
        failure_message=failure_message,
    )


def _resource_text(resource: Mapping[str, Any], pct: Optional[float]) -> Optional[str]:
    if pct is not None:
        return "Limit reached" if pct >= 100 else f"{_rounded_percent(pct)}% used"
    available = _number(resource.get("available"))
    unit = _text(resource.get("unit"))
    if available is not None and unit:
        return f"{_amount(available, unit)} available"
    used = _number(resource.get("used"))
    if used is not None and unit:
        return f"{_amount(used, unit)} used"
    return None


def _not_supported_count(capabilities: Any) -> int:
    if not isinstance(capabilities, Mapping):
        return 0
    return sum(
        1 for capability in capabilities.values()
        if isinstance(capability, Mapping) and capability.get("state") == "notSupported"
    )


def _response_failure(response: Mapping[str, Any]) -> Optional[str]:
    errors = response.get("errors")
    if not isinstance(errors, (list, tuple)):
        return None
    for error in errors:
        if isinstance(error, Mapping) and (message := _text(error.get("message"))):
            return message
    return None


def _severity(pct: float) -> Severity:
    if pct >= QUOTA_CRITICAL_AT:
        return "crit"
    if pct >= QUOTA_WARN_AT:
        return "warn"
    return "ok"


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _rounded_percent(pct: float) -> int:
    return int(math.floor(pct + 0.5))


def _amount(value: float, unit: str) -> str:
    if unit == "usd":
        return f"${value:.2f}" if value < 10 else f"${value:.0f}"
    if unit == "percent":
        return f"{_rounded_percent(value)}%"
    number = str(int(value)) if value.is_integer() else f"{value:.1f}"
    return f"{number} {unit}"


def _humanize(value: str) -> str:
    result = []
    for index, character in enumerate(value):
        if index and character.isupper() and value[index - 1].islower():
            result.append(" ")
        result.append(character)
    return "".join(result).capitalize()
