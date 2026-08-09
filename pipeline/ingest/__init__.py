"""Per-source ingestion connectors."""

from .careerviet import CareerVietConnector
from .glints import GlintsConnector
from .itviec import ITviecConnector
from .topcv import TopCVConnector
from .topdev import TopDevConnector
from .vieclam24h import Vieclam24hConnector
from .vietnamworks import VietnamWorksConnector

CONNECTORS = {
    "itviec": ITviecConnector,
    "topdev": TopDevConnector,
    "vietnamworks": VietnamWorksConnector,
    "glints": GlintsConnector,
    "topcv": TopCVConnector,
    "careerviet": CareerVietConnector,
    "vieclam24h": Vieclam24hConnector,
}
