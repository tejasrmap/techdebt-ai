import pytest
from app.services.source_code_analyzer import SourceCodeAnalyzer

def test_python_syntax_error():
    analyzer = SourceCodeAnalyzer()
    bad_code = "def broken_code(: print('syntax error')"
    comp, findings = analyzer._analyze_python("bad.py", bad_code, bad_code.splitlines())
    assert any(f["rule_id"] == "SYNTAX_PARSE_ERROR" for f in findings)

def test_python_high_complexity_and_deep_nesting():
    analyzer = SourceCodeAnalyzer()
    complex_code = """
def deeply_nested_and_complex(a, b, c, d):
    if a:
        if b:
            while c:
                for x in range(10):
                    if d:
                        try:
                            print(x)
                        except ValueError:
                            pass
    return True
"""
    comp, findings = analyzer._analyze_python("complex.py", complex_code, complex_code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "PY_DEEP_NESTING" in rules
    assert any("depth" in f["title"] for f in findings if f["rule_id"] == "PY_DEEP_NESTING")

def test_python_mutable_defaults_and_too_many_args():
    analyzer = SourceCodeAnalyzer()
    code = """
def problematic_func(p1, p2, p3, p4, p5, p6, p7, cache={}):
    cache[p1] = p2
    return cache
"""
    comp, findings = analyzer._analyze_python("params.py", code, code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "PY_TOO_MANY_ARGUMENTS" in rules
    assert "PY_MUTABLE_DEFAULT_ARG" in rules

def test_python_security_and_deserialization():
    analyzer = SourceCodeAnalyzer()
    code = """
import pickle
import yaml

def unsafe_worker(data):
    obj = pickle.loads(data)
    cfg = yaml.load(data)
    result = eval("2 + 2")
    return obj, cfg, result
"""
    comp, findings = analyzer._analyze_python("sec.py", code, code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "PY_INSECURE_DESERIALIZATION_PICKLE" in rules
    assert "PY_UNSAFE_YAML_LOAD" in rules
    assert "PY_DANGEROUS_EVAL" in rules

def test_python_wildcard_and_globals():
    analyzer = SourceCodeAnalyzer()
    code = """
from math import *

total = 0

def add_to_total(x):
    global total
    total += x
"""
    comp, findings = analyzer._analyze_python("imports.py", code, code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "PY_WILDCARD_IMPORT" in rules
    assert "PY_GLOBAL_STATEMENT" in rules
