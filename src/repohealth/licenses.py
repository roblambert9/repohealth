"""SPDX license catalog, normalization, and pairwise compatibility model.

Design notes (read before changing the rules):

- The catalog covers the licenses a working scanner meets most often. It is
  intentionally small: every entry is a real SPDX identifier with a tier the
  author can defend. Unknown strings are never guessed into a tier; they
  become :class:`UnknownLicense` and force a REVIEW finding.
- Tiers: ``permissive`` (MIT, Apache-2.0, BSD, ISC, ...), ``weak-copyleft``
  (MPL-2.0, LGPL), ``strong-copyleft`` (GPL), ``network-copyleft`` (AGPL).
- Pairwise compatibility is conservative by design. Where real-world
  compatibility depends on secondary-license notices or linking details the
  scanner cannot see (notably MPL-2.0 combined with GPL-family licenses),
  the model returns REVIEW, not a verdict. A REVIEW is a human task, not a
  pass.
- This module is not legal advice and its output must never be presented as
  a legal opinion. The Markdown reporter carries that disclaimer on every
  report.
"""

from __future__ import annotations

from dataclasses import dataclass

PERMISSIVE = "permissive"
WEAK = "weak-copyleft"
STRONG = "strong-copyleft"
NETWORK = "network-copyleft"


@dataclass(frozen=True)
class LicenseInfo:
    spdx_id: str
    name: str
    tier: str
    osi_approved: bool = True
    notes: str = ""


@dataclass(frozen=True)
class UnknownLicense:
    """A license string the catalog cannot map. Never silently treated as safe."""

    raw: str
    reason: str
    spdx_id: str | None = None


License = LicenseInfo | UnknownLicense


CATALOG: dict[str, LicenseInfo] = {
    "MIT": LicenseInfo("MIT", "MIT License", PERMISSIVE),
    "Apache-2.0": LicenseInfo("Apache-2.0", "Apache License 2.0", PERMISSIVE),
    "BSD-2-Clause": LicenseInfo("BSD-2-Clause", "BSD 2-Clause License", PERMISSIVE),
    "BSD-3-Clause": LicenseInfo("BSD-3-Clause", "BSD 3-Clause License", PERMISSIVE),
    "ISC": LicenseInfo("ISC", "ISC License", PERMISSIVE),
    "Zlib": LicenseInfo("Zlib", "zlib License", PERMISSIVE),
    "Unlicense": LicenseInfo("Unlicense", "The Unlicense", PERMISSIVE, osi_approved=False),
    "CC0-1.0": LicenseInfo("CC0-1.0", "Creative Commons Zero v1.0 Universal", PERMISSIVE, osi_approved=False),
    "PSF-2.0": LicenseInfo("PSF-2.0", "Python Software Foundation License 2.0", PERMISSIVE),
    "BSL-1.0": LicenseInfo("BSL-1.0", "Boost Software License 1.0", PERMISSIVE),
    "MPL-2.0": LicenseInfo("MPL-2.0", "Mozilla Public License 2.0", WEAK),
    "LGPL-2.0-only": LicenseInfo("LGPL-2.0-only", "GNU Lesser General Public License v2.0 only", WEAK),
    "LGPL-2.1-only": LicenseInfo("LGPL-2.1-only", "GNU Lesser General Public License v2.1 only", WEAK),
    "LGPL-3.0-only": LicenseInfo("LGPL-3.0-only", "GNU Lesser General Public License v3.0 only", WEAK),
    "GPL-2.0-only": LicenseInfo("GPL-2.0-only", "GNU General Public License v2.0 only", STRONG),
    "GPL-3.0-only": LicenseInfo("GPL-3.0-only", "GNU General Public License v3.0 only", STRONG),
    "AGPL-3.0-only": LicenseInfo("AGPL-3.0-only", "GNU Affero General Public License v3.0 only", NETWORK),
}

# Human-written strings mapped to SPDX ids. Keys are normalized by
# _normalize_key(); anything absent here falls through to UnknownLicense.
_ALIASES: dict[str, str] = {
    "mit": "MIT",
    "mit license": "MIT",
    "mit licence": "MIT",
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "simplified bsd": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "new bsd": "BSD-3-Clause",
    "isc": "ISC",
    "isc license": "ISC",
    "zlib": "Zlib",
    "zlib/libpng license": "Zlib",
    "unlicense": "Unlicense",
    "the unlicense": "Unlicense",
    "cc0-1.0": "CC0-1.0",
    "cc0": "CC0-1.0",
    "psf-2.0": "PSF-2.0",
    "psf": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "bsl-1.0": "BSL-1.0",
    "boost software license 1.0": "BSL-1.0",
    "mpl-2.0": "MPL-2.0",
    "mpl 2.0": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "lgpl-2.0-only": "LGPL-2.0-only",
    "lgpl-2.0": "LGPL-2.0-only",
    "lgpl-2.1-only": "LGPL-2.1-only",
    "lgpl-2.1": "LGPL-2.1-only",
    "gnu lesser general public license v2.1": "LGPL-2.1-only",
    "lgpl-3.0-only": "LGPL-3.0-only",
    "lgpl-3.0": "LGPL-3.0-only",
    "gnu lesser general public license v3.0": "LGPL-3.0-only",
    "gpl-2.0-only": "GPL-2.0-only",
    "gpl-2.0": "GPL-2.0-only",
    "gpl v2": "GPL-2.0-only",
    "gnu general public license v2": "GPL-2.0-only",
    "gpl-3.0-only": "GPL-3.0-only",
    "gpl-3.0": "GPL-3.0-only",
    "gpl v3": "GPL-3.0-only",
    "gnu general public license v3": "GPL-3.0-only",
    "agpl-3.0-only": "AGPL-3.0-only",
    "agpl-3.0": "AGPL-3.0-only",
    "agpl v3": "AGPL-3.0-only",
    "gnu affero general public license v3": "AGPL-3.0-only",
}

# Strings that name a family but not a version or clause count. Mapping one of
# these to a specific license would be a guess, so they stay unknown.
_AMBIGUOUS = {
    "bsd",
    "bsd license",
    "gpl",
    "lgpl",
    "agpl",
    "apache",
    "apache license",
    "mozilla public license",
    "general public license",
}


def _normalize_key(raw: str) -> str:
    """Reduce a license string to a lookup key.

    Handles trove-classifier tails ("License :: OSI Approved :: MIT License"
    -> "MIT License") and case/punctuation variation.
    """
    text = raw.strip()
    if "::" in text:
        text = text.split("::")[-1].strip()
    text = text.lower().replace("_", "-").replace("licence", "license")
    # Collapse runs of spaces and strip a trailing " license" only when the
    # remainder still identifies something ("mit license" -> "mit").
    text = " ".join(text.split())
    return text


def normalize(raw: str) -> License:
    """Map a raw license string to a catalog entry or UnknownLicense."""
    if not raw or not raw.strip():
        return UnknownLicense(raw=raw, reason="empty license string")
    key = _normalize_key(raw)
    if key in _AMBIGUOUS:
        return UnknownLicense(raw=raw, reason=f"ambiguous license family: {raw.strip()!r} names no version")
    # Direct SPDX id match, case-insensitive.
    for spdx_id, info in CATALOG.items():
        if spdx_id.lower() == key:
            return info
    spdx_id = _ALIASES.get(key)
    if spdx_id is not None:
        return CATALOG[spdx_id]
    return UnknownLicense(raw=raw, reason=f"unrecognized license string: {raw.strip()!r}")


# Pairs whose combination is a known hard conflict (version-family mismatch).
_CONFLICTS: frozenset[frozenset[str]] = frozenset(
    [
        frozenset(["GPL-2.0-only", "GPL-3.0-only"]),
        frozenset(["LGPL-2.1-only", "GPL-3.0-only"]),
        frozenset(["LGPL-3.0-only", "GPL-2.0-only"]),
        frozenset(["LGPL-2.1-only", "LGPL-3.0-only"]),
        frozenset(["LGPL-2.1-only", "AGPL-3.0-only"]),
        frozenset(["GPL-2.0-only", "AGPL-3.0-only"]),
    ]
)

# Pairs explicitly compatible across the copyleft boundary.
_COMPATIBLE: frozenset[frozenset[str]] = frozenset(
    [
        frozenset(["LGPL-2.1-only", "GPL-2.0-only"]),
        frozenset(["LGPL-3.0-only", "GPL-3.0-only"]),
        frozenset(["LGPL-3.0-only", "AGPL-3.0-only"]),
        frozenset(["GPL-3.0-only", "AGPL-3.0-only"]),
    ]
)


def pair_status(a: License, b: License) -> tuple[str, str]:
    """Assess two licenses combined in one product.

    Returns (status, reason) where status is one of "compatible",
    "conflict", or "review".
    """
    if isinstance(a, UnknownLicense) or isinstance(b, UnknownLicense):
        unknown = a if isinstance(a, UnknownLicense) else b
        return ("review", f"unassessable license: {unknown.reason}")
    if a.spdx_id == b.spdx_id:
        return ("compatible", "same license")
    if a.tier == PERMISSIVE or b.tier == PERMISSIVE:
        return ("compatible", "permissive license combines freely")
    pair = frozenset([a.spdx_id, b.spdx_id])
    if pair in _CONFLICTS:
        return ("conflict", f"{a.spdx_id} and {b.spdx_id} are version-incompatible")
    if pair in _COMPATIBLE:
        return ("compatible", f"{a.spdx_id} may be combined under {b.spdx_id} terms")
    return (
        "review",
        f"{a.spdx_id} combined with {b.spdx_id} needs human review "
        "(secondary-license or linking details not visible to the scanner)",
    )
