"""Job Family Labeling Engine — standalone, reusable.

Assigns each job a hierarchical `job_family` (Domain → Sub-domain → Family) from title + JD +
skills, via a 3-tier cascade (rule → embedding → multi-LLM voting) with confidence + review status.
Entry point: `from job_family_engine.engine import predict, run_corpus`.
"""
