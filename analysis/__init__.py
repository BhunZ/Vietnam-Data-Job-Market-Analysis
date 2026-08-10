"""Read-only reporting over the warehouse.

Separate from `pipeline` on purpose: nothing here writes to DuckDB. These scripts open the
warehouse, check it, and print or plot — so a broken report can never corrupt the data it
describes.

This file exists so the directory is a real package. Without it `analysis` was not installed
alongside `pipeline`, and `import analysis.validate_gold` worked from the repo root and
nowhere else.
"""
