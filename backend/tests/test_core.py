import pytest
from app.services.parsers.dependency_parser import DependencyParser, clean_version
from app.services.ai_analyzer import calculate_weighted_score, classify_risk
from app.services.report_generator import ReportGenerator

def test_clean_version():
    assert clean_version("^18.2.0") == "18.2.0"
    assert clean_version("~2.1.0") == "2.1.0"
    assert clean_version(">=3.8.0, <4.0") == "3.8.0"
    assert clean_version("v1.5.0") == "1.5.0"
    assert clean_version("") == "latest"

def test_parse_package_json():
    content = """{
        "dependencies": {
            "react": "^18.2.0",
            "axios": "~1.5.0"
        },
        "devDependencies": {
            "typescript": "^5.0.0"
        }
    }"""
    deps = DependencyParser.parse("package.json", content)
    assert len(deps) == 3
    names = {d["name"]: d for d in deps}
    assert "react" in names
    assert names["react"]["installed_version"] == "18.2.0"
    assert names["react"]["is_direct_dep"] is True
    assert names["typescript"]["is_direct_dep"] is False

def test_parse_requirements_txt():
    content = """
    fastapi==0.100.0
    uvicorn>=0.23.0
    # comment line
    pydantic~=2.0.0; python_version > '3.8'
    """
    deps = DependencyParser.parse("requirements.txt", content)
    assert len(deps) == 3
    names = {d["name"]: d["installed_version"] for d in deps}
    assert names["fastapi"] == "0.100.0"
    assert names["uvicorn"] == "0.23.0"
    assert names["pydantic"] == "2.0.0"

def test_parse_cargo_toml():
    content = """
    [dependencies]
    serde = "1.0"
    tokio = { version = "1.28", features = ["full"] }
    """
    deps = DependencyParser.parse("Cargo.toml", content)
    assert len(deps) == 2
    names = {d["name"]: d["installed_version"] for d in deps}
    assert names["serde"] == "1.0"
    assert names["tokio"] == "1.28"

def test_parse_go_mod():
    content = """
    module myapp

    go 1.21

    require (
        github.com/gin-gonic/gin v1.9.1
        github.com/stretchr/testify v1.8.4 // indirect
    )
    """
    deps = DependencyParser.parse("go.mod", content)
    assert len(deps) == 2
    g = [d for d in deps if "gin-gonic" in d["name"]][0]
    assert g["installed_version"] == "1.9.1"
    assert g["is_direct_dep"] is True
    t = [d for d in deps if "testify" in d["name"]][0]
    assert t["is_direct_dep"] is False

def test_parse_pom_xml():
    content = """
    <project>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-web</artifactId>
                <version>3.1.2</version>
            </dependency>
        </dependencies>
    </project>
    """
    deps = DependencyParser.parse("pom.xml", content)
    assert len(deps) == 1
    assert deps[0]["name"] == "org.springframework.boot:spring-boot-starter-web"
    assert deps[0]["installed_version"] == "3.1.2"

def test_weighted_scoring_calculation():
    # 100 on all categories should yield 100.0
    score = calculate_weighted_score(100, 100, 100, 100, 100, 100, 100, 100)
    assert score == 100.0

    # Maintenance: 20%, Security: 20%, Currency: 15%, Community: 10%, Docs: 10%, Ecosystem: 10%, Sustainability: 10%, Complexity: 5%
    # Test specific values
    score_custom = calculate_weighted_score(50, 50, 50, 50, 50, 50, 50, 50)
    assert score_custom == 50.0

def test_risk_classification():
    assert classify_risk(95.0) == "Healthy"
    assert classify_risk(85.0) == "Healthy"
    assert classify_risk(75.0) == "Good"
    assert classify_risk(60.0) == "Needs Attention"
    assert classify_risk(40.0) == "High Risk"
    assert classify_risk(20.0) == "Critical"

def test_csv_report_generation():
    sample_data = {
        "overall_health_score": 85.0,
        "risk_classification": "Healthy",
        "scores": [
            {
                "technology_name": "react",
                "installed_version": "18.2.0",
                "latest_stable_version": "19.0.0",
                "overall_score": 88.0,
                "risk_classification": "Healthy",
                "maintenance_health": 90.0,
                "security_exposure": 90.0,
                "version_currency": 85.0,
                "community_activity": 90.0,
                "documentation_quality": 90.0,
                "ecosystem_compatibility": 90.0,
                "sustainability": 90.0,
                "upgrade_complexity": 85.0,
                "confidence_level": "High",
                "upgrade_complexity_level": "Low",
                "recommended_action": "Plan upgrade to 19"
            }
        ],
        "risks": [
            {
                "severity": "Low",
                "technology_name": "react",
                "title": "Minor version drift",
                "status": "Open",
                "business_impact": "None",
                "technical_impact": "None"
            }
        ]
    }
    csv_text = ReportGenerator.generate_csv("Test Project", sample_data)
    assert "TechDebt AI" in csv_text
    assert "react" in csv_text
    assert "88.0" in csv_text

def test_pdf_report_generation():
    sample_data = {
        "overall_health_score": 85.0,
        "risk_classification": "Healthy",
        "scores": [
            {
                "technology_name": "react",
                "installed_version": "18.2.0",
                "latest_stable_version": "19.0.0",
                "overall_score": 88.0,
                "risk_classification": "Healthy",
                "upgrade_complexity_level": "Low",
                "recommended_action": "Plan upgrade to 19"
            }
        ],
        "risks": []
    }
    pdf_bytes = ReportGenerator.generate_pdf("Test Project", sample_data)
    assert pdf_bytes.startswith(b"%PDF")

def test_parse_package_lock_json():
    content = """{
        "name": "my-app",
        "version": "1.0.0",
        "packages": {
            "": {"name": "my-app"},
            "node_modules/express": {"version": "4.18.2"},
            "node_modules/lodash": {"version": "4.17.21"}
        }
    }"""
    deps = DependencyParser.parse("package-lock.json", content)
    assert len(deps) == 2
    names = {d["name"]: d["installed_version"] for d in deps}
    assert names["express"] == "4.18.2"
    assert names["lodash"] == "4.17.21"

def test_parse_cargo_lock_and_csproj():
    cargo_lock = """
    [[package]]
    name = "tokio"
    version = "1.28.0"

    [[package]]
    name = "serde"
    version = "1.0.160"
    """
    deps = DependencyParser.parse("Cargo.lock", cargo_lock)
    assert len(deps) == 2
    names = {d["name"]: d["installed_version"] for d in deps}
    assert names["tokio"] == "1.28.0"
    assert names["serde"] == "1.0.160"

    csproj = """<Project Sdk="Microsoft.NET.Sdk">
      <ItemGroup>
        <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
      </ItemGroup>
    </Project>"""
    csdeps = DependencyParser.parse("App.csproj", csproj)
    assert len(csdeps) == 1
    assert csdeps[0]["name"] == "Newtonsoft.Json"
    assert csdeps[0]["installed_version"] == "13.0.1"
    assert csdeps[0]["ecosystem"] == "nuget"


