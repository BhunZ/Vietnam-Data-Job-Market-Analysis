"""Dataset-engineering layer: data discovery, taxonomy proposal, and (deferred)
LLM-first annotation → human-verified Golden Set.

This package builds a traceable, reproducible, public-grade labeled dataset on top of
the warehouse `jobs_silver`/`jobs` tables. Artifacts are immutable and provenance-tracked
via data/dataset/manifests/MANIFEST.jsonl. See plan + PROJECT_STATUS for the staged design.

Phase 1 (discovery) + Phase 2 (taxonomy proposal) execute now; annotation/golden/metrics
are designed but gated behind user approval of the taxonomy.
"""
