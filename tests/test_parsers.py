from repohealth.parsers import parse_package_json, parse_pyproject_toml, parse_requirements_txt


def test_requirements_txt():
    text = """# comment
requests==2.31.0
flask>=3.0
uvicorn[standard]==0.29.0
django; python_version >= "3.11"
-r other.txt
"""
    result = parse_requirements_txt(text)
    by_name = {dep.name: dep for dep in result.dependencies}
    assert set(by_name) == {"requests", "flask", "uvicorn", "django"}
    assert by_name["requests"].version == "2.31.0"
    assert by_name["flask"].version is None
    assert by_name["uvicorn"].version == "0.29.0"
    assert by_name["django"].version is None
    assert len(result.warnings) == 1  # The -r line.


def test_pyproject_toml():
    text = """
[project]
dependencies = ["requests==2.31.0", "flask>=3.0"]

[project.optional-dependencies]
dev = ["pytest==8.0.0"]
"""
    result = parse_pyproject_toml(text)
    by_name = {dep.name: dep for dep in result.dependencies}
    assert by_name["requests"].version == "2.31.0"
    assert by_name["pytest"].dev is True
    assert by_name["requests"].dev is False
    assert result.warnings == []


def test_pyproject_invalid_toml_warns():
    result = parse_pyproject_toml("[project\nbroken")
    assert result.dependencies == []
    assert len(result.warnings) == 1


def test_package_json():
    text = '{"dependencies": {"react": "^18.2.0"}, "devDependencies": {"jest": "~29.0.0"}}'
    result = parse_package_json(text)
    by_name = {dep.name: dep for dep in result.dependencies}
    assert by_name["react"].version == "18.2.0"
    assert by_name["react"].ecosystem == "npm"
    assert by_name["jest"].dev is True
