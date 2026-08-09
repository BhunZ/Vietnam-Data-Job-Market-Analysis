"""Per-source ingestion connectors."""

"""Per-source ingestion connectors.

TopCV was removed 2026-08-09. It is reachable only from a real logged-in browser —
DataDome fingerprints the TLS handshake, so `requests` gets 403 and ScraperAPI 500 — and a
source that needs a human every week is not a source an automated pipeline can claim.
vieclam24h was added in its place: same order of volume, fully automatable, and every
posting carries its description inline. See README §Sources.
"""

from .careerviet import CareerVietConnector
from .glints import GlintsConnector
from .itviec import ITviecConnector
from .topdev import TopDevConnector
from .vieclam24h import Vieclam24hConnector
from .vietnamworks import VietnamWorksConnector

CONNECTORS = {
    "itviec": ITviecConnector,
    "topdev": TopDevConnector,
    "vietnamworks": VietnamWorksConnector,
    "glints": GlintsConnector,
    "careerviet": CareerVietConnector,
    "vieclam24h": Vieclam24hConnector,
}
