import os
import yaml
import pytest

def test_backend_dockerfile_security_and_healthcheck():
    """Verify backend Dockerfile implements non-root execution and healthcheck safeguards."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dockerfile_path = os.path.join(root_dir, "backend", "Dockerfile")
    assert os.path.exists(dockerfile_path), f"Backend Dockerfile not found at {dockerfile_path}"

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "USER appuser" in content, "Backend Dockerfile must run as non-root user (appuser)"
    assert "HEALTHCHECK" in content, "Backend Dockerfile must declare HEALTHCHECK instruction"
    assert "EXPOSE 8000" in content, "Backend Dockerfile must expose port 8000"

def test_frontend_dockerfile_structure():
    """Verify frontend Dockerfile utilizes multi-stage build and healthcheck."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dockerfile_path = os.path.join(root_dir, "frontend", "Dockerfile")
    assert os.path.exists(dockerfile_path), f"Frontend Dockerfile not found at {dockerfile_path}"

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "AS builder" in content, "Frontend Dockerfile must use multi-stage builder"
    assert "HEALTHCHECK" in content, "Frontend Dockerfile must declare HEALTHCHECK instruction"
    assert "EXPOSE 80" in content, "Frontend Dockerfile must expose port 80"

def test_docker_compose_configuration():
    """Verify docker-compose.yml defines all services, healthchecks, and dependency topologies."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    compose_path = os.path.join(root_dir, "docker-compose.yml")
    assert os.path.exists(compose_path), f"docker-compose.yml not found at {compose_path}"

    with open(compose_path, "r", encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)

    services = compose_data.get("services", {})
    assert "db" in services
    assert "backend" in services
    assert "worker" in services
    assert "frontend" in services

    # Verify healthchecks
    assert "healthcheck" in services["db"]
    assert "healthcheck" in services["backend"]

    # Verify dependency topology
    assert services["backend"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert services["worker"]["depends_on"]["backend"]["condition"] == "service_healthy"
    assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"

def test_github_actions_ci_workflow():
    """Verify GitHub Actions CI workflow file syntax and test stages."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ci_path = os.path.join(root_dir, ".github", "workflows", "ci.yml")
    assert os.path.exists(ci_path), f"ci.yml not found at {ci_path}"

    with open(ci_path, "r", encoding="utf-8") as f:
        ci_data = yaml.safe_load(f)

    assert "backend-test" in ci_data.get("jobs", {})
    assert "frontend-test" in ci_data.get("jobs", {})
