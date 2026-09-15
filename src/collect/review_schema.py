"""Define the shared privacy-safe schema for app-store reviews.

Platform and canonical-product identity stay on every row so listings from different stores or
similarly branded products can be compared without being silently pooled.
"""

from __future__ import annotations

from typing import Any

REVIEW_FIELDS = (
    "review_id",
    "platform",
    "platform_app_id",
    "product_id",
    "text",
    "rating",
    "timestamp",
    "app_version",
    "helpful_count",
)


def review_record(
    *,
    review_id: Any,
    platform: str,
    platform_app_id: str,
    product_id: str,
    text: Any,
    rating: Any,
    timestamp: Any,
    app_version: Any,
    helpful_count: Any,
) -> dict[str, Any]:
    """Build one review record in stable field order."""
    return {
        "review_id": review_id,
        "platform": platform,
        "platform_app_id": platform_app_id,
        "product_id": product_id,
        "text": text,
        "rating": rating,
        "timestamp": timestamp,
        "app_version": app_version,
        "helpful_count": helpful_count,
    }
