"""Pydantic models for the pipeline's typed layers.

Phase 1 only needs the Bronze record (one row per raw posting per source). Silver/Gold
models are added in later phases once the schema is agreed from real data.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BronzeJob(BaseModel):
    """One raw posting as scraped, before any normalization.

    Mirrors PROJECT_SPEC §5 Bronze: source, source_job_id, title_raw, company_raw,
    location_raw, description_raw, skills_raw, posted_date_raw, url, ingested_at.
    Raw strings are kept verbatim; cleaning happens in Silver. NO salary field by design.
    """

    source: str
    source_job_id: str
    title_raw: str | None = None
    company_raw: str | None = None
    location_raw: str | None = None
    description_raw: str | None = None
    skills_raw: list[str] = Field(default_factory=list)
    posted_date_raw: str | None = None
    url: str | None = None
    ingested_at: datetime

    # Source-specific extras captured during the spike (not yet in the canonical schema).
    extra: dict = Field(default_factory=dict)
