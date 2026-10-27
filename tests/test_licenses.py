from repohealth.licenses import CATALOG, UnknownLicense, normalize, pair_status


def test_normalize_common_strings():
    assert normalize("MIT License").spdx_id == "MIT"
    assert normalize("Apache License, Version 2.0").spdx_id == "Apache-2.0"
    assert normalize("BSD 3-Clause").spdx_id == "BSD-3-Clause"
    assert normalize("Mozilla Public License 2.0").spdx_id == "MPL-2.0"
    assert normalize("License :: OSI Approved :: MIT License").spdx_id == "MIT"


def test_normalize_deprecated_ids_map_to_only_variants():
    assert normalize("GPL-3.0").spdx_id == "GPL-3.0-only"
    assert normalize("LGPL-2.1").spdx_id == "LGPL-2.1-only"


def test_normalize_never_guesses():
    assert isinstance(normalize("BSD"), UnknownLicense)
    assert isinstance(normalize("GPL"), UnknownLicense)
    assert isinstance(normalize(""), UnknownLicense)
    assert isinstance(normalize("MadeUpLicense 9.9"), UnknownLicense)


def test_pair_status_compatible():
    mit, gpl3 = CATALOG["MIT"], CATALOG["GPL-3.0-only"]
    assert pair_status(mit, gpl3)[0] == "compatible"
    assert pair_status(mit, mit)[0] == "compatible"
    assert pair_status(CATALOG["GPL-3.0-only"], CATALOG["AGPL-3.0-only"])[0] == "compatible"
    assert pair_status(CATALOG["LGPL-3.0-only"], CATALOG["GPL-3.0-only"])[0] == "compatible"


def test_pair_status_conflict():
    assert pair_status(CATALOG["GPL-2.0-only"], CATALOG["GPL-3.0-only"])[0] == "conflict"
    assert pair_status(CATALOG["LGPL-2.1-only"], CATALOG["GPL-3.0-only"])[0] == "conflict"
    assert pair_status(CATALOG["GPL-2.0-only"], CATALOG["AGPL-3.0-only"])[0] == "conflict"


def test_pair_status_review_for_nuanced_or_unknown():
    assert pair_status(CATALOG["MPL-2.0"], CATALOG["GPL-3.0-only"])[0] == "review"
    assert pair_status(UnknownLicense("GPL", "ambiguous"), CATALOG["MIT"])[0] == "review"
