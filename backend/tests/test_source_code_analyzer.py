import os
import tempfile
import pytest
from app.services.source_code_analyzer import SourceCodeAnalyzer

def test_python_ast_cyclomatic_complexity_and_findings():
    """Verify cyclomatic complexity calculation and rule violations on Python code."""
    analyzer = SourceCodeAnalyzer()
    
    code = """
import os

def complex_function(x, y, z):
    # High branching complexity
    result = 0
    if x > 0:
        if y > 0:
            result = 1
        elif y < -5:
            result = 2
        else:
            result = 3
    else:
        for i in range(10):
            while z > 0:
                z -= 1
                if z % 2 == 0:
                    result += z
    return result

def dangerous_function(cmd):
    # Dangerous API usage
    eval(cmd)
    exec("print('executed')")
    import subprocess
    subprocess.call("ls -la", shell=True)
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        f_path = f.name

    try:
        res = analyzer.analyze_file(f_path)
        assert res["lines_of_code"] > 20
        assert res["cyclomatic_complexity"] >= 6

        # Check findings
        rule_ids = [f.rule_id for f in res["findings"]]
        assert any("EVAL" in r for r in rule_ids)
        assert any("SHELL" in r for r in rule_ids)
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)

def test_hardcoded_secrets_detection():
    """Verify regex secret scanner identifies API keys and credentials."""
    analyzer = SourceCodeAnalyzer()

    code = """
# Config with exposed secret
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
GITHUB_TOKEN = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        f_path = f.name

    try:
        res = analyzer.analyze_file(f_path)
        severities = [f.severity for f in res["findings"]]
        assert "Critical" in severities
        # Ensure raw secret is masked in evidence
        for f in res["findings"]:
            if "SECRET" in f.rule_id:
                assert "AKIAIOSFODNN7EXAMPLE" not in f.technical_evidence
                assert "ghp_1234567890" not in f.technical_evidence
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)

def test_directory_analysis_and_maintainability_index():
    """Verify aggregate directory analysis and maintainability calculations."""
    analyzer = SourceCodeAnalyzer()

    with tempfile.TemporaryDirectory() as temp_dir:
        f1 = os.path.join(temp_dir, "clean.py")
        with open(f1, "w") as f:
            f.write("def simple_add(a, b):\n    return a + b\n")

        f2 = os.path.join(temp_dir, "test_clean.py")
        with open(f2, "w") as f:
            f.write("def test_simple_add():\n    assert simple_add(1, 2) == 3\n")

        summary = analyzer.analyze_directory(temp_dir)
        assert summary.total_files == 2
        assert summary.test_files_count == 1
        assert summary.maintainability_index > 80.0
