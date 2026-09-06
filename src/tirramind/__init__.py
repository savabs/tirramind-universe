"""tirramind — survivorship-bias-free US listing ledger from SEC filings."""

from .store import snapshot, read_index

__version__ = "0.1.0"
__all__ = ["snapshot", "read_index", "__version__"]
