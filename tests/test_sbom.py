from repohealth.licenses import CATALOG, UnknownLicense
from repohealth.resolver import ResolvedDependency
from repohealth.sbom import build_cyclonedx


def _dep(name, version, license):
    return ResolvedDependency(
        name=name, version=version, spec="", ecosystem="pypi",
        source="requirements.txt", dev=False, license=license, resolver="stub",
    )


def test_cyclonedx_shape():
    sbom = build_cyclonedx(
        "demo",
        [
            _dep("requests", "2.31.0", CATALOG["Apache-2.0"]),
            _dep("mystery", None, UnknownLicense("MysterySoft", "unrecognized")),
        ],
    )
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["metadata"]["component"]["name"] == "demo"
    assert len(sbom["components"]) == 2
    known, unknown = sbom["components"]
    assert known["purl"] == "pkg:pypi/requests@2.31.0"
    assert known["licenses"] == [{"license": {"id": "Apache-2.0"}}]
    assert known["version"] == "2.31.0"
    assert unknown["licenses"] == [{"license": {"name": "MysterySoft"}}]
    assert "version" not in unknown  # No version invented.
