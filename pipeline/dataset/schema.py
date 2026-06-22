"""Annotation schema (Phase 3) — single source of truth for the 3-judge LLM output and the
human-verified Golden record. Controlled vocabularies are loaded from `ref/taxonomy/taxonomy_v2.yml`
so the YAML stays authoritative; validators reject out-of-vocab values (→ LLM retries on mismatch).

`JudgeAnnotation.model_json_schema()` is what we hand to each judge as the structured-output
contract. `GoldenRecord` is the adjudicated, released row. See codebook_v1.md / decision_tree_v1.md.
"""

from __future__ import annotations

from functools import lru_cache

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from ..utils.config import REPO_ROOT

TAXONOMY_PATH = REPO_ROOT / "ref" / "taxonomy" / "taxonomy_v2.yml"
TAXONOMY_VERSION = 2
CODEBOOK_VERSION = 1
DECISION_TREE_VERSION = 1


@lru_cache(maxsize=1)
def vocab() -> dict:
    """Controlled vocabularies pulled from taxonomy_v2.yml (authoritative)."""
    t = yaml.safe_load(TAXONOMY_PATH.open(encoding="utf-8"))
    facets = t["facets"]
    return {
        "functions": {f["code"] for f in t["functions"]},
        "task_tags": set(facets["task_tags"]["vocab"]),
        "artifacts": set(facets["artifact"]["vocab"]),
        "data_intensity": set(facets["data_intensity"]["vocab"]),
        "domains": set(facets["domain"]["vocab"]),
        "statuses": set(t["annotation_metadata"]["annotation_status"]["vocab"]),
        "confidence": set(t["annotation_metadata"]["confidence"]["vocab"]),
    }


_ORD = {"med": "medium", "mid": "medium", "hi": "high", "lo": "low"}  # common judge variants


class Evidence(BaseModel):
    span: str = Field(..., description="Verbatim JD quote that justifies the primary_function.")
    decision_tree_node_id: str = Field(..., description="Node id from decision_tree_v1 (S0..S8).")


class JudgeAnnotation(BaseModel):
    """One judge's structured output for one job. Out-of-vocab values raise → retry."""

    # Only `primary_function` (the ML target) is strict — invalid → raise → retry.
    # All auxiliary fields coerce/filter/default so a stray tag never nukes the primary label.
    primary_function: str
    secondary_functions: list[str] = Field(default_factory=list)
    task_tags: list[str] = Field(default_factory=list)
    artifact: str | None = None
    data_intensity: str = "medium"
    domain: str | None = None
    specialization: list[str] = Field(default_factory=list)
    evidence: Evidence | None = None
    confidence: str = "medium"
    annotation_status: str = "resolved"

    @field_validator("primary_function")
    @classmethod
    def _v_primary(cls, v: str) -> str:  # STRICT (the only one)
        if v not in vocab()["functions"]:
            raise ValueError(f"primary_function {v!r} not in {sorted(vocab()['functions'])}")
        return v

    @field_validator("secondary_functions", mode="before")
    @classmethod
    def _v_secondary(cls, v):  # drop unknowns
        return [x for x in (v or []) if x in vocab()["functions"]]

    @field_validator("task_tags", mode="before")
    @classmethod
    def _v_tasks(cls, v):  # drop unknowns
        return [x for x in (v or []) if x in vocab()["task_tags"]]

    @field_validator("data_intensity", mode="before")
    @classmethod
    def _v_di(cls, v):
        s = _ORD.get(str(v or "").strip().lower(), str(v or "").strip().lower())
        return s if s in vocab()["data_intensity"] else "medium"

    @field_validator("confidence", mode="before")
    @classmethod
    def _v_conf(cls, v):
        s = _ORD.get(str(v or "").strip().lower(), str(v or "").strip().lower())
        return s if s in vocab()["confidence"] else "medium"

    @field_validator("annotation_status", mode="before")
    @classmethod
    def _v_status(cls, v):
        s = str(v or "resolved").strip().lower()
        return s if s in vocab()["statuses"] else "resolved"

    @field_validator("artifact", mode="before")
    @classmethod
    def _v_artifact(cls, v):
        return v if v in vocab()["artifacts"] else None

    @field_validator("domain", mode="before")
    @classmethod
    def _v_domain(cls, v):
        return v if v in vocab()["domains"] else None

    @model_validator(mode="after")
    def _primary_not_in_secondary(self) -> "JudgeAnnotation":
        self.secondary_functions = [x for x in self.secondary_functions
                                    if x != self.primary_function]
        return self


class GoldenRecord(BaseModel):
    """Adjudicated, released row. Built from judge votes + human review."""

    job_id: str
    content_hash: str
    primary_function: str
    secondary_functions: list[str] = Field(default_factory=list)
    task_tags: list[str] = Field(default_factory=list)
    artifact: str | None = None
    data_intensity: str
    domain: str | None = None
    specialization: list[str] = Field(default_factory=list)
    seniority: str | None = None                 # reused from jobs_silver
    evidence: Evidence
    annotation_status: str = "resolved"
    is_borderline: bool = False
    source_of_truth: str = "human"               # 'human' | 'llm_auto_accept'
    # provenance
    taxonomy_version: int = TAXONOMY_VERSION
    codebook_version: int = CODEBOOK_VERSION
    decision_tree_version: int = DECISION_TREE_VERSION
    # internal QA (not part of the public label)
    llm_majority_function: str | None = None
    agreement_score: float | None = None
    reviewer: str | None = None
    adjudication_notes: str | None = None

    @field_validator("source_of_truth")
    @classmethod
    def _v_sot(cls, v: str) -> str:
        if v not in {"human", "llm_auto_accept"}:
            raise ValueError("source_of_truth must be 'human' or 'llm_auto_accept'")
        return v


def judge_json_schema() -> dict:
    """JSON schema handed to each LLM judge as its structured-output contract."""
    return JudgeAnnotation.model_json_schema()
