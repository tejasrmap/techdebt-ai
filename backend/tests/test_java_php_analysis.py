import pytest
from app.services.source_code_analyzer import SourceCodeAnalyzer

def test_java_security_and_reliability_rules():
    analyzer = SourceCodeAnalyzer()
    java_code = """
package com.techdebt.demo;

import java.util.Random;

public class OrderService {
    public void process(String userInput) {
        try {
            Random r = new Random();
            String token = "TOKEN-" + r.nextInt();
            String sql = "SELECT * FROM orders WHERE id = '" + userInput + "'";
            stmt.executeQuery(sql);
        } catch (Exception e) {}

        if (userInput == null) {
            throw new Exception("Invalid order input");
        }
        if (userInput.equals("exit")) {
            System.exit(1);
        }
    }
}
"""
    comp, findings = analyzer._analyze_java("OrderService.java", java_code, java_code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "JAVA_EMPTY_CATCH_BLOCK" in rules
    assert "JAVA_SQL_INJECTION_CONCAT" in rules
    assert "JAVA_GENERIC_EXCEPTION_THROWN" in rules
    assert "JAVA_SYSTEM_EXIT" in rules
    assert "JAVA_INSECURE_RANDOM" in rules

def test_java_deep_nesting():
    analyzer = SourceCodeAnalyzer()
    java_code = """
public class ComplexMatrix {
    public void compute(boolean a, boolean b, boolean c, boolean d, boolean e) {
        if (a) {
            while (b) {
                for (int i = 0; i < 10; i++) {
                    if (c) {
                        if (d) {
                            System.out.println("Deeply nested");
                        }
                    }
                }
            }
        }
    }
}
"""
    comp, findings = analyzer._analyze_java("ComplexMatrix.java", java_code, java_code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "JAVA_DEEP_NESTING" in rules

def test_php_security_and_patterns():
    analyzer = SourceCodeAnalyzer()
    php_code = """<?
$data = $_POST['payload'];
$user = unserialize($data);

if (isset($_GET['cmd'])) {
    eval($_GET['cmd']);
}

try {
    query("SELECT * FROM users WHERE email = '" . $_POST['email'] . "'");
} catch (Exception $e) {}
"""
    comp, findings = analyzer._analyze_php("legacy_endpoint.php", php_code, php_code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "PHP_SHORT_OPEN_TAG" in rules
    assert "PHP_INSECURE_UNSERIALIZE" in rules
    assert "PHP_DANGEROUS_EVAL" in rules
    assert "PHP_RAW_SUPERGLOBAL_USAGE" in rules
    assert "PHP_EMPTY_CATCH_BLOCK" in rules
