import os
import re
import ast
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Set

class CodeFindingItem:
    def __init__(self, d: Dict[str, Any]):
        self._d = d
        for k, v in d.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return self._d

    def __getitem__(self, key):
        return self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __repr__(self):
        return f"<CodeFindingItem rule_id={getattr(self, 'rule_id', '')} severity={getattr(self, 'severity', '')}>"


class AnalysisResult:
    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.files_analyzed = data.get("files_analyzed", 0)
        self.total_files = self.files_analyzed
        self.lines_of_code = data.get("lines_of_code", 0)
        self.total_lines_of_code = self.lines_of_code
        self.test_files_count = data.get("test_files_count", 0)
        self.avg_complexity = data.get("avg_cyclomatic_complexity", 1.0)
        self.max_complexity = data.get("max_cyclomatic_complexity", 1)
        self.code_duplication_percentage = data.get("code_duplication_percentage", 0.0)
        self.maintainability_index = data.get("maintainability_index", 85.0)
        self.total_remediation_hours = data.get("total_remediation_hours", 0.0)
        self.findings = [CodeFindingItem(f) for f in data.get("findings", [])]
        self.hotspots = data.get("hotspots", [])

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)


class SourceCodeAnalyzer:
    """
    Production-grade multi-language source code static intelligence engine.
    Analyzes Python, JavaScript, TypeScript, Java, Go, PHP, C#, C/C++ repositories.
    Calculates cyclomatic complexity, code duplication, nesting depth, architecture smell,
    and security anti-patterns with verifiable technical evidence.
    """

    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".php": "php",
        ".cs": "csharp",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp"
    }

    IGNORE_DIRS = {
        "node_modules", "vendor", ".git", ".github", "__pycache__", ".pytest_cache",
        "dist", "build", ".next", ".nuxt", "target", "bin", "obj", ".venv", "venv",
        "env", ".idea", ".vscode", "coverage", ".turbo"
    }

    SECRET_PATTERNS = [
        (re.compile(r"""(?i)(?:api_key|apikey|secret|password|passwd|auth_token|access_token|private_key|aws_access_key|aws_secret|token)\s*[:=]\s*['"][a-zA-Z0-9_\-\.\/+=]{16,}['"]"""), "HARDCODED_SECRET_SUSPECTED", "Hardcoded credential or API secret pattern detected in source file", "Critical"),
        (re.compile(r"""ghp_[a-zA-Z0-9]{20,}"""), "GITHUB_TOKEN_EXPOSED", "GitHub personal access token exposed in source code", "Critical"),
        (re.compile(r"""-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"""), "HARDCODED_PRIVATE_KEY", "Unencrypted private cryptographic key committed in source file", "Critical"),
    ]

    DANGEROUS_CALLS = [
        (re.compile(r"""\b(eval|exec)\s*\("""), "DANGEROUS_EVAL_USAGE", "Dynamic code execution via eval/exec introduces arbitrary code execution vulnerabilities", "Critical"),
        (re.compile(r"""\bsubprocess\.(?:Popen|call|run|check_output)\s*\(.*shell\s*=\s*True"""), "DANGEROUS_SHELL_INJECTION", "Subprocess execution with shell=True invites command injection attacks", "High"),
        (re.compile(r"""(?i)(?:execute|query)\s*\(\s*f['"].*\{.*\}"""), "SQL_INJECTION_FORMAT_STRING", "Potential SQL injection: Raw string formatting detected inside database query call", "Critical"),
    ]

    def __init__(self, root_dir: str = ".", max_files: int = 2000, max_file_size_bytes: int = 1024 * 1024):
        self.root_dir = os.path.abspath(root_dir) if root_dir else os.path.abspath(".")
        self.max_files = max_files
        self.max_file_size_bytes = max_file_size_bytes

    def analyze_directory(self, dir_path: Optional[str] = None) -> AnalysisResult:
        """Analyzes a directory and returns wrapped AnalysisResult with attribute and key access."""
        if dir_path:
            self.root_dir = os.path.abspath(dir_path)
        raw_res = self.analyze_repository()
        return AnalysisResult(raw_res)

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """Analyzes a single source code file and returns metrics and findings."""
        abs_path = os.path.abspath(file_path)
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = content.splitlines()
        loc = len(lines)
        ext = os.path.splitext(file_path)[1].lower()
        lang = self.SUPPORTED_EXTENSIONS.get(ext, "unknown")

        complexity = 1
        raw_findings = []
        if lang == "python":
            comp, py_findings = self._analyze_python(file_path, content, lines)
            complexity = max(complexity, comp)
            raw_findings.extend(py_findings)
        else:
            comp, gen_findings = self._analyze_generic_code(file_path, content, lines, lang)
            complexity = max(complexity, comp)
            raw_findings.extend(gen_findings)

        sec_findings = self._scan_security_patterns(file_path, lines)
        raw_findings.extend(sec_findings)

        return {
            "file_path": file_path,
            "lines_of_code": loc,
            "cyclomatic_complexity": complexity,
            "findings": [CodeFindingItem(f) for f in raw_findings]
        }

    def analyze_repository(self) -> Dict[str, Any]:
        """
        Executes static analysis across all supported source code files in repository.
        Returns comprehensive metrics, file hotspots, and structured findings.
        """
        files_to_analyze: List[str] = []
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in self.SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    try:
                        if os.path.getsize(full_path) <= self.max_file_size_bytes:
                            files_to_analyze.append(full_path)
                    except OSError:
                        continue
                if len(files_to_analyze) >= self.max_files:
                    break
            if len(files_to_analyze) >= self.max_files:
                break

        findings: List[Dict[str, Any]] = []
        total_loc = 0
        file_metrics: Dict[str, Dict[str, Any]] = {}
        all_line_hashes: Dict[str, List[Tuple[str, int]]] = {}  # hash -> [(file_rel, line_no)]
        test_files_count = 0

        for file_path in files_to_analyze:
            rel_path = os.path.relpath(file_path, self.root_dir).replace("\\", "/")
            ext = os.path.splitext(file_path)[1].lower()
            lang = self.SUPPORTED_EXTENSIONS.get(ext, "unknown")

            # Check if this is a test file
            is_test = any(pattern in rel_path.lower() for pattern in [
                "/test/", "/tests/", "test_", "_test.", ".spec.", ".test.", "testcase", "tests."
            ])
            if is_test:
                test_files_count += 1

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            lines = content.splitlines()
            loc = len(lines)
            total_loc += loc

            # Language-specific analysis
            file_findings: List[Dict[str, Any]] = []
            complexity = 1
            if lang == "python":
                comp, py_findings = self._analyze_python(rel_path, content, lines)
                complexity = max(complexity, comp)
                file_findings.extend(py_findings)
            else:
                comp, generic_findings = self._analyze_generic_code(rel_path, content, lines, lang)
                complexity = max(complexity, comp)
                file_findings.extend(generic_findings)

            # Security regex scans
            sec_findings = self._scan_security_patterns(rel_path, lines)
            file_findings.extend(sec_findings)

            # Track duplicate lines (normalized blocks of 6+ non-empty lines)
            self._index_code_lines_for_duplication(rel_path, lines, all_line_hashes)

            file_metrics[rel_path] = {
                "loc": loc,
                "complexity": complexity,
                "findings_count": len(file_findings),
                "language": lang,
                "is_test": is_test
            }
            findings.extend(file_findings)

        # Detect cross-file code duplication
        dup_findings, dup_lines_count = self._detect_code_duplications(all_line_hashes)
        findings.extend(dup_findings)

        # Calculate overall metrics
        files_count = len(files_to_analyze)
        avg_complexity = sum(m["complexity"] for m in file_metrics.values()) / max(1, files_count)
        max_complexity = max((m["complexity"] for m in file_metrics.values()), default=1)
        duplication_pct = round((dup_lines_count / max(1, total_loc)) * 100, 1)

        # Calculate Maintainability Index (0-100) based on Halstead Volume and Cyclomatic Complexity approximation
        # MI = max(0, min(100, 171 - 5.2 * ln(avg_loc) - 0.23 * avg_comp - 16.2 * ln(total_loc)))
        import math
        avg_loc = total_loc / max(1, files_count)
        try:
            mi_raw = 171.0 - 5.2 * math.log(max(1, avg_loc)) - 0.23 * avg_complexity - 1.5 * (len(findings) / max(1, files_count))
            maintainability_index = round(max(10.0, min(100.0, mi_raw * 100.0 / 171.0)), 1)
        except Exception:
            maintainability_index = 80.0

        # Identify hotspots (files with highest risk & finding density)
        hotspots = sorted(
            [
                {
                    "file_path": path,
                    "loc": data["loc"],
                    "complexity": data["complexity"],
                    "findings_count": data["findings_count"],
                    "language": data["language"]
                }
                for path, data in file_metrics.items()
                if data["findings_count"] > 0 or data["complexity"] > 15 or data["loc"] > 500
            ],
            key=lambda x: (x["findings_count"] * 2 + x["complexity"]),
            reverse=True
        )[:15]

        # Calculate estimated total remediation hours
        total_remediation_hours = round(sum(f.get("estimated_remediation_hours", 1.0) for f in findings), 1)

        return {
            "files_analyzed": files_count,
            "lines_of_code": total_loc,
            "test_files_count": test_files_count,
            "avg_cyclomatic_complexity": round(avg_complexity, 1),
            "max_cyclomatic_complexity": max_complexity,
            "code_duplication_percentage": duplication_pct,
            "maintainability_index": maintainability_index,
            "total_remediation_hours": total_remediation_hours,
            "findings": findings,
            "hotspots": hotspots
        }

    # =========================================================================
    # Python AST Analysis
    # =========================================================================

    def _analyze_python(self, rel_path: str, content: str, lines: List[str]) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        max_file_complexity = 1

        try:
            tree = ast.parse(content, filename=rel_path)
        except SyntaxError as se:
            findings.append({
                "file_path": rel_path,
                "line_start": se.lineno or 1,
                "line_end": se.lineno or 1,
                "rule_id": "SYNTAX_PARSE_ERROR",
                "category": "reliability",
                "severity": "High",
                "confidence": "High",
                "title": f"Python syntax parse failure: {se.msg}",
                "explanation": f"Source file cannot be parsed into an Abstract Syntax Tree: {se.msg}",
                "technical_evidence": f"Line {se.lineno}: {se.text.strip() if se.text else ''}",
                "why_it_matters": "Syntax errors prevent static analysis, automated testing, and execution.",
                "recommended_remediation": "Correct syntax syntax constructs to maintain compilation integrity.",
                "estimated_remediation_hours": 0.5,
                "is_auto_verifiable": True
            })
            return 1, findings

        # Check file length
        if len(lines) > 600:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": len(lines),
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive file length ({len(lines)} lines)",
                "explanation": f"Module exceeds recommended length limit of 600 lines ({len(lines)} lines detected).",
                "technical_evidence": f"Total LOC: {len(lines)}",
                "why_it_matters": "Monolithic files degrade code comprehension, violate single-responsibility principle, and increase merge conflicts.",
                "recommended_remediation": "Decompose into cohesive domain submodules or separate utility classes.",
                "estimated_remediation_hours": round(len(lines) / 200, 1),
                "is_auto_verifiable": True
            })

        # Deep nesting tracker
        def _check_nesting(node: ast.AST, current_depth: int = 0) -> None:
            nonlocal findings
            is_control = isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.Try))
            next_depth = current_depth + 1 if is_control else current_depth

            if is_control and current_depth >= 4:
                start_l = getattr(node, "lineno", 1)
                end_l = getattr(node, "end_lineno", start_l)
                findings.append({
                    "file_path": rel_path,
                    "line_start": start_l,
                    "line_end": end_l,
                    "rule_id": "PY_DEEP_NESTING",
                    "category": "complexity",
                    "severity": "Medium" if current_depth == 4 else "High",
                    "confidence": "High",
                    "title": f"Deeply nested control flow (depth {current_depth + 1})",
                    "explanation": f"Control block exceeds recommended maximum nesting depth of 4 levels (depth: {current_depth + 1}).",
                    "technical_evidence": f"Line {start_l}: nested {node.__class__.__name__} statement at nesting depth {current_depth + 1}",
                    "why_it_matters": "Deeply nested blocks severely impair readability, increase mental overhead, and lead to logic errors.",
                    "recommended_remediation": "Flatten control flow using early returns, guard clauses, or method extraction.",
                    "estimated_remediation_hours": 1.0,
                    "is_auto_verifiable": True
                })

            for child in ast.iter_child_nodes(node):
                _check_nesting(child, next_depth)

        _check_nesting(tree)

        for node in ast.walk(tree):
            # 1. Function Complexity, Length, Arguments, & Mutable Defaults
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                func_start = node.lineno
                func_end = getattr(node, "end_lineno", func_start + 1)
                func_len = func_end - func_start + 1

                # Calculate McCabe Cyclomatic Complexity
                complexity = 1
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.AsyncWith)):
                        complexity += 1
                    elif isinstance(sub, ast.BoolOp):
                        complexity += len(sub.values) - 1
                    elif isinstance(sub, ast.IfExp):
                        complexity += 1

                max_file_complexity = max(max_file_complexity, complexity)

                if complexity > 12:
                    severity = "Critical" if complexity > 25 else "High"
                    findings.append({
                        "file_path": rel_path,
                        "line_start": func_start,
                        "line_end": func_end,
                        "rule_id": "PY_HIGH_CYCLOMATIC_COMPLEXITY",
                        "category": "complexity",
                        "severity": severity,
                        "confidence": "High",
                        "title": f"High cyclomatic complexity ({complexity}) in '{func_name}'",
                        "explanation": f"Function '{func_name}' contains {complexity} linearly independent paths (threshold: 12).",
                        "technical_evidence": f"def {func_name}(...) [lines {func_start}-{func_end}]: Cyclomatic complexity = {complexity}",
                        "why_it_matters": "Functions with high cyclomatic complexity require exponentially more test cases and are 4x more prone to defects.",
                        "recommended_remediation": "Extract conditional branches and helper routines into dedicated single-purpose methods.",
                        "estimated_remediation_hours": round(complexity * 0.25, 1),
                        "is_auto_verifiable": True
                    })

                if func_len > 80:
                    findings.append({
                        "file_path": rel_path,
                        "line_start": func_start,
                        "line_end": func_end,
                        "rule_id": "PY_LONG_FUNCTION",
                        "category": "maintainability",
                        "severity": "Medium" if func_len < 150 else "High",
                        "confidence": "High",
                        "title": f"Excessive function length ({func_len} lines) in '{func_name}'",
                        "explanation": f"Function '{func_name}' spans {func_len} lines (recommended maximum: 80 lines).",
                        "technical_evidence": f"Lines {func_start}-{func_end} ({func_len} lines)",
                        "why_it_matters": "Long functions obscure execution flow, encourage variable leakage, and complicate unit testing.",
                        "recommended_remediation": "Refactor into smaller composable functions adhering to single-responsibility principle.",
                        "estimated_remediation_hours": round(func_len * 0.03, 1),
                        "is_auto_verifiable": True
                    })

                # Parameter count
                total_args = len(node.args.args) + len(node.args.kwonlyargs)
                if total_args > 6:
                    findings.append({
                        "file_path": rel_path,
                        "line_start": func_start,
                        "line_end": func_start,
                        "rule_id": "PY_TOO_MANY_ARGUMENTS",
                        "category": "maintainability",
                        "severity": "Medium",
                        "confidence": "High",
                        "title": f"Too many function parameters ({total_args}) in '{func_name}'",
                        "explanation": f"Function '{func_name}' defines {total_args} parameters (threshold: 6).",
                        "technical_evidence": f"def {func_name}({total_args} arguments)",
                        "why_it_matters": "Functions with many parameters indicate low cohesion and make call sites error-prone and brittle.",
                        "recommended_remediation": "Encapsulate parameters into a dedicated options object, dataclass, or Pydantic model.",
                        "estimated_remediation_hours": 0.75,
                        "is_auto_verifiable": True
                    })

                # Mutable default arguments
                for default_val in node.args.defaults + node.args.kw_defaults:
                    if isinstance(default_val, (ast.List, ast.Dict, ast.Set)):
                        d_line = getattr(default_val, "lineno", func_start)
                        findings.append({
                            "file_path": rel_path,
                            "line_start": d_line,
                            "line_end": d_line,
                            "rule_id": "PY_MUTABLE_DEFAULT_ARG",
                            "category": "reliability",
                            "severity": "High",
                            "confidence": "High",
                            "title": f"Dangerous mutable default argument in '{func_name}'",
                            "explanation": f"Function '{func_name}' uses a mutable default value (list/dict/set), which persists mutations across all calls.",
                            "technical_evidence": f"Line {d_line}: Mutable default {default_val.__class__.__name__} detected",
                            "why_it_matters": "Python default arguments are evaluated once at module load time; mutating them produces unpredictable shared state bugs.",
                            "recommended_remediation": "Default the parameter to None and initialize a new container inside the function body.",
                            "estimated_remediation_hours": 0.25,
                            "is_auto_verifiable": True
                        })

            # 2. Bare Exception Handling & Silent Exception Swallowing
            elif isinstance(node, ast.ExceptHandler):
                handler_start = node.lineno
                handler_end = getattr(node, "end_lineno", handler_start)
                is_bare = node.type is None
                is_broad = False
                if node.type:
                    if isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
                        is_broad = True

                is_swallowed = False
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    is_swallowed = True

                if is_bare or (is_broad and is_swallowed):
                    findings.append({
                        "file_path": rel_path,
                        "line_start": handler_start,
                        "line_end": handler_end,
                        "rule_id": "BARE_OR_SWALLOWED_EXCEPTION",
                        "category": "reliability",
                        "severity": "High" if is_swallowed else "Medium",
                        "confidence": "High",
                        "title": "Silent exception swallowing or unhandled bare except clause",
                        "explanation": "Catching all exceptions with a bare 'except:' or broad 'except Exception: pass' hides critical operational failures and keyboard interrupts.",
                        "technical_evidence": f"Line {handler_start}: except {'Exception: pass' if is_swallowed else 'clause without specific error type'}",
                        "why_it_matters": "Silently swallowing exceptions masks system defects, corrupts transaction states, and makes root-cause debugging nearly impossible.",
                        "recommended_remediation": "Catch explicit exception types and log errors with tracebacks.",
                        "estimated_remediation_hours": 0.5,
                        "is_auto_verifiable": True
                    })

            # 3. Insecure Deserialization & Dangerous Calls
            elif isinstance(node, ast.Call):
                call_line = node.lineno
                # Check pickle.loads / pickle.load
                if isinstance(node.func, ast.Attribute) and node.func.attr in ("load", "loads"):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id in ("pickle", "_pickle", "cPickle"):
                        findings.append({
                            "file_path": rel_path,
                            "line_start": call_line,
                            "line_end": call_line,
                            "rule_id": "PY_INSECURE_DESERIALIZATION_PICKLE",
                            "category": "security",
                            "severity": "Critical",
                            "confidence": "High",
                            "title": "Insecure object deserialization via pickle",
                            "explanation": f"Call to '{node.func.value.id}.{node.func.attr}()' deserializes untrusted data into arbitrary Python bytecode.",
                            "technical_evidence": f"Line {call_line}: {node.func.value.id}.{node.func.attr}(...)",
                            "why_it_matters": "Pickle deserialization allows Remote Code Execution (RCE) if any part of the payload originates from untrusted sources.",
                            "recommended_remediation": "Use safe serialization formats like JSON, Protobuf, or MsgPack.",
                            "estimated_remediation_hours": 1.5,
                            "is_auto_verifiable": True
                        })
                    elif isinstance(node.func.value, ast.Name) and node.func.value.id == "yaml" and node.func.attr == "load":
                        # Check if Loader keyword argument is present and safe
                        has_safe_loader = any(kw.arg == "Loader" and "SafeLoader" in getattr(kw.value, "attr", "") for kw in node.keywords)
                        if not has_safe_loader:
                            findings.append({
                                "file_path": rel_path,
                                "line_start": call_line,
                                "line_end": call_line,
                                "rule_id": "PY_UNSAFE_YAML_LOAD",
                                "category": "security",
                                "severity": "Critical",
                                "confidence": "High",
                                "title": "Unsafe PyYAML loading without SafeLoader",
                                "explanation": "yaml.load() without explicit SafeLoader can execute arbitrary Python objects.",
                                "technical_evidence": f"Line {call_line}: yaml.load() call",
                                "why_it_matters": "Untrusted YAML payloads can construct Python objects and achieve remote code execution.",
                                "recommended_remediation": "Use yaml.safe_load() or specify Loader=yaml.SafeLoader.",
                                "estimated_remediation_hours": 0.5,
                                "is_auto_verifiable": True
                            })
                # Check eval / exec
                elif isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                    findings.append({
                        "file_path": rel_path,
                        "line_start": call_line,
                        "line_end": call_line,
                        "rule_id": "PY_DANGEROUS_EVAL",
                        "category": "security",
                        "severity": "Critical",
                        "confidence": "High",
                        "title": f"Dangerous dynamic execution via {node.func.id}()",
                        "explanation": f"Using {node.func.id}() executes dynamic Python expressions or bytecode at runtime.",
                        "technical_evidence": f"Line {call_line}: {node.func.id}(...)",
                        "why_it_matters": "Dynamic code execution invites severe code injection and sandbox escape vulnerabilities.",
                        "recommended_remediation": "Use ast.literal_eval() for safe data evaluation or statically dispatch methods.",
                        "estimated_remediation_hours": 1.0,
                        "is_auto_verifiable": True
                    })

            # 4. Wildcard Imports
            elif isinstance(node, ast.ImportFrom):
                if any(alias.name == "*" for alias in node.names):
                    line_no = node.lineno
                    findings.append({
                        "file_path": rel_path,
                        "line_start": line_no,
                        "line_end": line_no,
                        "rule_id": "PY_WILDCARD_IMPORT",
                        "category": "maintainability",
                        "severity": "Low",
                        "confidence": "High",
                        "title": f"Wildcard import 'from {node.module or ''} import *'",
                        "explanation": "Wildcard imports pollute the module namespace and obscure symbol origin.",
                        "technical_evidence": f"Line {line_no}: from {node.module or ''} import *",
                        "why_it_matters": "Wildcard imports break static analysis, hide symbol origins, and risk subtle namespace collisions.",
                        "recommended_remediation": "Explicitly import required identifiers by name.",
                        "estimated_remediation_hours": 0.25,
                        "is_auto_verifiable": True
                    })

            # 5. Global Statement
            elif isinstance(node, ast.Global):
                line_no = node.lineno
                findings.append({
                    "file_path": rel_path,
                    "line_start": line_no,
                    "line_end": line_no,
                    "rule_id": "PY_GLOBAL_STATEMENT",
                    "category": "architecture",
                    "severity": "Medium",
                    "confidence": "High",
                    "title": f"Usage of global variable statement: {', '.join(node.names)}",
                    "explanation": f"Function modifies global variables ({', '.join(node.names)}) directly.",
                    "technical_evidence": f"Line {line_no}: global {', '.join(node.names)}",
                    "why_it_matters": "Global mutable state causes hidden coupling, race conditions in multi-threaded runtimes, and makes unit testing difficult.",
                    "recommended_remediation": "Pass state explicitly via arguments or encapsulate within a class instance.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

        return max_file_complexity, findings

    # =========================================================================
    # Generic Lexical & Structural Analysis (JS, TS, Java, Go, PHP, C#)
    # =========================================================================

    def _analyze_generic_code(self, rel_path: str, content: str, lines: List[str], lang: str) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        loc = len(lines)
        if loc > 800:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive file length ({loc} lines)",
                "explanation": f"Source file spans {loc} lines (recommended maximum: 800 lines).",
                "technical_evidence": f"Total LOC: {loc}",
                "why_it_matters": "Large source files exhibit low cohesion, high cognitive complexity, and higher defect rates.",
                "recommended_remediation": "Extract reusable components, service interfaces, or domain entities.",
                "estimated_remediation_hours": round(loc / 250, 1),
                "is_auto_verifiable": True
            })

        # Measure nesting depth and cyclomatic proxies
        max_nesting = 0
        current_nesting = 0
        deep_nesting_line = 0
        branch_count = 1

        branch_keywords = {
            "if", "else if", "elif", "case", "for", "while", "catch", "&&", "||", "switch"
        }

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Estimate nesting by brackets / indentation
            open_braces = line.count("{") - line.count("}")
            current_nesting = max(0, current_nesting + open_braces)
            if current_nesting > max_nesting:
                max_nesting = current_nesting
                deep_nesting_line = idx

            # Branch count proxy
            for kw in branch_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', stripped):
                    branch_count += 1

        if max_nesting >= 5:
            findings.append({
                "file_path": rel_path,
                "line_start": deep_nesting_line,
                "line_end": deep_nesting_line + 5,
                "rule_id": "EXCESSIVE_NESTING_DEPTH",
                "category": "complexity",
                "severity": "High" if max_nesting >= 7 else "Medium",
                "confidence": "High",
                "title": f"Excessive block nesting depth ({max_nesting} levels)",
                "explanation": f"Code reaches nesting depth of {max_nesting} levels at line {deep_nesting_line} (threshold: 4 levels).",
                "technical_evidence": f"Line {deep_nesting_line}: nesting level {max_nesting}",
                "why_it_matters": "Deep nesting ('arrow anti-pattern') impairs readability and indicates tightly-coupled control flow.",
                "recommended_remediation": "Apply early return guard clauses, invert conditionals, or decompose into helper routines.",
                "estimated_remediation_hours": 1.0,
                "is_auto_verifiable": True
            })

        # Language-specific anti-patterns
        if lang in ("javascript", "typescript"):
            # Check for console.log statements
            for idx, line in enumerate(lines, start=1):
                if re.search(r'\bconsole\.(?:log|debug|trace)\s*\(', line):
                    findings.append({
                        "file_path": rel_path,
                        "line_start": idx,
                        "line_end": idx,
                        "rule_id": "CONSOLE_LOG_PRODUCTION_LEAK",
                        "category": "maintainability",
                        "severity": "Low",
                        "confidence": "High",
                        "title": "Debug console statement in production code",
                        "explanation": "Direct console.log statements bypass structured logging and risk leaking sensitive runtime memory.",
                        "technical_evidence": line.strip()[:100],
                        "why_it_matters": "Pollutes stdout/browser console and may disclose internal data structures in production.",
                        "recommended_remediation": "Replace with dedicated enterprise logger or remove debug statements.",
                        "estimated_remediation_hours": 0.2,
                        "is_auto_verifiable": True
                    })
                    break  # Flag once per file to prevent spam

        return max(1, min(50, branch_count // 3)), findings

    # =========================================================================
    # Security Pattern Scanners
    # =========================================================================

    def _scan_security_patterns(self, rel_path: str, lines: List[str]) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []

        for idx, line in enumerate(lines, start=1):
            # Skip comments
            trimmed = line.strip()
            if trimmed.startswith(("#", "//", "/*", "*")):
                continue

            # Hardcoded secrets
            for pattern, rule_id, desc, sev in self.SECRET_PATTERNS:
                if pattern.search(line):
                    masked_evidence = re.sub(r'([\'\"][a-zA-Z0-9_\-\.\/+=]{4})[a-zA-Z0-9_\-\.\/+=]+([\'\"])', r'\1****\2', trimmed[:80])
                    findings.append({
                        "file_path": rel_path,
                        "line_start": idx,
                        "line_end": idx,
                        "rule_id": rule_id,
                        "category": "security",
                        "severity": sev,
                        "confidence": "Medium",
                        "title": "Potential hardcoded credential or secret detected",
                        "explanation": desc,
                        "technical_evidence": f"Line {idx}: {masked_evidence}",
                        "why_it_matters": "Hardcoded credentials in repositories can be extracted by unauthorized users or repository collaborators.",
                        "recommended_remediation": "Move credentials to secure environment variables and revoke compromised secrets.",
                        "estimated_remediation_hours": 1.0,
                        "is_auto_verifiable": False
                    })
                    break

            # Dangerous calls
            for pattern, rule_id, desc, sev in self.DANGEROUS_CALLS:
                if pattern.search(line):
                    findings.append({
                        "file_path": rel_path,
                        "line_start": idx,
                        "line_end": idx,
                        "rule_id": rule_id,
                        "category": "security",
                        "severity": sev,
                        "confidence": "High",
                        "title": desc,
                        "explanation": f"Potentially dangerous API invocation detected on line {idx}.",
                        "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                        "why_it_matters": "Unsanitized user inputs reaching this call can compromise host security.",
                        "recommended_remediation": "Refactor to use safe, parameterized standard library alternatives.",
                        "estimated_remediation_hours": 2.0,
                        "is_auto_verifiable": True
                    })
                    break

        return findings

    # =========================================================================
    # Code Duplication Detection
    # =========================================================================

    def _index_code_lines_for_duplication(self, rel_path: str, lines: List[str], line_hashes: Dict[str, List[Tuple[str, int]]]):
        block_size = 6
        if len(lines) < block_size:
            return

        for i in range(len(lines) - block_size + 1):
            block = [lines[i + j].strip() for j in range(block_size)]
            # Skip blocks that are mostly comments or trivial brackets
            if any(len(b) < 4 for b in block):
                continue
            if any(b.startswith(("#", "//", "/*", "*")) for b in block):
                continue

            block_text = "\n".join(block)
            b_hash = hashlib.md5(block_text.encode("utf-8")).hexdigest()
            line_hashes.setdefault(b_hash, []).append((rel_path, i + 1))

    def _detect_code_duplications(self, line_hashes: Dict[str, List[Tuple[str, int]]]) -> Tuple[List[Dict[str, Any]], int]:
        findings: List[Dict[str, Any]] = []
        duplicated_lines = set()
        reported_pairs: Set[Tuple[str, str]] = set()

        for b_hash, occurrences in line_hashes.items():
            if len(occurrences) > 1:
                # Group occurrences across different files or distinct sections
                unique_files = list({occ[0] for occ in occurrences})
                if len(unique_files) > 1:
                    f1, f2 = unique_files[0], unique_files[1]
                    pair_key = tuple(sorted([f1, f2]))
                    if pair_key not in reported_pairs:
                        reported_pairs.add(pair_key)
                        l1 = [o[1] for o in occurrences if o[0] == f1][0]
                        l2 = [o[1] for o in occurrences if o[0] == f2][0]

                        findings.append({
                            "file_path": f1,
                            "line_start": l1,
                            "line_end": l1 + 6,
                            "rule_id": "CROSS_FILE_CODE_DUPLICATION",
                            "category": "maintainability",
                            "severity": "Medium",
                            "confidence": "High",
                            "title": f"Duplicated code block identified across files",
                            "explanation": f"Identical 6+ line block duplicated in '{f1}' (line {l1}) and '{f2}' (line {l2}).",
                            "technical_evidence": f"Matching block SHA-256 hash: {b_hash[:12]} in {f1}:{l1} and {f2}:{l2}",
                            "why_it_matters": "Duplicated logic increases technical debt, requires double maintenance, and leads to divergent bug fixes.",
                            "recommended_remediation": "Extract shared logic into a common domain utility or service function.",
                            "estimated_remediation_hours": 1.5,
                            "is_auto_verifiable": True
                        })

                for f_rel, l_num in occurrences:
                    for offset in range(6):
                        duplicated_lines.add((f_rel, l_num + offset))

                if len(findings) >= 20:  # Cap duplication findings to prevent overwhelming report
                    break

        return findings, len(duplicated_lines)
