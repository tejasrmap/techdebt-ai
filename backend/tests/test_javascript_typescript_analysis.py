import pytest
from app.services.source_code_analyzer import SourceCodeAnalyzer

def test_javascript_equality_and_dom_security():
    analyzer = SourceCodeAnalyzer()
    js_code = """
function renderUser(user) {
    if (user.id == 123) {
        document.getElementById('profile').innerHTML = user.bio;
    }
}
"""
    comp, findings = analyzer._analyze_javascript_typescript("user.js", js_code, js_code.splitlines(), "javascript")
    rules = [f["rule_id"] for f in findings]
    assert "JS_LOOSE_EQUALITY" in rules
    assert "JS_DANGEROUS_DOM_XSS" in rules

def test_javascript_eval_and_prototype_pollution():
    analyzer = SourceCodeAnalyzer()
    js_code = """
function unsafeProcessor(input, obj) {
    obj.__proto__.isAdmin = true;
    eval("console.log(" + input + ")");
}
"""
    comp, findings = analyzer._analyze_javascript_typescript("bad.js", js_code, js_code.splitlines(), "javascript")
    rules = [f["rule_id"] for f in findings]
    assert "JS_PROTOTYPE_POLLUTION" in rules
    assert "JS_DANGEROUS_EVAL" in rules

def test_javascript_empty_catch_and_nesting():
    analyzer = SourceCodeAnalyzer()
    js_code = """
function nestedHell(a, b, c, d, e) {
    if (a) {
        for (let i = 0; i < 10; i++) {
            while (b) {
                if (c) {
                    try {
                        doSomething();
                    } catch (err) {}
                }
            }
        }
    }
}
"""
    comp, findings = analyzer._analyze_javascript_typescript("nested.js", js_code, js_code.splitlines(), "javascript")
    rules = [f["rule_id"] for f in findings]
    assert "JS_EMPTY_CATCH_BLOCK" in rules
    assert "JS_DEEP_NESTING" in rules

def test_typescript_specific_rules():
    analyzer = SourceCodeAnalyzer()
    ts_code = """
// @ts-ignore
const payload: any = fetchPayload();

function processUser(u: any) {
    const email = u!.email;
    return email;
}
"""
    comp, findings = analyzer._analyze_javascript_typescript("service.ts", ts_code, ts_code.splitlines(), "typescript")
    rules = [f["rule_id"] for f in findings]
    assert "TS_EXPLICIT_ANY" in rules
    assert "TS_IGNORE_DIRECTIVE" in rules
    assert "TS_NON_NULL_ASSERTION" in rules
