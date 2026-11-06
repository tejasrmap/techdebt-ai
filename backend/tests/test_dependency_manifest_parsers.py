import pytest
from app.services.parsers.dependency_parser import DependencyParser

def test_pnpm_lock_parsing():
    content = """
lockfileVersion: 5.4

packages:
  /@types/node@18.11.9:
    resolution: {integrity: sha512-vErqGrDunF07QoGAlAIBPQLY5z0Si1gkQvBi366pqofPOfV83ASU3138Rhp8h+e2KPQh0voU37wcIBKB54oGBA==}
    dev: true

  /react@18.2.0:
    resolution: {integrity: sha512-/3IjMdb2L9QbBdWiW5e3P2/npwMBaU9mHCSCUzNln0ZCYbcfTsGbTJrU/kGemcgSJO9hcWRh82ucrTr+3uZ73g==}
    dependencies:
      loose-envify: 1.4.0
    dev: false
"""
    deps = DependencyParser.parse("pnpm-lock.yaml", content)
    assert len(deps) == 2
    names = {d["name"]: d["installed_version"] for d in deps}
    assert names["@types/node"] == "18.11.9"
    assert names["react"] == "18.2.0"

def test_pipfile_and_pipfile_lock_parsing():
    pipfile_content = """
[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]
fastapi = ">=0.95.0"
sqlalchemy = "~=2.0.0"

[dev-packages]
pytest = ">=7.0.0"
"""
    deps = DependencyParser.parse("Pipfile", pipfile_content)
    assert len(deps) == 3
    fastapi_dep = next(d for d in deps if d["name"] == "fastapi")
    assert fastapi_dep["installed_version"] == "0.95.0"
    assert not fastapi_dep.get("is_dev", False)

    pytest_dep = next(d for d in deps if d["name"] == "pytest")
    assert pytest_dep["is_dev"] is True

    # Pipfile.lock
    lock_content = """
{
    "_meta": {"hash": {"sha256": "123"}},
    "default": {
        "fastapi": {"version": "==0.95.2"}
    },
    "develop": {
        "pytest": {"version": "==7.3.1"}
    }
}
"""
    lock_deps = DependencyParser.parse("Pipfile.lock", lock_content)
    assert len(lock_deps) == 2
    assert next(d["installed_version"] for d in lock_deps if d["name"] == "fastapi") == "0.95.2"

def test_gemfile_and_gemfile_lock_parsing():
    gemfile_content = """
source 'https://rubygems.org'
gem 'rails', '~> 7.0.4'
gem 'pg', '>= 1.4'
"""
    deps = DependencyParser.parse("Gemfile", gemfile_content)
    assert len(deps) == 2
    assert next(d["name"] for d in deps if "rails" in d["name"]) == "rails"

    lock_content = """
GEM
  remote: https://rubygems.org/
  specs:
    actionpack (7.0.4.3)
    rails (7.0.4.3)
      actionpack (= 7.0.4.3)

DEPENDENCIES
  rails (~> 7.0.4)
"""
    lock_deps = DependencyParser.parse("Gemfile.lock", lock_content)
    assert len(lock_deps) == 2
    assert next(d["installed_version"] for d in lock_deps if d["name"] == "rails") == "7.0.4.3"

def test_pom_xml_property_interpolation():
    pom_content = """
<project>
    <properties>
        <spring.boot.version>3.1.2</spring.boot.version>
        <junit.version>5.9.3</junit.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>${spring.boot.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
"""
    deps = DependencyParser.parse("pom.xml", pom_content)
    assert len(deps) == 2
    spring_dep = next(d for d in deps if "spring-boot-starter-web" in d["name"])
    assert spring_dep["installed_version"] == "3.1.2"
    assert spring_dep["is_dev"] is False

    junit_dep = next(d for d in deps if "junit-jupiter" in d["name"])
    assert junit_dep["installed_version"] == "5.9.3"
    assert junit_dep["is_dev"] is True

def test_package_json_and_requirements():
    pkg_json = '{"dependencies": {"express": "^4.18.2"}, "devDependencies": {"jest": "~29.5.0"}}'
    deps = DependencyParser.parse("package.json", pkg_json)
    assert len(deps) == 2
    assert next(d["installed_version"] for d in deps if d["name"] == "express") == "4.18.2"

    reqs = "requests>=2.28.0; python_version >= '3.8'\nblack==23.3.0"
    py_deps = DependencyParser.parse("requirements.txt", reqs)
    assert len(py_deps) == 2
    assert next(d["name"] for d in py_deps if d["name"] == "requests") == "requests"
