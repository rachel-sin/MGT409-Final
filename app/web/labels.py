"""Plain-language labels and CSS tier classes for the 5 SafetyLevel values —
keeps internal enum names (confirmed_dedicated_gf_prep, etc.) out of the UI,
which a first-time user shouldn't need to parse."""

SAFETY_LABELS = {
    "confirmed_dedicated_gf_prep": {
        "label": "Confirmed dedicated gluten-free prep",
        "tier_class": "tier-safe",
        "icon": "ti-circle-check",
    },
    "accommodates_caution_cross_contamination": {
        "label": "Accommodates — proceed with caution",
        "tier_class": "tier-caution",
        "icon": "ti-alert-triangle",
    },
    "unclear_gluten_specific": {
        "label": "Unclear — recommend contacting the restaurant",
        "tier_class": "tier-unclear",
        "icon": "ti-help-circle",
    },
    "no_evidence_found": {
        "label": "No evidence found",
        "tier_class": "tier-none",
        "icon": "ti-circle-dashed",
    },
    "credible_illness_report": {
        "label": "Caution — credible illness report",
        "tier_class": "tier-risk",
        "icon": "ti-alert-octagon",
    },
}

CONFIDENCE_LEVELS = {"low": 1, "medium": 2, "high": 3}


def safety_label(level: str) -> str:
    return SAFETY_LABELS.get(level, {}).get("label", level)


def safety_class(level: str) -> str:
    return SAFETY_LABELS.get(level, {}).get("tier_class", "tier-none")


def safety_icon(level: str) -> str:
    return SAFETY_LABELS.get(level, {}).get("icon", "ti-circle-dashed")


def confidence_dots(level: str) -> int:
    return CONFIDENCE_LEVELS.get(level, 0)
