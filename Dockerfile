# Runtime for the pipeline. The point is not portability for its own sake — it is that this
# project used to run in exactly one place. The test suite passed on the author's laptop and
# failed everywhere else, because two things it needed came from the local machine rather than
# from the repository: a `.env` that decided which LLM judges existed, and a working directory
# that made `analysis` importable. Both are fixed in the code; this file makes the rest of the
# environment a declared artifact too.
#
# Python is read from .python-version — the same file GitHub Actions reads — so there is one
# answer to "which interpreter", not three.
FROM python:3.12-slim

# Faster, quieter, and no .pyc written into a layer that will be thrown away.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# lxml needs a C toolchain to build if no wheel matches. Installed, used, and removed in one
# layer so the compiler does not travel in the image.
COPY requirements.lock ./
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && pip install -r requirements.lock \
 && apt-get purge -y --auto-remove build-essential \
 && rm -rf /var/lib/apt/lists/*

# Source last: dependencies change rarely, code changes constantly, and this ordering means a
# code edit rebuilds one small layer instead of reinstalling everything.
COPY pyproject.toml README.md ./
COPY pipeline/ ./pipeline/
COPY job_family_engine/ ./job_family_engine/
COPY analysis/ ./analysis/
COPY config/ ./config/
# Reference dictionaries read at run time by pipeline/transform/normalize.py — skills,
# seniority rules, company types, role keywords. Leaving them out cost 31 tests in the first
# image build, all with a FileNotFoundError that pointed at a path nobody had declared anywhere.
COPY ref/ ./ref/
# The suite travels with the image on purpose: it is the proof that this environment works,
# and it must be runnable by whoever received the image rather than only by whoever built it.
COPY tests/ ./tests/
RUN pip install --no-deps -e .

# Data is a volume, not a layer. The warehouse is written on every run; baking it in would make
# each image carry a snapshot that is stale the moment it is built.
VOLUME ["/app/data"]

# Secrets arrive as environment variables at run time. Nothing here reads a .env from the image,
# and none is ever copied in — see .dockerignore.
#
# The embedding tier (`build-text`, and tier 2 of `label`) needs sentence-transformers, which
# pulls in torch and roughly two more gigabytes. It is deliberately not installed: everything
# else — scrape, load, gate, silver, gold, validate, and the LLM judging tiers — runs without it.
# Add it with `pip install -e .[dataset]` inside the container if you need that tier.
ENTRYPOINT ["python", "-m", "pipeline"]
CMD ["--help"]
