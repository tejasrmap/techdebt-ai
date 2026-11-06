import pytest
from app.services.source_code_analyzer import SourceCodeAnalyzer

def test_go_code_analysis():
    analyzer = SourceCodeAnalyzer()
    go_code = """
package main

import (
    "database/sql"
    "fmt"
)

func QueryUser(db *sql.DB, id string) {
    query := fmt.Sprintf("SELECT * FROM users WHERE id = '%s'", id)
    _, _ := db.Query(query)

    go func() {
        fmt.Println("background work")
    }()

    if id == "fatal" {
        panic("unrecoverable state")
    }
}
"""
    comp, findings = analyzer._analyze_go("service.go", go_code, go_code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "GO_SQL_INJECTION_CONCAT" in rules
    assert "GO_UNHANDLED_ERROR" in rules
    assert "GO_UNBOUNDED_GOROUTINE" in rules
    assert "GO_UNCONTROLLED_PANIC" in rules

def test_csharp_code_analysis():
    analyzer = SourceCodeAnalyzer()
    cs_code = """
using System;
using System.Data.SqlClient;
using System.Runtime.Serialization.Formatters.Binary;
using System.Threading;

public class LegacyWorker {
    public void Execute(string userId, byte[] rawBytes) {
        try {
            var formatter = new BinaryFormatter();
            var obj = formatter.Deserialize(rawStream);
            var cmd = new SqlCommand($"SELECT * FROM Accounts WHERE Id = '{userId}'");
        } catch {}

        var thread = new Thread(() => {});
        thread.Abort();
    }
}
"""
    comp, findings = analyzer._analyze_csharp("LegacyWorker.cs", cs_code, cs_code.splitlines())
    rules = [f["rule_id"] for f in findings]
    assert "CSHARP_EMPTY_CATCH_BLOCK" in rules
    assert "CSHARP_INSECURE_BINARY_FORMATTER" in rules
    assert "CSHARP_SQL_INJECTION" in rules
    assert "CSHARP_DANGEROUS_THREAD_ABORT" in rules

def test_cpp_code_analysis():
    analyzer = SourceCodeAnalyzer()
    cpp_code = """
#include <cstdio>
#include <cstring>

void processBuffer(const char* input) {
    char dest[64];
    strcpy(dest, input);
    printf(dest);
}
"""
    comp, findings = analyzer._analyze_c_cpp("buffer.cpp", cpp_code, cpp_code.splitlines(), "cpp")
    rules = [f["rule_id"] for f in findings]
    assert "CPP_UNSAFE_BUFFER_FUNCTION" in rules
    assert "CPP_FORMAT_STRING_VULN" in rules
