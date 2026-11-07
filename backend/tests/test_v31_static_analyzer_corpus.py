"""
TechDebt AI v3.1.0 — Phase 2 static analysis corpus tests.

Covers positive detections, negative (comment/string false-positive immunity),
malformed syntax, excluded paths, real coverage-artifact parsing, documentation
coverage, de-duplication and telemetry across all eight language families.
"""
import json
import os

import pytest

from app.services.source_code_analyzer import SourceCodeAnalyzer
from app.services.static_analysis_rules import mask_source, parse_coverage_artifacts


def _rules(findings):
    return [f["rule_id"] for f in findings]


def _write(root, rel, content):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def _analyze(analyzer, rel, content, lang):
    _, findings, meta = analyzer._analyze_content(rel, content, content.splitlines(), lang)
    return findings, meta


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------

def test_mask_preserves_line_structure_and_blanks_comments_and_strings():
    src = 'let a = "x { y"; // if {\n/* multi\n   line { */\nlet b = `t\n{`;\n'
    code, struct = mask_source(src, "javascript")
    assert len(code) == len(src) and len(struct) == len(src)
    assert code.splitlines().__len__() == src.splitlines().__len__()
    assert "{" not in struct  # all braces were inside strings/comments
    assert '"x { y"' in code  # strings retained in code view
    assert "if" not in code.splitlines()[0]  # comment removed


# ---------------------------------------------------------------------------
# False-positive immunity (negative cases)
# ---------------------------------------------------------------------------

def test_js_comments_and_strings_do_not_trigger_rules():
    analyzer = SourceCodeAnalyzer()
    js = (
        "/*\n"
        "  if (a == b) { { { { { {\n"
        "  eval(x)\n"
        "*/\n"
        "const msg = \"if (a == b) {{{{{{ eval(y) }\";\n"
        "const re = /abc/;\n"
        "function ok(a, b) {\n"
        "  return a === b; // a == b\n"
        "}\n"
        "const m = pattern.exec(input);\n"
    )
    findings, _ = _analyze(analyzer, "clean.js", js, "javascript")
    rules = _rules(findings)
    assert "JS_LOOSE_EQUALITY" not in rules
    assert "JS_DEEP_NESTING" not in rules
    assert "JS_DANGEROUS_EVAL" not in rules
    assert "DANGEROUS_EVAL_USAGE" not in rules  # regex .exec() is not eval


def test_python_safe_loader_variants_are_not_flagged():
    analyzer = SourceCodeAnalyzer()
    code = (
        "import yaml\nfrom yaml import SafeLoader\n"
        "a = yaml.load(data, Loader=SafeLoader)\n"
        "b = yaml.load(data, Loader=yaml.SafeLoader)\n"
        "c = yaml.load(data, yaml.CSafeLoader)\n"
    )
    findings, _ = _analyze(analyzer, "cfg.py", code, "python")
    assert "PY_UNSAFE_YAML_LOAD" not in _rules(findings)


def test_java_strings_do_not_inflate_nesting():
    analyzer = SourceCodeAnalyzer()
    java = 'public class A {\n  public String s() {\n    return "{{{{{{{{";\n  }\n}\n'
    findings, _ = _analyze(analyzer, "A.java", java, "java")
    assert "JAVA_DEEP_NESTING" not in _rules(findings)


# ---------------------------------------------------------------------------
# De-duplication & normalization
# ---------------------------------------------------------------------------

def test_eval_is_reported_once_per_line_with_provenance():
    analyzer = SourceCodeAnalyzer()
    findings, meta = _analyze(analyzer, "x.py", "def f(c):\n    return eval(c)\n", "python")
    evals = [f for f in findings if "EVAL" in f["rule_id"]]
    assert len(evals) == 1 and evals[0]["rule_id"] == "PY_DANGEROUS_EVAL"
    f = evals[0]
    assert f["analyzer_name"] == "SourceCodeAnalyzer"
    assert f["analyzer_version"] == "3.1.0"
    assert f["analysis_mode"] == "ast" and meta["mode"] == "ast"
    assert f["finding_id"] and f["description"]


def test_aws_key_detected_and_masked():
    analyzer = SourceCodeAnalyzer()
    findings, _ = _analyze(analyzer, "k.js", 'const k = "AKIAIOSFODNN7EXAMPLE";\n', "javascript")
    aws = [f for f in findings if f["rule_id"] == "AWS_ACCESS_KEY_EXPOSED"]
    assert aws
    assert "AKIAIOSFODNN7EXAMPLE" not in aws[0]["technical_evidence"]


# ---------------------------------------------------------------------------
# Python dimensions
# ---------------------------------------------------------------------------

def test_python_performance_reliability_and_security_rules():
    analyzer = SourceCodeAnalyzer()
    code = '''
import time, requests, hashlib, re, tempfile

async def handler():
    time.sleep(1)
    return 1

def n_plus_one(ids, cursor):
    for i in ids:
        cursor.execute("SELECT 1")
        pat = re.compile("a+")
    r = requests.get("https://x", verify=False)
    h = hashlib.md5(b"x")
    ok = hashlib.md5(b"x", usedforsecurity=False)
    t = tempfile.mktemp()
    f = open("a.txt")
    with open("b.txt") as g:
        pass
    return r

def dead():
    return 1
    print("never")
'''
    findings, _ = _analyze(analyzer, "svc.py", code, "python")
    rules = _rules(findings)
    for expected in (
        "PY_BLOCKING_IO_IN_ASYNC", "DB_OR_HTTP_CALL_IN_LOOP", "REGEX_COMPILE_IN_LOOP",
        "HTTP_REQUEST_MISSING_TIMEOUT", "INSECURE_TLS_VERIFICATION", "WEAK_CRYPTO_HASH",
        "INSECURE_TEMP_FILE", "PY_UNCLOSED_FILE_HANDLE", "PY_UNREACHABLE_CODE",
    ):
        assert expected in rules, expected
    assert rules.count("WEAK_CRYPTO_HASH") == 1  # usedforsecurity=False is honoured
    assert rules.count("PY_UNCLOSED_FILE_HANDLE") == 1  # `with open` is fine
    perf = [f for f in findings if f["category"] == "performance"]
    assert perf, "performance category must be populated"


def test_python_large_class_detection():
    analyzer = SourceCodeAnalyzer()
    methods = "".join(f"    def m{i}(self):\n        return {i}\n" for i in range(30))
    findings, _ = _analyze(analyzer, "big.py", f"class Big:\n{methods}", "python")
    assert "PY_LARGE_CLASS" in _rules(findings)


def test_python_malformed_syntax_is_reported_not_raised():
    analyzer = SourceCodeAnalyzer()
    findings, meta = _analyze(analyzer, "bad.py", "def x(:\n  pass\n", "python")
    assert "SYNTAX_PARSE_ERROR" in _rules(findings)
    assert meta["parse_failed"] is True and meta["mode"] == "heuristic"


# ---------------------------------------------------------------------------
# C-family dimensions
# ---------------------------------------------------------------------------

def test_c_family_long_method_and_parameter_rules():
    analyzer = SourceCodeAnalyzer()
    body = "".join(f"  let v{i} = {i};\n" for i in range(90))
    js = f"function huge(a, b, c, d, e, f, g) {{\n{body}}}\n"
    findings, _ = _analyze(analyzer, "huge.js", js, "javascript")
    rules = _rules(findings)
    assert "EXCESSIVE_METHOD_LENGTH" in rules
    assert "TOO_MANY_PARAMETERS" in rules


@pytest.mark.parametrize("lang,rel,code,expected", [
    ("javascript", "a.js", "const h = crypto.createHash('md5');\n", "WEAK_CRYPTO_HASH"),
    ("javascript", "b.js", "https.request({ rejectUnauthorized: false });\n", "INSECURE_TLS_VERIFICATION"),
    ("javascript", "c.js", "child_process.exec(`ls ${dir}`);\n", "UNSAFE_COMMAND_EXEC"),
    ("go", "d.go", "package m\nvar c = &tls.Config{InsecureSkipVerify: true}\n", "INSECURE_TLS_VERIFICATION"),
    ("go", "e.go", "package m\nfunc f() {\n  resp, err := http.Get(u)\n  _ = resp\n  _ = err\n}\n", "HTTP_REQUEST_MISSING_TIMEOUT"),
    ("java", "F.java", 'class F { void f() { MessageDigest.getInstance("MD5"); } }\n', "WEAK_CRYPTO_HASH"),
    ("php", "g.php", "<?php\nshell_exec('ls ' . $dir);\n", "UNSAFE_COMMAND_EXEC"),
    ("csharp", "H.cs", "class H { void F() { var m = MD5.Create(); } }\n", "WEAK_CRYPTO_HASH"),
    ("c", "i.c", "void f(void) { char *p = tmpnam(NULL); }\n", "INSECURE_TEMP_FILE"),
    ("cpp", "j.cpp", "void f(char* c) { system(c); }\n", "UNSAFE_COMMAND_EXEC"),
])
def test_cross_language_security_and_reliability(lang, rel, code, expected):
    findings, _ = _analyze(SourceCodeAnalyzer(), rel, code, lang)
    assert expected in _rules(findings)


@pytest.mark.parametrize("lang,rel,code", [
    ("javascript", "loop.js", "async function f(ids) {\n  for (const id of ids) {\n    await db.query('x', [id]);\n  }\n}\n"),
    ("java", "Loop.java", "class L {\n  void f(List<Integer> ids) {\n    for (int id : ids) {\n      stmt.executeQuery(q);\n    }\n  }\n}\n"),
    ("go", "loop.go", "package m\nfunc f(ids []int) {\n  for _, id := range ids {\n    db.QueryRow(q, id)\n  }\n}\n"),
    ("php", "loop.php", "<?php\nforeach ($ids as $id) {\n  $pdo->query('x');\n}\n"),
    ("csharp", "Loop.cs", "class L {\n  void F(int[] ids) {\n    foreach (var id in ids)\n    {\n      cmd.ExecuteReader();\n    }\n  }\n}\n"),
])
def test_n_plus_one_detection_across_languages(lang, rel, code):
    findings, _ = _analyze(SourceCodeAnalyzer(), rel, code, lang)
    hits = [f for f in findings if f["rule_id"] == "DB_OR_HTTP_CALL_IN_LOOP"]
    assert len(hits) == 1 and hits[0]["category"] == "performance"


def test_regex_compile_in_loop_c_family():
    code = "function f(xs) {\n  for (const x of xs) {\n    const r = new RegExp(x);\n  }\n}\n"
    findings, _ = _analyze(SourceCodeAnalyzer(), "r.js", code, "javascript")
    assert "REGEX_COMPILE_IN_LOOP" in _rules(findings)


def test_excessive_imports():
    code = "".join(f"import m{i} from 'm{i}';\n" for i in range(35))
    findings, _ = _analyze(SourceCodeAnalyzer(), "imp.ts", code, "typescript")
    assert "EXCESSIVE_MODULE_IMPORTS" in _rules(findings)


# ---------------------------------------------------------------------------
# Repository-level telemetry, exclusions, coverage & documentation
# ---------------------------------------------------------------------------

def test_repository_telemetry_exclusions_and_documentation(tmp_path):
    root = str(tmp_path)
    _write(root, "src/app.py", '"""Module doc."""\n\ndef run():\n    """Run."""\n    return 1\n\ndef other():\n    return 2\n')
    _write(root, "src/util.js", "/** Adds. */\nfunction add(a, b) {\n  return a + b;\n}\n")
    _write(root, "src/broken.py", "def x(:\n")
    _write(root, "generated/huge.py", "eval('1')\n")
    _write(root, "src/legacy_skip.js", "eval(x)\n")
    _write(root, "README.md", "# readme\n")

    analyzer = SourceCodeAnalyzer(root, excluded_paths=["generated", "*_skip.js"])
    res = analyzer.analyze_repository()

    analyzed_paths = set(res["file_metrics"].keys())
    assert "generated/huge.py" not in analyzed_paths
    assert "src/legacy_skip.js" not in analyzed_paths
    assert res["files_excluded_by_pattern"] == 2
    assert res["files_analyzed"] == 3
    assert res["unsupported_files_count"] >= 1
    assert res["parser_failures_count"] == 1
    assert res["ast_analyzed_count"] == 1  # app.py parsed; broken.py failed
    assert res["heuristic_analyzed_count"] == 2
    assert res["syntax_tree_analyzed_count"] == 0
    assert set(res["language_coverage"]) == {"python", "javascript"}
    assert res["analyzer_version"] == "3.1.0"
    # app.py: module + run documented, other undocumented; util.js: add documented -> 3/4
    assert res["documentation_coverage_pct"] == 75.0
    # No coverage artifacts -> never fabricated
    assert res["measured_test_coverage_pct"] is None
    assert res["coverage_percentage"] is None


def test_coverage_artifacts_are_parsed_and_aggregated(tmp_path):
    root = str(tmp_path)
    _write(root, "coverage/lcov.info", "SF:a.js\nLF:100\nLH:80\nend_of_record\n")
    _write(root, "coverage/coverage-summary.json", json.dumps({"total": {"lines": {"total": 50, "covered": 25}}}))
    _write(root, "coverage.xml", '<?xml version="1.0"?><coverage line-rate="0.5" lines-valid="50" lines-covered="45"></coverage>')
    _write(root, "target/site/jacoco/jacoco.xml",
           '<?xml version="1.0"?><report name="x"><counter type="LINE" missed="10" covered="40"/></report>')
    res = parse_coverage_artifacts(root)
    formats = sorted(a["format"] for a in res["coverage_artifacts"])
    assert formats == ["cobertura", "istanbul-summary", "jacoco", "lcov"]
    # (80 + 25 + 45 + 40) / (100 + 50 + 50 + 50) = 190 / 250 = 76.0
    assert res["measured_test_coverage_pct"] == 76.0


def test_coverage_rejects_entity_expansion_and_malformed(tmp_path):
    root = str(tmp_path)
    _write(root, "coverage.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><coverage line-rate="1.0"/>')
    _write(root, "coverage/lcov.info", "garbage\n")
    res = parse_coverage_artifacts(root)
    assert res["measured_test_coverage_pct"] is None
    assert len(res["coverage_errors"]) == 2


def test_repository_analysis_includes_measured_coverage(tmp_path):
    root = str(tmp_path)
    _write(root, "main.py", "def f():\n    return 1\n")
    _write(root, "coverage/lcov.info", "LF:10\nLH:9\n")
    res = SourceCodeAnalyzer(root).analyze_repository()
    assert res["measured_test_coverage_pct"] == 90.0
    assert res["coverage_artifacts"][0]["path"] == "coverage/lcov.info"

