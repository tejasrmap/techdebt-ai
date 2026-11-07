"""
TechDebt AI v3.1.0 — Test Suite for Architecture Intelligence Engine,
Tarjan SCC Cycle Detection, Coupling Metrics, and Layering Checks (GAP-ARCH-01).
"""

import pytest
from app.services.architecture_review_engine import ArchitectureReviewEngine


def test_import_extraction_multilanguage():
    # Python
    py_code = "from services.auth import verify_token\nimport models.user\n"
    py_imports = ArchitectureReviewEngine.extract_imports_from_source(py_code, "api/auth.py")
    assert "services.auth" in py_imports
    assert "models.user" in py_imports

    # TypeScript
    ts_code = "import { User } from '../models/user';\nconst config = require('./config');"
    ts_imports = ArchitectureReviewEngine.extract_imports_from_source(ts_code, "src/api/auth.ts")
    assert "../models/user" in ts_imports
    assert "./config" in ts_imports

    # Go
    go_code = 'import (\n\t"fmt"\n\t"app/models"\n)'
    go_imports = ArchitectureReviewEngine.extract_imports_from_source(go_code, "main.go")
    assert "app/models" in go_imports

    # Java
    java_code = "package com.example;\nimport com.example.models.User;\n"
    java_imports = ArchitectureReviewEngine.extract_imports_from_source(java_code, "Service.java")
    assert "com.example.models.User" in java_imports


def test_tarjan_scc_circular_dependency_detection():
    # Create a 3-node cycle: A -> B -> C -> A
    files = ["src/module_a.py", "src/module_b.py", "src/module_c.py", "src/module_d.py"]
    file_contents = {
        "src/module_a.py": "from module_b import func_b",
        "src/module_b.py": "from module_c import func_c",
        "src/module_c.py": "from module_a import func_a",
        "src/module_d.py": "from module_a import func_a"  # depends on A but not part of cycle
    }

    graph = ArchitectureReviewEngine.build_dependency_graph(files, file_contents)
    cycles = graph["circular_dependencies"]
    assert len(cycles) == 1
    cycle_nodes = cycles[0]["cycle"]
    assert len(cycle_nodes) == 3
    assert set(cycle_nodes) == {"src/module_a.py", "src/module_b.py", "src/module_c.py"}

    # Nodes in cycle should have in_cycle=True
    node_map = {n["id"]: n for n in graph["nodes"]}
    assert node_map["src/module_a.py"]["in_cycle"] is True
    assert node_map["src/module_b.py"]["in_cycle"] is True
    assert node_map["src/module_c.py"]["in_cycle"] is True
    assert node_map["src/module_d.py"]["in_cycle"] is False


def test_coupling_and_instability_metrics():
    # Module Core has high Fan-In (depended on by A, B, C) and zero Fan-Out -> Instability 0.0 (highly stable)
    # Module Client has zero Fan-In and high Fan-Out -> Instability 1.0 (unstable)
    files = ["app/core.py", "app/client.py", "app/service_a.py", "app/service_b.py"]
    file_contents = {
        "app/service_a.py": "import app.core",
        "app/service_b.py": "import app.core",
        "app/client.py": "import app.core\nimport app.service_a"
    }

    graph = ArchitectureReviewEngine.build_dependency_graph(files, file_contents)
    node_map = {n["id"]: n for n in graph["nodes"]}

    assert node_map["app/core.py"]["fan_in"] == 3
    assert node_map["app/core.py"]["fan_out"] == 0
    assert node_map["app/core.py"]["instability"] == 0.0

    assert node_map["app/client.py"]["fan_in"] == 0
    assert node_map["app/client.py"]["fan_out"] == 2
    assert node_map["app/client.py"]["instability"] == 1.0


def test_layer_violation_detection():
    # Domain entity importing from presentation route violates clean architecture
    files = ["src/domain/user_entity.py", "src/api/auth_router.py"]
    file_contents = {
        "src/domain/user_entity.py": "from src.api.auth_router import get_current_user"
    }

    graph = ArchitectureReviewEngine.build_dependency_graph(files, file_contents)
    violations = graph["layer_violations"]
    assert len(violations) == 1
    assert violations[0]["source_layer"] == "domain"
    assert violations[0]["target_layer"] == "presentation"


def test_honest_coverage_notes_on_empty_files():
    res = ArchitectureReviewEngine.analyze_architecture(files=[])
    assert "No source files registered" in res["coverage_notes"]
    assert res["dependency_graph"]["total_modules"] == 0
    assert res["dependency_graph"]["total_dependencies"] == 0
