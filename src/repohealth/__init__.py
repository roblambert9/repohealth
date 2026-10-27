"""repohealth: dependency inventory, SPDX license risk, and CycloneDX SBOM output.

The core (parsers, license catalog, risk engine, SBOM builder, reporters) is
standard-library only. The optional FastAPI service lives in ``repohealth.api``
and is imported lazily by the ``serve`` CLI command.
"""

__version__ = "0.3.0"
