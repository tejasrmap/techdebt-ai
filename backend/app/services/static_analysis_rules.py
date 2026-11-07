"""
TechDebt AI v3.1.0 — supplementary static-analysis rules and telemetry helpers.

This module complements ``SourceCodeAnalyzer`` with:

* A lexical masker that blanks comments and string-literal contents while
  preserving exact line numbers (so brace counting, branch keywords and
  operator checks are not skewed by comments or strings).
* Cross-language (C-family) rules: long methods, long parameter lists, large
  classes, weak cryptography, disabled TLS verification, unsafe command
  execution, database/HTTP calls inside loops, regex compilation inside loops,
  missing HTTP timeouts and excessive module imports.
* Python AST rules: large classes, unreachable code, blocking I/O inside async
  functions, N+1 style calls inside loops, regex compilation inside loops,
  missing ``requests`` timeouts, unclosed file handles, weak hashes, disabled
  TLS verification and insecure temporary files.
* Documentation coverage statistics (Python AST docstrings / C-family doc
  comments).
* Parsing of *real* test-coverage artifacts (Cobertura ``coverage.xml``,
  JaCoCo ``jacoco.xml``, ``lcov.info`` and Istanbul ``coverage-summary.json``).
  Coverage is never fabricated: when no artifact exists the result is ``None``.

All analysis is static. Repository code is never imported or executed.
"""

from __future__ import annotations

import ast
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence, Tuple

ANALYZER_NAME = "SourceCodeAnalyzer"
ANALYZER_VERSION = "3.1.0"

# Characters that str.splitlines() treats as line boundaries. They must be preserved
# by the masker so masked output always splits into the same number of lines.
_LINE_BREAK_CHARS = frozenset("\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")

C_FAMILY_LANGS = frozenset({"javascript", "typescript", "java", "go", "php", "csharp", "c", "cpp"})


# =============================================================================
# Lexical masking
# =============================================================================

def mask_source(content: str, lang: str) -> Tuple[str, str]:
    """
    Returns ``(code_text, struct_text)`` for a C-family source file.

    * ``code_text``   – comments replaced by spaces, string literals retained.
    * ``struct_text`` – comments AND string-literal contents replaced by spaces
      (the delimiting quotes are retained).

    Both outputs have exactly the same length and line structure as ``content``.
    """
    hash_comments = lang == "php"
    backtick_strings = lang in ("javascript", "typescript", "go")
    multiline_backtick = backtick_strings

    code = list(content)
    struct = list(content)
    n = len(content)
    i = 0

    def blank(buf: List[str], start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if content[k] not in _LINE_BREAK_CHARS:
                buf[k] = " "

    while i < n:
        ch = content[i]
        nxt = content[i + 1] if i + 1 < n else ""

        # Line comment
        if (ch == "/" and nxt == "/") or (hash_comments and ch == "#" and nxt != "["):
            j = i
            while j < n and content[j] not in "\r\n":
                j += 1
            blank(code, i, j)
            blank(struct, i, j)
            i = j
            continue

        # Block comment
        if ch == "/" and nxt == "*":
            end = content.find("*/", i + 2)
            j = n if end == -1 else end + 2
            blank(code, i, j)
            blank(struct, i, j)
            i = j
            continue

        # String literals
        if ch in ("'", '"') or (backtick_strings and ch == "`"):
            quote = ch
            j = i + 1
            verbatim = lang == "csharp" and i > 0 and content[i - 1] == "@" and quote == '"'
            while j < n:
                c = content[j]
                if verbatim:
                    if c == '"' and j + 1 < n and content[j + 1] == '"':
                        j += 2
                        continue
                    if c == '"':
                        break
                elif c == "\\" and quote != "`":
                    j += 2
                    continue
                elif c == quote:
                    break
                elif c in "\r\n" and not (quote == "`" and multiline_backtick):
                    # Unterminated single-line string: stop masking at end of line.
                    break
                j += 1
            closing = j if j < n and content[j] == quote else j
            blank(struct, i + 1, closing)
            i = closing + 1 if closing < n and content[closing] == quote else closing
            continue

        i += 1

    return "".join(code), "".join(struct)


def prepare_lines(content: str, lines: Sequence[str], lang: str) -> Tuple[List[str], List[str]]:
    """Masks content and returns per-line lists aligned 1:1 with ``lines``."""
    code_text, struct_text = mask_source(content, lang)
    code_lines = code_text.splitlines()
    struct_lines = struct_text.splitlines()
    target = len(lines)
    if len(code_lines) < target:
        code_lines.extend([""] * (target - len(code_lines)))
    if len(struct_lines) < target:
        struct_lines.extend([""] * (target - len(struct_lines)))
    return code_lines[:target], struct_lines[:target]


# =============================================================================
# Finding factory
# =============================================================================

def make_finding(
    rel_path: str,
    line_start: int,
    rule_id: str,
    category: str,
    severity: str,
    title: str,
    explanation: str,
    evidence: str,
    why: str,
    remediation: str,
    hours: float,
    line_end: Optional[int] = None,
    confidence: str = "Medium",
) -> Dict[str, Any]:
    return {
        "file_path": rel_path,
        "line_start": int(line_start),
        "line_end": int(line_end if line_end is not None else line_start),
        "rule_id": rule_id,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "title": title,
        "explanation": explanation,
        "technical_evidence": evidence,
        "why_it_matters": why,
        "recommended_remediation": remediation,
        "estimated_remediation_hours": round(float(hours), 2),
        "is_auto_verifiable": True,
    }


# =============================================================================
# C-family structural helpers
# =============================================================================

_CONTROL_WORDS = frozenset({
    "if", "for", "foreach", "while", "switch", "catch", "with", "return", "elseif",
    "sizeof", "using", "lock", "fixed", "synchronized", "typeof", "new", "throw",
    "await", "yield", "delete", "case", "do", "else", "select", "defer", "go",
    "nameof", "when", "match", "unless", "until", "assert", "print", "echo",
    "require", "include", "isset", "empty", "list", "array", "super", "this", "func",
})

_SIGNATURE_RE = re.compile(
    r"(?<![\w$.])(?P<name>[A-Za-z_$][\w$]*)\s*\((?P<params>[^()]*)\)\s*(?P<tail>(?:[^{};=()]|\([^()]*\))*?)\s*(?P<brace>\{)?\s*$"
)
_ARROW_RE = re.compile(
    r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?\((?P<params>[^()]*)\)\s*(?::[^=]*)?=>\s*\{\s*$"
)
_CLASS_RE = re.compile(r"\b(?:class|struct|interface|trait)\s+(?P<name>[A-Za-z_$][\w$]*)")
_LOOP_RE = re.compile(r"(?:^|[\s};])(?:for|foreach|while)\b")


def _depth_at_line_start(struct_lines: Sequence[str]) -> List[int]:
    depths = [0] * (len(struct_lines) + 1)
    depth = 0
    for idx, line in enumerate(struct_lines):
        depths[idx] = depth
        depth = max(0, depth + line.count("{") - line.count("}"))
    depths[len(struct_lines)] = depth
    return depths


def _block_end(struct_lines: Sequence[str], depths: Sequence[int], open_idx: int) -> int:
    """Given the 0-based index of the line containing an opening brace, returns the
    0-based index of the line where that block closes (best effort)."""
    base = depths[open_idx]
    if depths[open_idx + 1] <= base:
        return open_idx
    for j in range(open_idx + 1, len(struct_lines)):
        if depths[j + 1] <= base:
            return j
    return len(struct_lines) - 1


def _next_nonblank(lines: Sequence[str], idx: int) -> Optional[int]:
    for j in range(idx + 1, min(len(lines), idx + 3)):
        if lines[j].strip():
            return j
    return None


def _count_params(params: str) -> int:
    cleaned = params
    for _ in range(3):
        cleaned = re.sub(r"<[^<>]*>", "", cleaned)
    cleaned = re.sub(r"\[[^\[\]]*\]", "", cleaned)
    parts = [p.strip() for p in cleaned.split(",")]
    parts = [p for p in parts if p and p not in ("void", "...")]
    return len(parts)


def extract_c_family_units(struct_lines: Sequence[str], lang: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extracts function-like and class-like units with their line spans (1-based)."""
    depths = _depth_at_line_start(struct_lines)
    functions: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []

    for idx, line in enumerate(struct_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        cls_match = _CLASS_RE.search(stripped)
        if cls_match and not stripped.endswith(";"):
            open_idx = idx if "{" in line else _next_nonblank(struct_lines, idx)
            if open_idx is not None and "{" in struct_lines[open_idx]:
                end_idx = _block_end(struct_lines, depths, open_idx)
                classes.append({"name": cls_match.group("name"), "start": idx + 1, "end": end_idx + 1})
            continue

        match = _ARROW_RE.search(stripped)
        is_arrow = match is not None
        if not match:
            match = next(
                (m for m in _SIGNATURE_RE.finditer(stripped) if m.group("name") not in _CONTROL_WORDS),
                None,
            )
        if not match:
            continue

        name = match.group("name")
        if name in _CONTROL_WORDS:
            continue
        if not is_arrow:
            prefix = stripped[: match.start()].rstrip()
            # Assignments / calls followed by blocks are not declarations.
            if prefix.endswith(("=", "return", ".", "(", ",", "&&", "||", "?", ":")) and not prefix.endswith("::"):
                continue
            has_brace = bool(match.group("brace"))
            if has_brace:
                open_idx = idx
            else:
                nb = _next_nonblank(struct_lines, idx)
                if nb is None or not struct_lines[nb].strip().startswith("{"):
                    continue
                open_idx = nb
            # Java / C# methods always carry a return type or modifier before the name.
            if lang in ("java", "csharp") and not prefix:
                continue
        else:
            open_idx = idx

        end_idx = _block_end(struct_lines, depths, open_idx)
        functions.append({
            "name": name if name != "function" else "<anonymous>",
            "start": idx + 1,
            "end": end_idx + 1,
            "param_count": _count_params(match.group("params")),
        })

    return functions, classes


def _loop_ranges(struct_lines: Sequence[str]) -> List[Tuple[int, int]]:
    """Returns (header_idx, end_idx) 0-based ranges for loop bodies."""
    depths = _depth_at_line_start(struct_lines)
    ranges: List[Tuple[int, int]] = []
    for idx, line in enumerate(struct_lines):
        if not _LOOP_RE.search(line):
            continue
        stripped = line.rstrip()
        # do { ... } while (x);  -> trailing while closes a do-block, not a new loop
        if re.match(r"^\s*\}\s*while\b", line) and stripped.endswith(";"):
            continue
        if "{" in line:
            ranges.append((idx, _block_end(struct_lines, depths, idx)))
        else:
            nb = _next_nonblank(struct_lines, idx)
            if nb is not None and struct_lines[nb].strip().startswith("{"):
                ranges.append((idx, _block_end(struct_lines, depths, nb)))
            else:
                ranges.append((idx, min(len(struct_lines) - 1, idx + 1)))
    return ranges


# =============================================================================
# C-family pattern catalogues
# =============================================================================

_WEAK_HASH = {
    "javascript": re.compile(r"createHash\(\s*['\"](?:md5|sha1)['\"]", re.I),
    "typescript": re.compile(r"createHash\(\s*['\"](?:md5|sha1)['\"]", re.I),
    "java": re.compile(r"MessageDigest\.getInstance\(\s*\"(?:MD5|SHA-?1|MD2)\"", re.I),
    "go": re.compile(r"\b(?:md5|sha1)\.(?:New|Sum)\s*\("),
    "php": re.compile(r"(?<![\w>$:])(?:md5|sha1)\s*\("),
    "csharp": re.compile(r"\b(?:MD5|SHA1)\.Create\s*\(|new\s+(?:MD5|SHA1)CryptoServiceProvider"),
    "c": re.compile(r"\b(?:MD5_Init|SHA1_Init|MD5\s*\(|SHA1\s*\()"),
    "cpp": re.compile(r"\b(?:MD5_Init|SHA1_Init|MD5\s*\(|SHA1\s*\()"),
}

_INSECURE_TLS = {
    "javascript": re.compile(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED[^\n]*['\"]?0"),
    "typescript": re.compile(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED[^\n]*['\"]?0"),
    "go": re.compile(r"InsecureSkipVerify\s*:\s*true"),
    "php": re.compile(r"CURLOPT_SSL_VERIFY(?:PEER|HOST)\s*,\s*(?:false|0)\b", re.I),
    "csharp": re.compile(r"(?:ServerCertificate(?:Custom)?ValidationCallback)\s*\+?=\s*[^;]*=>\s*true"),
    "java": re.compile(r"NoopHostnameVerifier|ALLOW_ALL_HOSTNAME_VERIFIER|TrustAllStrategy"),
}

_UNSAFE_EXEC = {
    "javascript": re.compile(r"(?:(?<![\w.$])|child_process\.)exec(?:Sync)?\s*\(\s*(?:`[^`]*\$\{|[^)]*\+)"),
    "typescript": re.compile(r"(?:(?<![\w.$])|child_process\.)exec(?:Sync)?\s*\(\s*(?:`[^`]*\$\{|[^)]*\+)"),
    "php": re.compile(r"(?<![\w>$:])(?:shell_exec|system|passthru|exec|popen|proc_open)\s*\([^)]*\$"),
    "go": re.compile(r"exec\.Command(?:Context)?\([^)]*\"(?:sh|bash|cmd(?:\.exe)?)\"\s*,\s*\"(?:-c|/c|/C)\""),
    "java": re.compile(r"Runtime\.getRuntime\(\)\.exec\([^)]*\+"),
    "csharp": re.compile(r"Process\.Start\([^)]*\+"),
    "c": re.compile(r"(?<![\w.])(?:system|popen)\s*\(\s*[A-Za-z_]"),
    "cpp": re.compile(r"(?<![\w.:])(?:system|popen)\s*\(\s*[A-Za-z_]"),
}

_IO_IN_LOOP = {
    "javascript": re.compile(r"\bawait\s+fetch\(|\baxios\.(?:get|post|put|delete|patch|request)\(|\.(?:query|execute|findOne|findById|findMany|findUnique|findFirst)\("),
    "typescript": re.compile(r"\bawait\s+fetch\(|\baxios\.(?:get|post|put|delete|patch|request)\(|\.(?:query|execute|findOne|findById|findMany|findUnique|findFirst)\("),
    "java": re.compile(r"\.(?:executeQuery|executeUpdate|prepareStatement|findById|findOne|getForObject|exchange)\("),
    "go": re.compile(r"\.(?:Query|QueryRow|QueryContext|Exec|ExecContext)\(|\bhttp\.(?:Get|Post|Head)\("),
    "php": re.compile(r"->(?:query|execute|prepare)\(|\bmysqli_query\(|\bcurl_exec\(|file_get_contents\(\s*['\"]https?:"),
    "csharp": re.compile(r"\.(?:ExecuteReader|ExecuteNonQuery|ExecuteScalar|GetAsync|PostAsync|SendAsync|FirstOrDefault|SingleOrDefault|Find)\("),
}

_REGEX_IN_LOOP = {
    "javascript": re.compile(r"\bnew\s+RegExp\("),
    "typescript": re.compile(r"\bnew\s+RegExp\("),
    "java": re.compile(r"\bPattern\.compile\("),
    "go": re.compile(r"\bregexp\.(?:Must)?Compile\("),
    "csharp": re.compile(r"\bnew\s+Regex\("),
    "php": re.compile(r"$^"),
}

_IMPORT_LINE = {
    "javascript": re.compile(r"^\s*import\b|\brequire\(\s*['\"]"),
    "typescript": re.compile(r"^\s*import\b|\brequire\(\s*['\"]"),
    "java": re.compile(r"^\s*import\s+[\w.*]+\s*;"),
    "csharp": re.compile(r"^\s*using\s+[\w.]+\s*;"),
    "php": re.compile(r"^\s*use\s+[\w\\]+"),
    "c": re.compile(r"^\s*#\s*include\b"),
    "cpp": re.compile(r"^\s*#\s*include\b"),
}

MAX_METHOD_LINES = 80
MAX_PARAMS = 6
MAX_CLASS_LINES = 500
MAX_IMPORTS = 30


def _count_go_imports(code_lines: Sequence[str]) -> int:
    count = 0
    in_block = False
    for line in code_lines:
        s = line.strip()
        if in_block:
            if s.startswith(")"):
                in_block = False
            elif s:
                count += 1
        elif re.match(r"^import\s*\($", s):
            in_block = True
        elif re.match(r"^import\s+", s):
            count += 1
    return count


def analyze_c_family_common(
    rel_path: str,
    lang: str,
    lines: Sequence[str],
    code_lines: Sequence[str],
    struct_lines: Sequence[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Language-agnostic C-family rules. Returns (findings, documentation_stats)."""
    findings: List[Dict[str, Any]] = []
    functions, classes = extract_c_family_units(struct_lines, lang)

    # --- Maintainability: method length & parameter count -------------------
    for fn in functions:
        length = fn["end"] - fn["start"] + 1
        if length > MAX_METHOD_LINES:
            findings.append(make_finding(
                rel_path, fn["start"], "EXCESSIVE_METHOD_LENGTH", "maintainability",
                "High" if length > 150 else "Medium",
                f"Excessive function length ({length} lines) in '{fn['name']}'",
                f"Function '{fn['name']}' spans {length} lines (recommended maximum: {MAX_METHOD_LINES}).",
                f"Lines {fn['start']}-{fn['end']} ({length} lines)",
                "Long functions obscure control flow and are harder to test and review.",
                "Extract cohesive steps into smaller, well-named functions.",
                length * 0.03, line_end=fn["end"], confidence="Medium",
            ))
        if fn["param_count"] > MAX_PARAMS:
            findings.append(make_finding(
                rel_path, fn["start"], "TOO_MANY_PARAMETERS", "maintainability", "Medium",
                f"Too many parameters ({fn['param_count']}) in '{fn['name']}'",
                f"Function '{fn['name']}' declares {fn['param_count']} parameters (threshold: {MAX_PARAMS}).",
                f"Line {fn['start']}: {lines[fn['start'] - 1].strip()[:100]}",
                "Long parameter lists indicate low cohesion and make call sites error-prone.",
                "Group related parameters into a typed options object or value type.",
                0.75, confidence="Medium",
            ))

    for cls in classes:
        length = cls["end"] - cls["start"] + 1
        if length > MAX_CLASS_LINES:
            findings.append(make_finding(
                rel_path, cls["start"], "LARGE_CLASS_DEFINITION", "maintainability",
                "High" if length > 1000 else "Medium",
                f"Large class '{cls['name']}' ({length} lines)",
                f"Class '{cls['name']}' spans {length} lines (threshold: {MAX_CLASS_LINES}).",
                f"Lines {cls['start']}-{cls['end']}",
                "Large classes usually accumulate several responsibilities (God object).",
                "Split responsibilities into collaborating classes or services.",
                length / 200.0, line_end=cls["end"], confidence="Medium",
            ))

    # --- Architecture: excessive imports -------------------------------------
    if lang == "go":
        import_count = _count_go_imports(code_lines)
    else:
        imp_re = _IMPORT_LINE.get(lang)
        import_count = sum(1 for l in code_lines if imp_re and imp_re.search(l)) if imp_re else 0
    if import_count > MAX_IMPORTS:
        findings.append(make_finding(
            rel_path, 1, "EXCESSIVE_MODULE_IMPORTS", "architecture", "Medium" if import_count > 50 else "Low",
            f"Module imports {import_count} dependencies",
            f"File declares {import_count} imports (threshold: {MAX_IMPORTS}), indicating high efferent coupling.",
            f"{import_count} import statements",
            "High fan-out modules are fragile: changes in any dependency can break them.",
            "Split the module along responsibilities or introduce a facade.",
            1.5, confidence="High",
        ))

    # --- Line-level security & reliability patterns --------------------------
    weak_hash = _WEAK_HASH.get(lang)
    insecure_tls = _INSECURE_TLS.get(lang)
    unsafe_exec = _UNSAFE_EXEC.get(lang)
    for idx, code in enumerate(code_lines, start=1):
        if not code.strip():
            continue
        evidence = f"Line {idx}: {lines[idx - 1].strip()[:100]}"
        if weak_hash and weak_hash.search(code):
            findings.append(make_finding(
                rel_path, idx, "WEAK_CRYPTO_HASH", "security", "Medium",
                "Weak cryptographic hash algorithm (MD5/SHA-1)",
                "MD5 and SHA-1 are collision-prone and unsuitable for security-sensitive hashing.",
                evidence,
                "Weak hashes allow forged signatures, integrity bypass and fast password cracking.",
                "Use SHA-256/SHA-3 for integrity, or Argon2/bcrypt/scrypt for passwords.",
                0.5, confidence="Medium",
            ))
        if insecure_tls and insecure_tls.search(code):
            findings.append(make_finding(
                rel_path, idx, "INSECURE_TLS_VERIFICATION", "security", "High",
                "TLS certificate verification disabled",
                "Disabling certificate or hostname verification accepts any server certificate.",
                evidence,
                "Disabled TLS verification enables man-in-the-middle interception of credentials and data.",
                "Keep verification enabled; trust a private CA bundle explicitly if required.",
                1.0, confidence="High",
            ))
        if unsafe_exec and unsafe_exec.search(code):
            findings.append(make_finding(
                rel_path, idx, "UNSAFE_COMMAND_EXEC", "security", "High",
                "OS command built from dynamic input",
                "A shell/OS command is executed with dynamically concatenated or interpolated input.",
                evidence,
                "Command injection lets attackers execute arbitrary commands on the host.",
                "Use argument-vector APIs without a shell and validate inputs against allow-lists.",
                1.5, confidence="Medium",
            ))
        if lang in ("c", "cpp") and re.search(r"(?<![\w.])(?:tmpnam|mktemp)\s*\(", code):
            findings.append(make_finding(
                rel_path, idx, "INSECURE_TEMP_FILE", "security", "Medium",
                "Race-prone temporary file creation (tmpnam/mktemp)",
                "tmpnam()/mktemp() return a predictable name that can be hijacked before use (TOCTOU).",
                evidence,
                "Attackers can pre-create or symlink the path to read or overwrite files.",
                "Use mkstemp() / tmpfile() which atomically create the file.",
                0.5, confidence="High",
            ))
        if lang == "go" and re.search(r"\bhttp\.(?:Get|Post|Head|PostForm)\(|\bhttp\.Client\{\s*\}", code):
            findings.append(make_finding(
                rel_path, idx, "HTTP_REQUEST_MISSING_TIMEOUT", "reliability", "Medium",
                "HTTP request without timeout (Go default client)",
                "http.Get/Post and zero-value http.Client have no timeout and can hang indefinitely.",
                evidence,
                "Hung outbound requests exhaust goroutines and connection pools under partial outages.",
                "Use an http.Client with an explicit Timeout or a context with deadline.",
                0.5, confidence="High",
            ))

    # --- Performance: I/O and regex compilation inside loops -----------------
    io_re = _IO_IN_LOOP.get(lang)
    rx_re = _REGEX_IN_LOOP.get(lang)
    reported_io: set = set()
    reported_rx: set = set()
    for header, end in _loop_ranges(struct_lines):
        for j in range(header + 1, end + 1):
            code = code_lines[j]
            if io_re and header not in reported_io and io_re.search(code):
                reported_io.add(header)
                findings.append(make_finding(
                    rel_path, j + 1, "DB_OR_HTTP_CALL_IN_LOOP", "performance", "Medium",
                    "Database or network call inside a loop (N+1 pattern)",
                    f"A database/HTTP call executes on every iteration of the loop starting at line {header + 1}.",
                    f"Line {j + 1}: {lines[j].strip()[:100]}",
                    "Per-iteration round-trips scale linearly with data size and dominate latency.",
                    "Batch the operation (bulk query, IN clause, eager loading) or parallelise with limits.",
                    1.5, line_end=end + 1, confidence="Medium",
                ))
            if rx_re and header not in reported_rx and rx_re.search(code):
                reported_rx.add(header)
                findings.append(make_finding(
                    rel_path, j + 1, "REGEX_COMPILE_IN_LOOP", "performance", "Low",
                    "Regular expression compiled inside a loop",
                    f"A regular expression is constructed on every iteration of the loop at line {header + 1}.",
                    f"Line {j + 1}: {lines[j].strip()[:100]}",
                    "Repeated regex compilation wastes CPU in hot paths.",
                    "Hoist the compiled pattern to a constant outside the loop.",
                    0.25, confidence="High",
                ))

    doc_stats = c_family_documentation_stats(lines, functions, classes, lang)
    return findings, doc_stats


def c_family_documentation_stats(
    lines: Sequence[str],
    functions: Sequence[Dict[str, Any]],
    classes: Sequence[Dict[str, Any]],
    lang: str,
) -> Dict[str, int]:
    """Counts declaration units preceded by a doc comment (/** */, ///, // or # in PHP)."""
    total = 0
    documented = 0
    for unit in list(functions) + list(classes):
        if unit.get("name") == "<anonymous>":
            continue
        total += 1
        j = unit["start"] - 2
        while j >= 0:
            prev = lines[j].strip()
            if not prev or prev.startswith("@") or prev.startswith("[") and lang == "csharp":
                if not prev and j < unit["start"] - 3:
                    break
                j -= 1
                continue
            if (
                prev.endswith("*/")
                or prev.startswith("///")
                or prev.startswith("//")
                or prev.startswith("*")
                or (lang == "php" and prev.startswith("#") and not prev.startswith("#["))
            ):
                documented += 1
            break
    return {"documented": documented, "total": total}


# =============================================================================
# Python AST supplementary rules
# =============================================================================

_PY_BLOCKING_CALLS = {
    ("time", "sleep"), ("requests", "get"), ("requests", "post"), ("requests", "put"),
    ("requests", "delete"), ("requests", "patch"), ("requests", "head"), ("requests", "request"),
    ("urllib.request", "urlopen"), ("subprocess", "run"), ("subprocess", "call"),
    ("subprocess", "check_output"),
}
_PY_REQUESTS_METHODS = {"get", "post", "put", "delete", "patch", "head", "options", "request"}
_PY_IO_IN_LOOP_ATTRS = {"execute", "executemany", "query", "fetch", "fetchrow", "fetchval"}


def _dotted(node: ast.AST) -> str:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _iter_stmt_lists(node: ast.AST):
    for field in ("body", "orelse", "finalbody"):
        stmts = getattr(node, field, None)
        if isinstance(stmts, list) and stmts and isinstance(stmts[0], ast.stmt):
            yield stmts
    for handler in getattr(node, "handlers", []) or []:
        yield handler.body
    for case in getattr(node, "cases", []) or []:
        yield case.body


def _walk_no_nested_defs(node: ast.AST):
    """Yields descendants of ``node`` without descending into nested function/class definitions."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        cur = stack.pop()
        yield cur
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(cur))


def analyze_python_extended(rel_path: str, tree: ast.AST, lines: Sequence[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    def ev(line_no: int) -> str:
        if 1 <= line_no <= len(lines):
            return f"Line {line_no}: {lines[line_no - 1].strip()[:100]}"
        return f"Line {line_no}"

    # Parent map (used for unclosed-file detection)
    parents: Dict[int, ast.AST] = {}
    with_ctx_ids: set = set()
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                with_ctx_ids.add(id(item.context_expr))

    # Module-level imports (architecture coupling)
    module_imports = set()
    for stmt in getattr(tree, "body", []):
        if isinstance(stmt, ast.Import):
            for a in stmt.names:
                module_imports.add(a.name)
        elif isinstance(stmt, ast.ImportFrom):
            module_imports.add(stmt.module or ".")
    if len(module_imports) > MAX_IMPORTS:
        findings.append(make_finding(
            rel_path, 1, "EXCESSIVE_MODULE_IMPORTS", "architecture",
            "Medium" if len(module_imports) > 50 else "Low",
            f"Module imports {len(module_imports)} distinct modules",
            f"Module depends on {len(module_imports)} distinct modules (threshold: {MAX_IMPORTS}).",
            f"{len(module_imports)} distinct imports",
            "High fan-out modules are fragile and hard to test in isolation.",
            "Split the module along responsibilities or introduce a facade.",
            1.5, confidence="High",
        ))

    reported_loops_io: set = set()
    reported_loops_rx: set = set()

    for node in ast.walk(tree):
        # Large classes
        if isinstance(node, ast.ClassDef):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            length = end - start + 1
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if length > MAX_CLASS_LINES or len(methods) > 25:
                findings.append(make_finding(
                    rel_path, start, "PY_LARGE_CLASS", "maintainability",
                    "High" if length > 1000 or len(methods) > 40 else "Medium",
                    f"Large class '{node.name}' ({length} lines, {len(methods)} methods)",
                    f"Class '{node.name}' spans {length} lines with {len(methods)} methods "
                    f"(thresholds: {MAX_CLASS_LINES} lines / 25 methods).",
                    f"class {node.name} [lines {start}-{end}]",
                    "Large classes accumulate unrelated responsibilities and become change hotspots.",
                    "Extract cohesive groups of methods into collaborating classes.",
                    length / 200.0, line_end=end, confidence="High",
                ))

        # Unreachable code after return/raise/break/continue
        for stmts in _iter_stmt_lists(node):
            for i, stmt in enumerate(stmts[:-1]):
                if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                    dead = stmts[i + 1]
                    findings.append(make_finding(
                        rel_path, dead.lineno, "PY_UNREACHABLE_CODE", "maintainability", "Low",
                        f"Unreachable code after '{type(stmt).__name__.lower()}'",
                        f"Statement at line {dead.lineno} can never execute because the preceding "
                        f"'{type(stmt).__name__.lower()}' at line {stmt.lineno} always exits the block.",
                        ev(dead.lineno),
                        "Dead code misleads readers and often hides logic errors.",
                        "Remove the dead statements or fix the control flow.",
                        0.25, line_end=getattr(stmts[-1], "end_lineno", dead.lineno), confidence="High",
                    ))
                    break

        # Blocking I/O inside async functions
        if isinstance(node, ast.AsyncFunctionDef):
            for sub in _walk_no_nested_defs(node):
                if isinstance(sub, ast.Call):
                    dotted = _dotted(sub.func)
                    if "." in dotted:
                        base, attr = dotted.rsplit(".", 1)
                        if (base, attr) in _PY_BLOCKING_CALLS:
                            findings.append(make_finding(
                                rel_path, sub.lineno, "PY_BLOCKING_IO_IN_ASYNC", "performance", "High",
                                f"Blocking call '{dotted}()' inside async function '{node.name}'",
                                f"'{dotted}()' blocks the event loop thread inside coroutine '{node.name}'.",
                                ev(sub.lineno),
                                "A single blocking call stalls every concurrent request served by the event loop.",
                                "Use async equivalents (asyncio.sleep, httpx.AsyncClient, asyncio.create_subprocess_exec) "
                                "or offload with asyncio.to_thread().",
                                1.0, confidence="High",
                            ))

        # Loop-scoped performance rules
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            header = getattr(node, "iter", None) if not isinstance(node, ast.While) else node.test
            header_ids = {id(n) for n in ast.walk(header)} if header is not None else set()
            for sub in _walk_no_nested_defs(node):
                # Calls in the loop header (iterable / condition) execute once per check, not per body.
                if not isinstance(sub, ast.Call) or id(sub) in header_ids:
                    continue
                dotted = _dotted(sub.func)
                base, _, attr = dotted.rpartition(".")
                is_io = (
                    (base in ("requests", "httpx") and attr in _PY_REQUESTS_METHODS)
                    or attr in _PY_IO_IN_LOOP_ATTRS
                    or (base.endswith(".objects") and attr in ("get", "filter", "create"))
                )
                if is_io and id(node) not in reported_loops_io:
                    reported_loops_io.add(id(node))
                    findings.append(make_finding(
                        rel_path, sub.lineno, "DB_OR_HTTP_CALL_IN_LOOP", "performance", "Medium",
                        f"Database or network call '{dotted}()' inside a loop (N+1 pattern)",
                        f"'{dotted}()' executes on every iteration of the loop starting at line {node.lineno}.",
                        ev(sub.lineno),
                        "Per-iteration round-trips scale linearly with data size and dominate latency.",
                        "Batch the work (bulk queries, IN clauses, eager loading, gather with limits).",
                        1.5, line_end=getattr(node, "end_lineno", sub.lineno), confidence="Medium",
                    ))
                if dotted == "re.compile" and id(node) not in reported_loops_rx:
                    reported_loops_rx.add(id(node))
                    findings.append(make_finding(
                        rel_path, sub.lineno, "REGEX_COMPILE_IN_LOOP", "performance", "Low",
                        "Regular expression compiled inside a loop",
                        f"re.compile() runs on every iteration of the loop at line {node.lineno}.",
                        ev(sub.lineno),
                        "Repeated compilation wastes CPU in hot paths.",
                        "Hoist the compiled pattern to module level.",
                        0.25, confidence="High",
                    ))

        if not isinstance(node, ast.Call):
            continue

        dotted = _dotted(node.func)
        kw_names = {kw.arg for kw in node.keywords if kw.arg}

        # Missing timeout on requests.*
        base, _, attr = dotted.rpartition(".")
        if base == "requests" and attr in _PY_REQUESTS_METHODS and "timeout" not in kw_names:
            has_kwargs_splat = any(kw.arg is None for kw in node.keywords)
            if not has_kwargs_splat:
                findings.append(make_finding(
                    rel_path, node.lineno, "HTTP_REQUEST_MISSING_TIMEOUT", "reliability", "Medium",
                    f"HTTP request '{dotted}()' without timeout",
                    "requests has no default timeout; the call can block indefinitely on a stalled server.",
                    ev(node.lineno),
                    "Hung requests exhaust worker threads and cascade into outages.",
                    "Always pass timeout=(connect, read), e.g. timeout=(3.05, 30).",
                    0.25, confidence="High",
                ))

        # Disabled TLS verification
        for kw in node.keywords:
            if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                findings.append(make_finding(
                    rel_path, node.lineno, "INSECURE_TLS_VERIFICATION", "security", "High",
                    "TLS certificate verification disabled (verify=False)",
                    f"'{dotted or 'call'}(..., verify=False)' accepts any server certificate.",
                    ev(node.lineno),
                    "Disabled verification enables man-in-the-middle interception.",
                    "Remove verify=False; pass a CA bundle path if a private CA is required.",
                    0.5, confidence="High",
                ))
        if dotted in ("ssl._create_unverified_context",):
            findings.append(make_finding(
                rel_path, node.lineno, "INSECURE_TLS_VERIFICATION", "security", "High",
                "Unverified SSL context created",
                "ssl._create_unverified_context() disables certificate and hostname checks.",
                ev(node.lineno),
                "Disabled verification enables man-in-the-middle interception.",
                "Use ssl.create_default_context().",
                0.5, confidence="High",
            ))

        # Weak hashes
        if dotted in ("hashlib.md5", "hashlib.sha1") or (
            dotted == "hashlib.new" and node.args and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value).lower() in ("md5", "sha1")
        ):
            not_for_security = any(
                kw.arg == "usedforsecurity" and isinstance(kw.value, ast.Constant) and kw.value.value is False
                for kw in node.keywords
            )
            if not not_for_security:
                findings.append(make_finding(
                    rel_path, node.lineno, "WEAK_CRYPTO_HASH", "security", "Medium",
                    f"Weak hash algorithm via {dotted}()",
                    "MD5/SHA-1 are collision-prone. If used for non-security purposes, declare usedforsecurity=False.",
                    ev(node.lineno),
                    "Weak hashes allow integrity bypass and fast password cracking.",
                    "Use hashlib.sha256 / blake2b, or a password KDF (argon2, bcrypt, scrypt).",
                    0.5, confidence="Medium",
                ))

        # Insecure temp files
        if dotted == "tempfile.mktemp":
            findings.append(make_finding(
                rel_path, node.lineno, "INSECURE_TEMP_FILE", "security", "Medium",
                "Race-prone tempfile.mktemp()",
                "tempfile.mktemp() returns a name without creating the file (TOCTOU race).",
                ev(node.lineno),
                "Attackers can pre-create or symlink the path.",
                "Use tempfile.mkstemp(), NamedTemporaryFile() or TemporaryDirectory().",
                0.25, confidence="High",
            ))

        # Unclosed file handles
        if isinstance(node.func, ast.Name) and node.func.id == "open" and id(node) not in with_ctx_ids:
            parent = parents.get(id(node))
            if isinstance(parent, (ast.Assign, ast.AnnAssign)):
                findings.append(make_finding(
                    rel_path, node.lineno, "PY_UNCLOSED_FILE_HANDLE", "reliability", "Medium",
                    "File opened without a context manager",
                    "open() result is assigned without 'with'; the handle leaks if an exception occurs before close().",
                    ev(node.lineno),
                    "Leaked file descriptors exhaust OS limits and can lose buffered writes.",
                    "Use 'with open(...) as f:' to guarantee closure.",
                    0.25, confidence="Medium",
                ))
            elif isinstance(parent, ast.Attribute):
                findings.append(make_finding(
                    rel_path, node.lineno, "PY_UNCLOSED_FILE_HANDLE", "reliability", "Low",
                    "File handle opened inline and never explicitly closed",
                    "open(...).read()/write() relies on garbage collection to close the file.",
                    ev(node.lineno),
                    "Non-CPython runtimes may delay closing, leaking descriptors and buffered data.",
                    "Use 'with open(...) as f:' or pathlib.Path.read_text().",
                    0.1, confidence="Medium",
                ))

    return findings


def python_documentation_stats(content: str) -> Tuple[Dict[str, int], bool]:
    """Returns ({documented, total}, has_module_docstring). Private (_name) defs are excluded."""
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return {"documented": 0, "total": 0}, False
    has_module_doc = ast.get_docstring(tree) is not None
    total = 1
    documented = 1 if has_module_doc else 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            total += 1
            if ast.get_docstring(node) is not None:
                documented += 1
    return {"documented": documented, "total": total}, has_module_doc


# =============================================================================
# Test coverage artifacts (never fabricated)
# =============================================================================

COVERAGE_FILENAMES = {"coverage.xml", "cobertura-coverage.xml", "cobertura.xml", "jacoco.xml", "lcov.info", "coverage-summary.json"}
_COVERAGE_SKIP_DIRS = {"node_modules", ".git", "vendor", ".venv", "venv", "__pycache__", ".tox", "site-packages"}
_MAX_COVERAGE_FILE_BYTES = 25 * 1024 * 1024


def _safe_xml_root(path: str) -> Optional[ET.Element]:
    with open(path, "rb") as fh:
        raw = fh.read(_MAX_COVERAGE_FILE_BYTES + 1)
    if len(raw) > _MAX_COVERAGE_FILE_BYTES:
        return None
    # Entity declarations are never required for coverage reports; refuse them to rule out
    # entity-expansion attacks from untrusted repository content.
    if b"<!ENTITY" in raw.upper():
        return None
    return ET.fromstring(raw)


def _parse_cobertura(path: str) -> Optional[Tuple[int, int]]:
    root = _safe_xml_root(path)
    if root is None or root.tag != "coverage":
        return None
    valid = root.attrib.get("lines-valid")
    covered = root.attrib.get("lines-covered")
    if valid is not None and covered is not None and int(float(valid)) > 0:
        return int(float(covered)), int(float(valid))
    rate = root.attrib.get("line-rate")
    if rate is not None:
        # Without absolute counts use a nominal weight of 1000 lines.
        return int(round(float(rate) * 1000)), 1000
    return None


def _parse_jacoco(path: str) -> Optional[Tuple[int, int]]:
    root = _safe_xml_root(path)
    if root is None or root.tag != "report":
        return None
    for counter in root.findall("counter"):
        if counter.attrib.get("type") == "LINE":
            missed = int(counter.attrib.get("missed", 0))
            covered = int(counter.attrib.get("covered", 0))
            if missed + covered > 0:
                return covered, missed + covered
    return None


def _parse_lcov(path: str) -> Optional[Tuple[int, int]]:
    hit = found = 0
    if os.path.getsize(path) > _MAX_COVERAGE_FILE_BYTES:
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("LH:"):
                hit += int(line[3:].strip() or 0)
            elif line.startswith("LF:"):
                found += int(line[3:].strip() or 0)
    return (hit, found) if found > 0 else None


def _parse_istanbul_summary(path: str) -> Optional[Tuple[int, int]]:
    if os.path.getsize(path) > _MAX_COVERAGE_FILE_BYTES:
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)
    lines = (data.get("total") or {}).get("lines") or {}
    total = int(lines.get("total") or 0)
    covered = int(lines.get("covered") or 0)
    if total > 0:
        return covered, total
    return None


def parse_coverage_artifacts(root_dir: str, max_depth: int = 4) -> Dict[str, Any]:
    """
    Locates and parses real coverage reports under ``root_dir``.

    Returns ``{"measured_test_coverage_pct": float|None, "coverage_artifacts": [...],
    "coverage_errors": [...]}``. When no artifact can be parsed the percentage is ``None``.
    """
    root_dir = os.path.abspath(root_dir)
    artifacts: List[Dict[str, Any]] = []
    errors: List[str] = []
    total_covered = 0
    total_lines = 0

    for current, dirs, files in os.walk(root_dir):
        depth = os.path.relpath(current, root_dir).count(os.sep)
        dirs[:] = [d for d in dirs if d not in _COVERAGE_SKIP_DIRS]
        if depth >= max_depth:
            dirs[:] = []
        for name in files:
            lower = name.lower()
            if lower not in COVERAGE_FILENAMES:
                continue
            path = os.path.join(current, name)
            if os.path.islink(path):
                continue
            rel = os.path.relpath(path, root_dir).replace("\\", "/")
            try:
                if lower == "lcov.info":
                    res, fmt = _parse_lcov(path), "lcov"
                elif lower == "coverage-summary.json":
                    res, fmt = _parse_istanbul_summary(path), "istanbul-summary"
                elif lower == "jacoco.xml":
                    res, fmt = _parse_jacoco(path), "jacoco"
                else:
                    res, fmt = _parse_cobertura(path), "cobertura"
            except Exception as exc:  # malformed artifact must not break analysis
                errors.append(f"{rel}: {type(exc).__name__}")
                continue
            if res is None:
                errors.append(f"{rel}: unrecognised or empty coverage report")
                continue
            covered, total = res
            total_covered += covered
            total_lines += total
            artifacts.append({
                "path": rel,
                "format": fmt,
                "lines_covered": covered,
                "lines_total": total,
                "line_coverage_pct": round(covered * 100.0 / total, 1),
            })

    pct = round(total_covered * 100.0 / total_lines, 1) if total_lines > 0 else None
    return {"measured_test_coverage_pct": pct, "coverage_artifacts": artifacts, "coverage_errors": errors}
