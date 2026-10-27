from repohealth.licenses import CATALOG, UnknownLicense
from repohealth.resolver import ResolvedDependency
from repohealth.risk import FAIL, PASS, REVIEW, Policy, assess


def _dep(name, license, resolver="stub"):
    return ResolvedDependency(
        name=name, version="1.0", spec="==1.0", ecosystem="pypi",
        source="requirements.txt", dev=False, license=license, resolver=resolver,
    )


def test_all_permissive_passes():
    result = assess([_dep("a", CATALOG["MIT"]), _dep("b", CATALOG["Apache-2.0"])], Policy())
    assert result.verdict == PASS


def test_denied_license_fails():
    policy = Policy(denied=frozenset(["GPL-3.0-only"]))
    result = assess([_dep("a", CATALOG["GPL-3.0-only"])], policy)
    assert result.verdict == FAIL
    assert any(f.component == "a" and f.level == FAIL for f in result.findings)


def test_warn_license_reviews():
    policy = Policy(warn=frozenset(["AGPL-3.0-only"]))
    result = assess([_dep("a", CATALOG["AGPL-3.0-only"])], policy)
    assert result.verdict == REVIEW


def test_unknown_reviews_by_default_and_fails_when_configured():
    dep = _dep("a", UnknownLicense("Mystery", "unrecognized"))
    assert assess([dep], Policy()).verdict == REVIEW
    assert assess([dep], Policy(fail_on_unknown=True)).verdict == FAIL


def test_version_conflict_fails():
    result = assess(
        [_dep("a", CATALOG["GPL-2.0-only"]), _dep("b", CATALOG["GPL-3.0-only"])], Policy()
    )
    assert result.verdict == FAIL
    assert any(f.component.startswith("pair:") for f in result.findings)


def test_compatible_pair_does_not_fail():
    result = assess(
        [_dep("a", CATALOG["MIT"]), _dep("b", CATALOG["GPL-3.0-only"])], Policy()
    )
    assert result.verdict == PASS
