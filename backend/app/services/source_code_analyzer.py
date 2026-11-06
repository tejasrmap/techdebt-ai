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
        elif lang in ("javascript", "typescript"):
            comp, js_findings = self._analyze_javascript_typescript(file_path, content, lines, lang)
            complexity = max(complexity, comp)
            raw_findings.extend(js_findings)
        elif lang == "java":
            comp, java_findings = self._analyze_java(file_path, content, lines)
            complexity = max(complexity, comp)
            raw_findings.extend(java_findings)
        elif lang == "php":
            comp, php_findings = self._analyze_php(file_path, content, lines)
            complexity = max(complexity, comp)
            raw_findings.extend(php_findings)
        elif lang == "go":
            comp, go_findings = self._analyze_go(file_path, content, lines)
            complexity = max(complexity, comp)
            raw_findings.extend(go_findings)
        elif lang == "csharp":
            comp, cs_findings = self._analyze_csharp(file_path, content, lines)
            complexity = max(complexity, comp)
            raw_findings.extend(cs_findings)
        elif lang in ("c", "cpp"):
            comp, cpp_findings = self._analyze_c_cpp(file_path, content, lines, lang)
            complexity = max(complexity, comp)
            raw_findings.extend(cpp_findings)
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
            elif lang in ("javascript", "typescript"):
                comp, js_findings = self._analyze_javascript_typescript(rel_path, content, lines, lang)
                complexity = max(complexity, comp)
                file_findings.extend(js_findings)
            elif lang == "java":
                comp, java_findings = self._analyze_java(rel_path, content, lines)
                complexity = max(complexity, comp)
                file_findings.extend(java_findings)
            elif lang == "php":
                comp, php_findings = self._analyze_php(rel_path, content, lines)
                complexity = max(complexity, comp)
                file_findings.extend(php_findings)
            elif lang == "go":
                comp, go_findings = self._analyze_go(rel_path, content, lines)
                complexity = max(complexity, comp)
                file_findings.extend(go_findings)
            elif lang == "csharp":
                comp, cs_findings = self._analyze_csharp(rel_path, content, lines)
                complexity = max(complexity, comp)
                file_findings.extend(cs_findings)
            elif lang in ("c", "cpp"):
                comp, cpp_findings = self._analyze_c_cpp(rel_path, content, lines, lang)
                complexity = max(complexity, comp)
                file_findings.extend(cpp_findings)
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
    # JavaScript & TypeScript Analysis
    # =========================================================================

    def _analyze_javascript_typescript(self, rel_path: str, content: str, lines: List[str], lang: str) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        loc = len(lines)
        is_ts = lang == "typescript" or rel_path.endswith((".ts", ".tsx"))

        # 1. File Length
        if loc > 600:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive file length ({loc} lines)",
                "explanation": f"Source file spans {loc} lines (recommended maximum: 600 lines).",
                "technical_evidence": f"Total LOC: {loc}",
                "why_it_matters": "Monolithic files decrease comprehension and increase defect rates.",
                "recommended_remediation": "Decompose into reusable modules or custom hooks.",
                "estimated_remediation_hours": round(loc / 250, 1),
                "is_auto_verifiable": True
            })

        # 2. Bracket Nesting & Branch Counting
        max_nesting = 0
        current_nesting = 0
        deep_nesting_line = 0
        branch_count = 1
        branch_keywords = {"if", "else if", "case", "for", "while", "catch", "&&", "||", "switch"}

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()

            # Check compiler directives even within comments
            if is_ts and ("@ts-ignore" in trimmed or "@ts-nocheck" in trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "TS_IGNORE_DIRECTIVE",
                    "category": "maintainability",
                    "severity": "Low",
                    "confidence": "High",
                    "title": "Compiler type check suppression directive (@ts-ignore / @ts-nocheck)",
                    "explanation": "Suppression directives mask type errors without addressing underlying type mismatches.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Accumulating type suppression directives defeats TypeScript adoption benefits.",
                    "recommended_remediation": "Resolve underlying type incompatibility or use type narrowing.",
                    "estimated_remediation_hours": 0.25,
                    "is_auto_verifiable": True
                })

            # Skip pure comment lines for code syntax analysis
            if trimmed.startswith(("//", "/*", "*")):
                continue

            open_b = line.count("{") - line.count("}")
            current_nesting = max(0, current_nesting + open_b)
            if current_nesting > max_nesting:
                max_nesting = current_nesting
                deep_nesting_line = idx

            for kw in branch_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', trimmed):
                    branch_count += 1

            # 3. Loose Equality
            if re.search(r'(?<![!=<>])==(?![=])', trimmed) or re.search(r'(?<![!])!=(?![=])', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JS_LOOSE_EQUALITY",
                    "category": "reliability",
                    "severity": "Medium",
                    "confidence": "High",
                    "title": "Loose equality operator ('==' or '!=') detected",
                    "explanation": "Using loose equality invokes JavaScript type coercion, causing subtle equality bugs.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Type coercion in loose equality creates unexpected falsy/truthy matches and bugs.",
                    "recommended_remediation": "Use strict equality ('===' and '!==').",
                    "estimated_remediation_hours": 0.25,
                    "is_auto_verifiable": True
                })

            # 4. Dangerous DOM XSS
            if re.search(r'\b(?:innerHTML|outerHTML)\s*=|document\.write\s*\(|dangerouslySetInnerHTML', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JS_DANGEROUS_DOM_XSS",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "Dangerous unescaped DOM insertion (Cross-Site Scripting)",
                    "explanation": "Directly assigning innerHTML or using dangerouslySetInnerHTML can execute injected scripts.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "DOM-based XSS allows attackers to hijack user sessions and execute arbitrary scripts.",
                    "recommended_remediation": "Use textContent, safe React JSX interpolation, or sanitize with DOMPurify.",
                    "estimated_remediation_hours": 1.5,
                    "is_auto_verifiable": True
                })

            # 5. Dynamic Eval & Execution
            if re.search(r'\beval\s*\(|new\s+Function\s*\(|setTimeout\s*\(\s*[\'"`]|setInterval\s*\(\s*[\'"`]', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JS_DANGEROUS_EVAL",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "Dynamic code execution via eval() or new Function()",
                    "explanation": "Evaluating dynamic string code at runtime exposes the application to arbitrary code execution.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Bypasses Content Security Policy and gives untrusted inputs script execution privileges.",
                    "recommended_remediation": "Replace dynamic code execution with static function dispatch.",
                    "estimated_remediation_hours": 1.0,
                    "is_auto_verifiable": True
                })

            # 6. Prototype Pollution
            if "__proto__" in trimmed or "prototype[" in trimmed:
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JS_PROTOTYPE_POLLUTION",
                    "category": "security",
                    "severity": "High",
                    "confidence": "Medium",
                    "title": "Potential prototype pollution vulnerability",
                    "explanation": "Direct property assignment to '__proto__' or dynamic prototype modifies global Object prototypes.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Prototype pollution can alter object properties globally and enable privilege escalation.",
                    "recommended_remediation": "Freeze prototypes or use Map / Object.create(null) for keyed collections.",
                    "estimated_remediation_hours": 1.0,
                    "is_auto_verifiable": True
                })

            # 7. Empty Catch Block
            if re.search(r'catch\s*(?:\([^)]*\))?\s*\{\s*\}', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JS_EMPTY_CATCH_BLOCK",
                    "category": "reliability",
                    "severity": "Medium",
                    "confidence": "High",
                    "title": "Silent empty catch block swallows runtime errors",
                    "explanation": "Catch block with an empty body silently ignores exceptions.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Swallowed errors leave the application in an indeterminate state and conceal bugs.",
                    "recommended_remediation": "Log the error, rethrow, or present a user-facing error message.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

            # 8. TypeScript Specific Anti-Patterns
            if is_ts:
                # Explicit any
                if re.search(r':\s*any\b|\bas\s+any\b|<any>', trimmed):
                    findings.append({
                        "file_path": rel_path,
                        "line_start": idx,
                        "line_end": idx,
                        "rule_id": "TS_EXPLICIT_ANY",
                        "category": "maintainability",
                        "severity": "Medium",
                        "confidence": "High",
                        "title": "Explicit 'any' type annotation weakens type safety",
                        "explanation": "Using 'any' disables TypeScript compiler type verification and refactoring guarantees.",
                        "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                        "why_it_matters": "Removes static type protection and leads to unexpected runtime TypeError exceptions.",
                        "recommended_remediation": "Use specific domain interfaces, generics, or 'unknown' with type guards.",
                        "estimated_remediation_hours": 0.5,
                        "is_auto_verifiable": True
                    })

                # Non-null assertion
                if re.search(r'[a-zA-Z0-9_$]+!\.[a-zA-Z0-9_$]+', trimmed):
                    findings.append({
                        "file_path": rel_path,
                        "line_start": idx,
                        "line_end": idx,
                        "rule_id": "TS_NON_NULL_ASSERTION",
                        "category": "reliability",
                        "severity": "Low",
                        "confidence": "Medium",
                        "title": "Unsafe non-null assertion operator ('!.')",
                        "explanation": "Bypassing null checking with '!.' will crash if value is null or undefined at runtime.",
                        "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                        "why_it_matters": "Non-null assertions produce preventable Cannot read properties of undefined crashes.",
                        "recommended_remediation": "Use optional chaining ('?.') or explicit null check guard clauses.",
                        "estimated_remediation_hours": 0.25,
                        "is_auto_verifiable": True
                    })

        # Check deep nesting
        if max_nesting >= 5:
            findings.append({
                "file_path": rel_path,
                "line_start": deep_nesting_line,
                "line_end": deep_nesting_line,
                "rule_id": "JS_DEEP_NESTING",
                "category": "complexity",
                "severity": "High" if max_nesting >= 7 else "Medium",
                "confidence": "High",
                "title": f"Excessive block nesting depth ({max_nesting} levels)",
                "explanation": f"Code reaches nesting depth of {max_nesting} levels at line {deep_nesting_line} (threshold: 4 levels).",
                "technical_evidence": f"Line {deep_nesting_line}: nesting level {max_nesting}",
                "why_it_matters": "Deep block nesting ('callback/promise hell') causes high mental fatigue and logic defects.",
                "recommended_remediation": "Flatten control flow using early returns, async/await, or helper methods.",
                "estimated_remediation_hours": 1.0,
                "is_auto_verifiable": True
            })

        # Cyclomatic complexity score for JS/TS
        complexity_score = max(1, min(50, branch_count // 2))
        if complexity_score > 12:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "JS_HIGH_CYCLOMATIC_COMPLEXITY",
                "category": "complexity",
                "severity": "High" if complexity_score > 20 else "Medium",
                "confidence": "High",
                "title": f"High cyclomatic complexity ({complexity_score}) in module",
                "explanation": f"Module contains {branch_count} branch points resulting in cyclomatic complexity score of {complexity_score}.",
                "technical_evidence": f"{rel_path}: {branch_count} branch points detected",
                "why_it_matters": "Modules with excessive complexity require disproportionately high testing effort.",
                "recommended_remediation": "Extract complex branch trees into modular subroutines or state machines.",
                "estimated_remediation_hours": round(complexity_score * 0.2, 1),
                "is_auto_verifiable": True
            })

        return complexity_score, findings

    # =========================================================================
    # Java Source Analysis
    # =========================================================================

    def _analyze_java(self, rel_path: str, content: str, lines: List[str]) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        loc = len(lines)

        if loc > 600:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive Java class length ({loc} lines)",
                "explanation": f"Java class spans {loc} lines (recommended maximum: 600 lines).",
                "technical_evidence": f"Total LOC: {loc}",
                "why_it_matters": "Monolithic classes violate single-responsibility principle and complicate testing.",
                "recommended_remediation": "Decompose into cohesive domain services or delegate to helper classes.",
                "estimated_remediation_hours": round(loc / 250, 1),
                "is_auto_verifiable": True
            })

        max_nesting = 0
        current_nesting = 0
        deep_nesting_line = 0
        branch_count = 1
        branch_keywords = {"if", "else if", "case", "for", "while", "catch", "&&", "||", "switch"}

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()
            if trimmed.startswith(("//", "/*", "*")):
                continue

            open_b = line.count("{") - line.count("}")
            current_nesting = max(0, current_nesting + open_b)
            if current_nesting > max_nesting:
                max_nesting = current_nesting
                deep_nesting_line = idx

            for kw in branch_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', trimmed):
                    branch_count += 1

            # 1. Empty catch block
            if re.search(r'catch\s*\([^)]+\)\s*\{\s*\}', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JAVA_EMPTY_CATCH_BLOCK",
                    "category": "reliability",
                    "severity": "High",
                    "confidence": "High",
                    "title": "Empty catch block silently swallows Java exception",
                    "explanation": "Catch block with an empty body conceals thrown exceptions and prevents proper error handling.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Swallowed exceptions prevent error logging and leave applications in an inconsistent state.",
                    "recommended_remediation": "Log the exception with a logger (e.g. SLF4J) or rethrow as a domain exception.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

            # 2. Generic Exception Thrown
            if re.search(r'\bthrow\s+new\s+(?:Exception|Throwable)\s*\(', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JAVA_GENERIC_EXCEPTION_THROWN",
                    "category": "reliability",
                    "severity": "Medium",
                    "confidence": "High",
                    "title": "Generic Exception or Throwable thrown directly",
                    "explanation": "Throwing raw java.lang.Exception or java.lang.Throwable forces callers to catch overly broad exceptions.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Generic exceptions break precise exception handling and obscure failure modes.",
                    "recommended_remediation": "Throw specific checked or unchecked domain exceptions.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

            # 3. SQL string concatenation in JDBC queries
            if (re.search(r'\b(?:executeQuery|executeUpdate|execute)\s*\(\s*".*"\s*\+', trimmed) or
                re.search(r'".*\b(?:SELECT|INSERT|UPDATE|DELETE)\b.*"\s*\+', trimmed, re.IGNORECASE)):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JAVA_SQL_INJECTION_CONCAT",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "SQL query built via string concatenation (SQL injection risk)",
                    "explanation": "Concatenating strings into JDBC statements invites SQL injection attacks.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Allows unauthorized users to manipulate queries and access or modify database records.",
                    "recommended_remediation": "Use PreparedStatement with parameterized '?' placeholders.",
                    "estimated_remediation_hours": 1.5,
                    "is_auto_verifiable": True
                })

            # 4. System.exit call
            if re.search(r'\bSystem\.exit\s*\(', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JAVA_SYSTEM_EXIT",
                    "category": "reliability",
                    "severity": "High",
                    "confidence": "High",
                    "title": "Direct System.exit() invocation in application logic",
                    "explanation": "Calling System.exit() terminates the entire JVM runtime immediately.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Abruptly aborts server instances, servlet containers, and scheduled background workers.",
                    "recommended_remediation": "Throw an application exception or let the container handle shutdown cleanly.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

            # 5. Insecure java.util.Random for security
            if re.search(r'\bnew\s+Random\s*\(', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "JAVA_INSECURE_RANDOM",
                    "category": "security",
                    "severity": "Medium",
                    "confidence": "Medium",
                    "title": "Weak PRNG (java.util.Random) detected in application code",
                    "explanation": "java.util.Random uses a linear congruential generator which is cryptographically predictable.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Predictable random values allow attackers to predict sequential outputs and tokens.",
                    "recommended_remediation": "Use java.security.SecureRandom for cryptographic and token generation.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

        if max_nesting >= 5:
            findings.append({
                "file_path": rel_path,
                "line_start": deep_nesting_line,
                "line_end": deep_nesting_line,
                "rule_id": "JAVA_DEEP_NESTING",
                "category": "complexity",
                "severity": "High" if max_nesting >= 7 else "Medium",
                "confidence": "High",
                "title": f"Excessive block nesting depth ({max_nesting} levels)",
                "explanation": f"Java method reaches nesting depth of {max_nesting} levels (threshold: 4 levels).",
                "technical_evidence": f"Line {deep_nesting_line}: nesting level {max_nesting}",
                "why_it_matters": "Excessive nesting obscures logic flow and makes branching paths hard to test.",
                "recommended_remediation": "Extract inner loops or conditionals into dedicated helper methods.",
                "estimated_remediation_hours": 1.0,
                "is_auto_verifiable": True
            })

        complexity_score = max(1, min(50, branch_count // 2))
        return complexity_score, findings

    # =========================================================================
    # PHP Source Analysis
    # =========================================================================

    def _analyze_php(self, rel_path: str, content: str, lines: List[str]) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        loc = len(lines)

        if loc > 600:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive PHP script length ({loc} lines)",
                "explanation": f"PHP script spans {loc} lines (recommended maximum: 600 lines).",
                "technical_evidence": f"Total LOC: {loc}",
                "why_it_matters": "Monolithic PHP scripts result in poor maintainability and spaghetti code.",
                "recommended_remediation": "Adopt MVC structure or split into cohesive PSR-4 classes.",
                "estimated_remediation_hours": round(loc / 250, 1),
                "is_auto_verifiable": True
            })

        max_nesting = 0
        current_nesting = 0
        deep_nesting_line = 0
        branch_count = 1
        branch_keywords = {"if", "elseif", "case", "for", "foreach", "while", "catch", "&&", "||", "switch"}

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()
            if trimmed.startswith(("//", "#", "/*", "*")):
                continue

            open_b = line.count("{") - line.count("}")
            current_nesting = max(0, current_nesting + open_b)
            if current_nesting > max_nesting:
                max_nesting = current_nesting
                deep_nesting_line = idx

            for kw in branch_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', trimmed):
                    branch_count += 1

            # 1. Short open tags
            if trimmed.startswith("<?") and not trimmed.startswith("<?php") and not trimmed.startswith("<?="):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "PHP_SHORT_OPEN_TAG",
                    "category": "reliability",
                    "severity": "Medium",
                    "confidence": "High",
                    "title": "PHP short open tag ('<?') used",
                    "explanation": "Short open tags depend on server short_open_tag ini directive and fail on modern environments.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Disabling short_open_tag in php.ini causes source code to be rendered in plaintext to users.",
                    "recommended_remediation": "Always use full '<?php' tags.",
                    "estimated_remediation_hours": 0.2,
                    "is_auto_verifiable": True
                })

            # 2. Dangerous eval / create_function
            if re.search(r'\b(?:eval|create_function)\s*\(', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "PHP_DANGEROUS_EVAL",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "Dynamic code execution via eval() or create_function()",
                    "explanation": "eval() and deprecated create_function() execute dynamic PHP code at runtime.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Allows remote attackers to execute arbitrary server commands and take over the system.",
                    "recommended_remediation": "Refactor away from dynamic code execution to anonymous functions or closures.",
                    "estimated_remediation_hours": 1.5,
                    "is_auto_verifiable": True
                })

            # 3. Insecure unserialize
            if re.search(r'\bunserialize\s*\(', trimmed) and "allowed_classes" not in trimmed:
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "PHP_INSECURE_UNSERIALIZE",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "Insecure PHP object deserialization via unserialize()",
                    "explanation": "unserialize() on untrusted user input triggers magic methods (__destruct, __wakeup) enabling POP chains.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "PHP Object Injection can lead to arbitrary code execution, file writes, and SQL injection.",
                    "recommended_remediation": "Use json_decode() or specify ['allowed_classes' => false].",
                    "estimated_remediation_hours": 1.0,
                    "is_auto_verifiable": True
                })

            # 4. Raw superglobals in query/output
            if re.search(r'\$_(?:GET|POST|REQUEST)\[', trimmed) and any(w in trimmed.lower() for w in ["query", "execute", "echo ", "print ", "where "]):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "PHP_RAW_SUPERGLOBAL_USAGE",
                    "category": "security",
                    "severity": "High",
                    "confidence": "Medium",
                    "title": "Direct unvalidated superglobal ($_GET/$_POST) in query or output",
                    "explanation": "Accessing $_GET, $_POST, or $_REQUEST directly in query or output statements risks XSS and SQLi.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Unfiltered input from superglobals is a primary vector for injection vulnerabilities.",
                    "recommended_remediation": "Sanitize with filter_input() or use parameterized PDO statements and htmlspecialchars().",
                    "estimated_remediation_hours": 1.0,
                    "is_auto_verifiable": True
                })

            # 5. Empty catch block
            if re.search(r'catch\s*\([^)]+\)\s*\{\s*\}', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "PHP_EMPTY_CATCH_BLOCK",
                    "category": "reliability",
                    "severity": "Medium",
                    "confidence": "High",
                    "title": "Silent empty catch block swallows PHP exception",
                    "explanation": "Catch block with an empty body conceals thrown exceptions.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Swallowed exceptions leave the system in an unknown state and conceal errors.",
                    "recommended_remediation": "Log the error using error_log() or Monolog.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

        if max_nesting >= 5:
            findings.append({
                "file_path": rel_path,
                "line_start": deep_nesting_line,
                "line_end": deep_nesting_line,
                "rule_id": "PHP_DEEP_NESTING",
                "category": "complexity",
                "severity": "High" if max_nesting >= 7 else "Medium",
                "confidence": "High",
                "title": f"Excessive block nesting depth ({max_nesting} levels)",
                "explanation": f"PHP block reaches nesting depth of {max_nesting} levels (threshold: 4 levels).",
                "technical_evidence": f"Line {deep_nesting_line}: nesting level {max_nesting}",
                "why_it_matters": "Deep nesting makes PHP code difficult to follow and maintain.",
                "recommended_remediation": "Apply early return statements or extract logic into helper methods.",
                "estimated_remediation_hours": 1.0,
                "is_auto_verifiable": True
            })

        complexity_score = max(1, min(50, branch_count // 2))
        return complexity_score, findings

    # =========================================================================
    # Go Source Analysis
    # =========================================================================

    def _analyze_go(self, rel_path: str, content: str, lines: List[str]) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        loc = len(lines)
        if loc > 600:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive Go file length ({loc} lines)",
                "explanation": f"Go source file spans {loc} lines (recommended maximum: 600 lines).",
                "technical_evidence": f"Total LOC: {loc}",
                "why_it_matters": "Large Go packages violate idiom of small, focused source files.",
                "recommended_remediation": "Decompose into smaller source files within the package.",
                "estimated_remediation_hours": round(loc / 250, 1),
                "is_auto_verifiable": True
            })

        max_nesting = 0
        current_nesting = 0
        deep_nesting_line = 0
        branch_count = 1
        branch_keywords = {"if", "for", "select", "switch", "case", "&&", "||"}

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()
            if trimmed.startswith(("//", "/*", "*")):
                continue

            open_b = line.count("{") - line.count("}")
            current_nesting = max(0, current_nesting + open_b)
            if current_nesting > max_nesting:
                max_nesting = current_nesting
                deep_nesting_line = idx

            for kw in branch_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', trimmed):
                    branch_count += 1

            # 1. Ignored error return
            if re.search(r'_\s*,\s*_\s*:=', trimmed) or re.search(r'if\s+err\s*!=\s*nil\s*\{\s*\}', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "GO_UNHANDLED_ERROR",
                    "category": "reliability",
                    "severity": "High",
                    "confidence": "High",
                    "title": "Unhandled error or blank identifier used for error return in Go",
                    "explanation": "Ignoring error returns with blank identifiers or empty 'if err != nil {}' causes silent failures.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Go philosophy requires explicit error handling; discarding errors produces cascading runtime panics.",
                    "recommended_remediation": "Check and return the error or wrap with fmt.Errorf().",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

            # 2. Uncontrolled panic in library code
            if re.search(r'\bpanic\s*\(', trimmed) and not rel_path.endswith("_test.go"):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "GO_UNCONTROLLED_PANIC",
                    "category": "reliability",
                    "severity": "Medium",
                    "confidence": "High",
                    "title": "Direct panic() invocation in production code",
                    "explanation": "Calling panic() terminates goroutine execution abruptly instead of returning error.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Panics in libraries crash calling services unless caught by recover().",
                    "recommended_remediation": "Return an error value rather than panicking.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

            # 3. Unbounded goroutine
            if re.search(r'\bgo\s+func\s*\(', trimmed) and "ctx" not in trimmed and "done" not in trimmed:
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "GO_UNBOUNDED_GOROUTINE",
                    "category": "reliability",
                    "severity": "Medium",
                    "confidence": "Medium",
                    "title": "Anonymous goroutine launched without context cancellation or lifecycle management",
                    "explanation": "Launching goroutines without context or quit channels can leak memory and goroutines indefinitely.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Goroutine leaks consume OS threads and memory, eventually leading to process OOM.",
                    "recommended_remediation": "Pass a context.Context or use errgroup.Group for lifecycle control.",
                    "estimated_remediation_hours": 1.0,
                    "is_auto_verifiable": True
                })

            # 4. SQL concatenation in Go
            if (re.search(r'\b(?:Query|Exec|QueryRow)\s*\(\s*".*"\s*\+', trimmed) or
                re.search(r'fmt\.Sprintf\s*\(\s*".*\b(?:SELECT|INSERT|UPDATE|DELETE)\b', trimmed, re.IGNORECASE)):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "GO_SQL_INJECTION_CONCAT",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "SQL query built via string formatting or concatenation in Go",
                    "explanation": "Using string formatting (fmt.Sprintf) or '+' to construct SQL statements creates SQL injection vulnerabilities.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Enables attackers to manipulate SQL queries and exfiltrate database contents.",
                    "recommended_remediation": "Use parameterized queries ($1, ? placeholders) in database/sql calls.",
                    "estimated_remediation_hours": 1.5,
                    "is_auto_verifiable": True
                })

        if max_nesting >= 5:
            findings.append({
                "file_path": rel_path,
                "line_start": deep_nesting_line,
                "line_end": deep_nesting_line,
                "rule_id": "GO_DEEP_NESTING",
                "category": "complexity",
                "severity": "High" if max_nesting >= 7 else "Medium",
                "confidence": "High",
                "title": f"Excessive block nesting depth ({max_nesting} levels)",
                "explanation": f"Go code reaches nesting depth of {max_nesting} levels (threshold: 4 levels).",
                "technical_evidence": f"Line {deep_nesting_line}: nesting level {max_nesting}",
                "why_it_matters": "Idiomatic Go favors early returns ('line of sight') to keep nesting shallow.",
                "recommended_remediation": "Apply early error returns to eliminate deep nesting.",
                "estimated_remediation_hours": 1.0,
                "is_auto_verifiable": True
            })

        complexity_score = max(1, min(50, branch_count // 2))
        return complexity_score, findings

    # =========================================================================
    # C# (.NET) Source Analysis
    # =========================================================================

    def _analyze_csharp(self, rel_path: str, content: str, lines: List[str]) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        loc = len(lines)
        if loc > 600:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive C# file length ({loc} lines)",
                "explanation": f"C# source file spans {loc} lines (recommended maximum: 600 lines).",
                "technical_evidence": f"Total LOC: {loc}",
                "why_it_matters": "Large C# classes violate single-responsibility principle.",
                "recommended_remediation": "Extract responsibilities into cohesive services or interfaces.",
                "estimated_remediation_hours": round(loc / 250, 1),
                "is_auto_verifiable": True
            })

        max_nesting = 0
        current_nesting = 0
        deep_nesting_line = 0
        branch_count = 1
        branch_keywords = {"if", "else if", "case", "for", "foreach", "while", "catch", "&&", "||", "switch"}

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()
            if trimmed.startswith(("//", "/*", "*")):
                continue

            open_b = line.count("{") - line.count("}")
            current_nesting = max(0, current_nesting + open_b)
            if current_nesting > max_nesting:
                max_nesting = current_nesting
                deep_nesting_line = idx

            for kw in branch_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', trimmed):
                    branch_count += 1

            # 1. Empty catch block
            if re.search(r'catch\s*(?:\([^)]+\))?\s*\{\s*\}', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "CSHARP_EMPTY_CATCH_BLOCK",
                    "category": "reliability",
                    "severity": "High",
                    "confidence": "High",
                    "title": "Empty catch block silently swallows C# exception",
                    "explanation": "Catch block with an empty body conceals thrown exceptions.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Conceals operational failures and corrupts application state.",
                    "recommended_remediation": "Log the exception via ILogger or rethrow.",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

            # 2. Insecure BinaryFormatter deserialization
            if re.search(r'\bBinaryFormatter\b', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "CSHARP_INSECURE_BINARY_FORMATTER",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "Insecure deserialization with deprecated BinaryFormatter",
                    "explanation": "BinaryFormatter is dangerous and vulnerable to remote code execution attacks.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Microsoft strongly advises against using BinaryFormatter due to unavoidable RCE vulnerabilities.",
                    "recommended_remediation": "Migrate to System.Text.Json or protobuf-net.",
                    "estimated_remediation_hours": 2.0,
                    "is_auto_verifiable": True
                })

            # 3. SQL string interpolation
            if re.search(r'\bSqlCommand\s*\(.*\$".*\b(?:SELECT|INSERT|UPDATE|DELETE)\b', trimmed, re.IGNORECASE) or re.search(r'Execute(?:NonQuery|Reader|Scalar)\s*\(.*\$"', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "CSHARP_SQL_INJECTION",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "SQL query built via string interpolation ($) in C#",
                    "explanation": "Using string interpolation inside SqlCommand exposes the database to SQL injection attacks.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Allows unauthenticated users to execute arbitrary SQL commands.",
                    "recommended_remediation": "Use parameterized queries with SqlParameter or Dapper.",
                    "estimated_remediation_hours": 1.5,
                    "is_auto_verifiable": True
                })

            # 4. Thread.Abort / Suspend
            if re.search(r'\b[tT]hread\.(?:Abort|Suspend)\s*\(', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "CSHARP_DANGEROUS_THREAD_ABORT",
                    "category": "reliability",
                    "severity": "High",
                    "confidence": "High",
                    "title": "Dangerous Thread.Abort() or Thread.Suspend() invocation",
                    "explanation": "Thread.Abort forcefully kills a thread, corrupting shared state and leaking locks.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Deprecated in modern .NET; produces ThreadAbortException and deadlocks.",
                    "recommended_remediation": "Use cooperative cancellation tokens (CancellationToken).",
                    "estimated_remediation_hours": 1.0,
                    "is_auto_verifiable": True
                })

        if max_nesting >= 5:
            findings.append({
                "file_path": rel_path,
                "line_start": deep_nesting_line,
                "line_end": deep_nesting_line,
                "rule_id": "CSHARP_DEEP_NESTING",
                "category": "complexity",
                "severity": "High" if max_nesting >= 7 else "Medium",
                "confidence": "High",
                "title": f"Excessive block nesting depth ({max_nesting} levels)",
                "explanation": f"C# method reaches nesting depth of {max_nesting} levels (threshold: 4 levels).",
                "technical_evidence": f"Line {deep_nesting_line}: nesting level {max_nesting}",
                "why_it_matters": "Deep nesting makes logic hard to understand and test.",
                "recommended_remediation": "Use early returns or local functions to flatten execution paths.",
                "estimated_remediation_hours": 1.0,
                "is_auto_verifiable": True
            })

        complexity_score = max(1, min(50, branch_count // 2))
        return complexity_score, findings

    # =========================================================================
    # C and C++ Source Analysis
    # =========================================================================

    def _analyze_c_cpp(self, rel_path: str, content: str, lines: List[str], lang: str) -> Tuple[int, List[Dict[str, Any]]]:
        findings: List[Dict[str, Any]] = []
        loc = len(lines)
        if loc > 600:
            findings.append({
                "file_path": rel_path,
                "line_start": 1,
                "line_end": loc,
                "rule_id": "FILE_EXCESSIVE_LENGTH",
                "category": "maintainability",
                "severity": "Medium",
                "confidence": "High",
                "title": f"Excessive C/C++ file length ({loc} lines)",
                "explanation": f"C/C++ file spans {loc} lines (recommended maximum: 600 lines).",
                "technical_evidence": f"Total LOC: {loc}",
                "why_it_matters": "Monolithic translation units degrade compile times and readability.",
                "recommended_remediation": "Split into cohesive compilation units.",
                "estimated_remediation_hours": round(loc / 250, 1),
                "is_auto_verifiable": True
            })

        max_nesting = 0
        current_nesting = 0
        deep_nesting_line = 0
        branch_count = 1
        branch_keywords = {"if", "else if", "case", "for", "while", "catch", "&&", "||", "switch"}

        for idx, line in enumerate(lines, start=1):
            trimmed = line.strip()
            if trimmed.startswith(("//", "/*", "*")):
                continue

            open_b = line.count("{") - line.count("}")
            current_nesting = max(0, current_nesting + open_b)
            if current_nesting > max_nesting:
                max_nesting = current_nesting
                deep_nesting_line = idx

            for kw in branch_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', trimmed):
                    branch_count += 1

            # 1. Unsafe buffer functions
            unsafe_match = re.search(r'\b(strcpy|strcat|gets|sprintf|vsprintf)\s*\(', trimmed)
            if unsafe_match:
                fn_name = unsafe_match.group(1)
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "CPP_UNSAFE_BUFFER_FUNCTION",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": f"Dangerous buffer manipulation function '{fn_name}()' (Buffer overflow risk)",
                    "explanation": f"Function '{fn_name}()' does not perform boundary checking on buffer destination.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Buffer overflows in C/C++ allow remote code execution and memory corruption.",
                    "recommended_remediation": f"Replace with bounded alternatives (e.g. strncpy, snprintf, or std::string).",
                    "estimated_remediation_hours": 1.5,
                    "is_auto_verifiable": True
                })

            # 2. Format string vulnerability
            if re.search(r'\b(?:printf|fprintf|syslog)\s*\(\s*[a-zA-Z0-9_]+\s*\)', trimmed):
                findings.append({
                    "file_path": rel_path,
                    "line_start": idx,
                    "line_end": idx,
                    "rule_id": "CPP_FORMAT_STRING_VULN",
                    "category": "security",
                    "severity": "Critical",
                    "confidence": "High",
                    "title": "Potential format string vulnerability",
                    "explanation": "Passing variable as format string argument without '%s' specifier allows attackers to read or write arbitrary stack memory.",
                    "technical_evidence": f"Line {idx}: {trimmed[:80]}",
                    "why_it_matters": "Attackers can use %n and %x specifiers to execute arbitrary code or leak memory.",
                    "recommended_remediation": "Use literal format string, e.g. printf(\"%s\", buf).",
                    "estimated_remediation_hours": 0.5,
                    "is_auto_verifiable": True
                })

        if max_nesting >= 5:
            findings.append({
                "file_path": rel_path,
                "line_start": deep_nesting_line,
                "line_end": deep_nesting_line,
                "rule_id": "CPP_DEEP_NESTING",
                "category": "complexity",
                "severity": "High" if max_nesting >= 7 else "Medium",
                "confidence": "High",
                "title": f"Excessive block nesting depth ({max_nesting} levels)",
                "explanation": f"C/C++ block reaches nesting depth of {max_nesting} levels (threshold: 4 levels).",
                "technical_evidence": f"Line {deep_nesting_line}: nesting level {max_nesting}",
                "why_it_matters": "Excessive nesting obscures control flow and complicates verification.",
                "recommended_remediation": "Refactor complex conditional branches into helper functions.",
                "estimated_remediation_hours": 1.0,
                "is_auto_verifiable": True
            })

        complexity_score = max(1, min(50, branch_count // 2))
        return complexity_score, findings

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
