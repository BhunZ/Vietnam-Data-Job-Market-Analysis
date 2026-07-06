# Validation Checklist

Milestone 6 deliverable: validate the Family Gold tables before using them for
EDA, insight, dashboard, or report writing.

## Scope

Primary analysis should use `jobs_silver.job_family` and the `gold_*` Family
Gold tables. Legacy Gold tables remain useful as baseline/reference, but they
are not the main analytical layer.

## Checks

| Check | Expected | Result | Status |
|---|---:|---:|---|
| Analysis base rows: `jobs_silver` where `job_family != 'OTHER'`, active, non-duplicate | 852 | 852 | PASS |
| `gold_market_share.SUM(n)` equals analysis base | 852 | 852 | PASS |
| `gold_market_share.SUM(pct)` approximately equals 100 | ~100 | 99.9 | PASS, rounding |
| Duplicate grain in `gold_family_skill` (`job_family`, `skill`) | 0 | 0 | PASS |
| Duplicate grain in `gold_company` (`company_type`, `job_family`) | 0 | 0 | PASS |
| Duplicate grain in `gold_location` (`region`, `city`, `job_family`) | 0 | 0 | PASS |
| Duplicate grain in `gold_seniority` (`seniority`, `job_family`) | 0 | 0 | PASS |
| Duplicate grain in `gold_skill_cooccurrence` (`skill_a`, `skill_b`) | 0 | 0 | PASS |
| Bad unordered skill-pair ordering in `gold_skill_cooccurrence` | 0 | 0 | PASS |

## Top Market Share Evidence

| Rank | Job family | n | pct |
|---:|---|---:|---:|
| 1 | `BUSINESS_ANALYST` | 181 | 21.2 |
| 2 | `DATA_ENGINEER` | 149 | 17.5 |
| 3 | `DATA_ANALYST` | 125 | 14.7 |
| 4 | `AI_ENGINEER` | 118 | 13.8 |
| 5 | `RISK_FRAUD_ANALYST` | 52 | 6.1 |

## Reproduce

```bash
python analysis/validate_gold.py
```

## Interpretation

The Family Gold layer is internally consistent enough to use for Milestone 7
EDA and insight work. The `99.9` total percentage is expected because each
family percentage is rounded to one decimal place.

## Design Decision

Validation happens after Business Question Mapping and before EDA because
insights are only as trustworthy as their grain, filters, and metrics. This
keeps the report from explaining charts built on accidental duplicates,
wrong filters, or mismatched denominators.

## Limitations

- These checks validate internal consistency, not real-world representativeness.
- The dataset has one snapshot, so `trend` is descriptive only and should not be
  interpreted as forecasting.
- Salary analysis remains out of scope because the repo has no salary field.

