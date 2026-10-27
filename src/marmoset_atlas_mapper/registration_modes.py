"""Readable registration names, with aliases for saved pre-1.00 results."""

SKULL_BASE = "Landmarks (skull base)"
TOTAL = "Landmarks (total)"


def normalize_registration_type(value: str | None) -> str | None:
    return {
        "Landmark (Skull-base)": SKULL_BASE,
        "Landmark (Skull-all)": TOTAL,
    }.get(value, value)
