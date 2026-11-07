"""
TechDebt AI v3.1.0 — Architecture Intelligence Engine.

Performs source-derived dependency graph extraction, Tarjan SCC circular dependency detection,
fan-in/fan-out coupling analysis, architecture layering violation checks, and cloud-native readiness.
"""

import os
import re
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class AntiPatternFinding:
    rule_id: str
    title: str
    severity: str  # Critical, High, Medium, Low
    file_path: str
    description: str
    remediation: str


class ArchitectureReviewEngine:
    """
    Production-grade software architecture intelligence engine.
    Extracts module dependency graphs across Python, JavaScript, TypeScript, Go, Java, PHP, and C/C++.
    Applies Tarjan's SCC algorithm for cycle detection, computes fan-in/fan-out coupling and instability,
    and identifies structural anti-patterns.
    """

    ARCH_LAYERS = {
        "presentation": re.compile(r"(api|router|route|controller|endpoint|views?|handler)", re.IGNORECASE),
        "application": re.compile(r"(service|workflow|orchestrat|use_case|interactor)", re.IGNORECASE),
        "domain": re.compile(r"(domain|model|entity|schema|dto|aggregate)", re.IGNORECASE),
        "infrastructure": re.compile(r"(infra|db|database|repository|adapter|client|cache|storage|mq|queue)", re.IGNORECASE),
    }

    @classmethod
    def classify_layer(cls, file_path: str) -> str:
        """Categorizes a file into Clean Architecture tiers based on naming and path conventions."""
        norm_path = file_path.replace("\\", "/")
        for layer_name, pattern in cls.ARCH_LAYERS.items():
            if pattern.search(norm_path):
                return layer_name
        return "common"

    @classmethod
    def extract_imports_from_source(cls, source_code: str, file_path: str) -> List[str]:
        """
        Extracts imported module identifiers or relative file references from source code.
        Supports Python, JS/TS, Go, Java, PHP, and C/C++.
        """
        imported_modules = []
        if not source_code:
            return imported_modules

        norm_path = file_path.replace("\\", "/").lower()

        # Python
        if norm_path.endswith(".py"):
            # from x.y import z
            for match in re.finditer(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import", source_code, re.MULTILINE):
                imported_modules.append(match.group(1))
            # import x
            for match in re.finditer(r"^\s*import\s+([a-zA-Z0-9_\.]+)", source_code, re.MULTILINE):
                imported_modules.append(match.group(1))

        # JavaScript / TypeScript
        elif any(norm_path.endswith(ext) for ext in (".js", ".jsx", ".ts", ".tsx", ".mjs")):
            for match in re.finditer(r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\))""", source_code):
                mod = match.group(1) or match.group(2)
                if mod:
                    imported_modules.append(mod)

        # Go
        elif norm_path.endswith(".go"):
            for match in re.finditer(r'import\s+\(\s*([^)]+)\s*\)', source_code):
                block = match.group(1)
                for line in block.splitlines():
                    sub = re.findall(r'"([^"]+)"', line)
                    imported_modules.extend(sub)
            for match in re.finditer(r'import\s+"([^"]+)"', source_code):
                imported_modules.append(match.group(1))

        # Java
        elif norm_path.endswith(".java"):
            for match in re.finditer(r"^\s*import\s+([a-zA-Z0-9_\.]+);", source_code, re.MULTILINE):
                imported_modules.append(match.group(1))

        # PHP
        elif norm_path.endswith(".php"):
            for match in re.finditer(r"^\s*use\s+([a-zA-Z0-9_\\]+);", source_code, re.MULTILINE):
                imported_modules.append(match.group(1))

        # C / C++
        elif any(norm_path.endswith(ext) for ext in (".c", ".cpp", ".cc", ".h", ".hpp")):
            for match in re.finditer(r'#include\s+["<]([^">]+)[">]', source_code):
                imported_modules.append(match.group(1))

        return list(set(imported_modules))

    @classmethod
    def build_dependency_graph(
        cls,
        files: List[str],
        file_contents: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Constructs directed module dependency graph, computes fan-in, fan-out,
        instability metrics, and detects circular dependency cycles.
        """
        file_contents = file_contents or {}
        nodes: Dict[str, Dict[str, Any]] = {}
        adjacency: Dict[str, Set[str]] = {}
        reverse_adjacency: Dict[str, Set[str]] = {}

        # Normalize file keys
        normalized_files = [f.replace("\\", "/") for f in files]
        for f in normalized_files:
            nodes[f] = {
                "id": f,
                "name": os.path.basename(f),
                "layer": cls.classify_layer(f),
                "fan_in": 0,
                "fan_out": 0,
                "instability": 0.0,
                "in_cycle": False
            }
            adjacency[f] = set()
            reverse_adjacency[f] = set()

        # Build edges from content or heuristic path references
        edges = []
        for f in normalized_files:
            content = file_contents.get(f) or file_contents.get(f.replace("/", "\\")) or ""
            imported_raw = cls.extract_imports_from_source(content, f)

            # Match imported symbols to existing files
            for imp in imported_raw:
                imp_clean = imp.replace(".", "/").replace("\\", "/")
                target_matched = None
                for candidate in normalized_files:
                    if candidate == f:
                        continue
                    # Check direct or partial suffix match
                    cand_no_ext = os.path.splitext(candidate)[0]
                    if cand_no_ext.endswith(imp_clean) or imp_clean.endswith(cand_no_ext) or os.path.basename(cand_no_ext) == os.path.basename(imp_clean):
                        target_matched = candidate
                        break

                if target_matched and target_matched != f:
                    if target_matched not in adjacency[f]:
                        adjacency[f].add(target_matched)
                        reverse_adjacency[target_matched].add(f)
                        edges.append({
                            "source": f,
                            "target": target_matched,
                            "imported_symbol": imp
                        })

        # Calculate Fan-in (Ca), Fan-out (Ce), and Instability (Ce / (Ca + Ce))
        for f in normalized_files:
            fan_out = len(adjacency[f])
            fan_in = len(reverse_adjacency[f])
            instability = round(fan_out / (fan_in + fan_out), 2) if (fan_in + fan_out) > 0 else 0.5
            nodes[f]["fan_in"] = fan_in
            nodes[f]["fan_out"] = fan_out
            nodes[f]["instability"] = instability

        # Detect circular dependencies using Tarjan's Strongly Connected Components (SCC)
        cycles = cls._find_tarjan_cycles(normalized_files, adjacency)
        for cycle in cycles:
            for node_id in cycle:
                if node_id in nodes:
                    nodes[node_id]["in_cycle"] = True

        # Detect layer violations (e.g. Domain -> Presentation, Infrastructure -> Presentation)
        layer_violations = []
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            src_layer = nodes[src]["layer"]
            tgt_layer = nodes[tgt]["layer"]

            # Domain layer should not depend on presentation or infrastructure
            if src_layer == "domain" and tgt_layer in ("presentation", "infrastructure"):
                layer_violations.append({
                    "source": src,
                    "target": tgt,
                    "source_layer": src_layer,
                    "target_layer": tgt_layer,
                    "rule": "Domain invariants must not depend on outward Presentation or Infrastructure layers."
                })
            # Infrastructure layer should not depend directly on presentation
            elif src_layer == "infrastructure" and tgt_layer == "presentation":
                layer_violations.append({
                    "source": src,
                    "target": tgt,
                    "source_layer": src_layer,
                    "target_layer": tgt_layer,
                    "rule": "Infrastructure components must not couple back to HTTP presentation routes."
                })

        return {
            "total_modules": len(nodes),
            "total_dependencies": len(edges),
            "nodes": list(nodes.values()),
            "edges": edges,
            "circular_dependencies": [
                {
                    "cycle": cycle,
                    "cycle_length": len(cycle),
                    "severity": "High" if len(cycle) <= 3 else "Critical",
                    "description": f"Circular import chain detected across {len(cycle)} modules: {' -> '.join(os.path.basename(c) for c in cycle)}"
                }
                for cycle in cycles
            ],
            "layer_violations": layer_violations,
            "instability_hotspots": sorted(
                [n for n in nodes.values() if n["fan_in"] > 3 and n["instability"] > 0.6],
                key=lambda x: x["fan_in"],
                reverse=True
            )
        }

    @classmethod
    def _find_tarjan_cycles(cls, file_list: List[str], adj: Dict[str, Set[str]]) -> List[List[str]]:
        """Tarjan's algorithm to identify strongly connected components with size >= 2."""
        index = 0
        indices: Dict[str, int] = {}
        lowlinks: Dict[str, int] = {}
        on_stack: Dict[str, bool] = {}
        stack: List[str] = []
        sccs: List[List[str]] = []

        def strongconnect(v: str):
            nonlocal index
            indices[v] = index
            lowlinks[v] = index
            index += 1
            stack.append(v)
            on_stack[v] = True

            for w in adj.get(v, set()):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif on_stack.get(w, False):
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == v:
                        break
                # Only report components with cycle length >= 2
                if len(scc) > 1:
                    sccs.append(scc)

        for u in file_list:
            if u not in indices:
                strongconnect(u)

        return sccs

    @classmethod
    def analyze_architecture(
        cls,
        files: List[str],
        code_findings: Optional[List[Dict[str, Any]]] = None,
        code_metrics: Optional[Dict[str, Any]] = None,
        technologies: Optional[List[Dict[str, Any]]] = None,
        file_contents: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete architectural evaluation:
        - Dependency graph generation
        - Tarjan cycle identification
        - Layering boundary analysis
        - 12-Factor App cloud readiness
        - Modernization action plan
        """
        code_findings = code_findings or []
        code_metrics = code_metrics or {}
        technologies = technologies or []
        files = files or []

        anti_patterns: List[AntiPatternFinding] = []

        # 1. Dependency Graph & Coupling Analysis
        graph_data = cls.build_dependency_graph(files, file_contents)

        # Flag detected circular cycles as High/Critical anti-patterns
        for cd in graph_data["circular_dependencies"]:
            cycle_nodes = cd["cycle"]
            anti_patterns.append(AntiPatternFinding(
                rule_id="CIRCULAR_DEPENDENCY_CYCLE",
                title=f"Circular Module Cycle ({len(cycle_nodes)} modules)",
                severity=cd["severity"],
                file_path=cycle_nodes[0] if cycle_nodes else "unknown",
                description=cd["description"],
                remediation="Decouple circular reference via dependency inversion (interfaces) or by extracting shared definitions into a standalone common module."
            ))

        # Flag layer boundary violations
        for lv in graph_data["layer_violations"]:
            anti_patterns.append(AntiPatternFinding(
                rule_id="ARCHITECTURE_LAYER_VIOLATION",
                title=f"Clean Architecture Layer Violation ({lv['source_layer']} -> {lv['target_layer']})",
                severity="High",
                file_path=lv["source"],
                description=f"Module '{lv['source']}' depends directly on '{lv['target']}'. {lv['rule']}",
                remediation="Invert the dependency using an abstract interface or move common logic into an application/domain boundary."
            ))

        # 2. Inspect God Objects / Monolithic Bloat using SourceCodeAnalyzer findings
        god_object_rules = (
            "LARGE_CLASS_GOD_OBJECT",
            "EXCESSIVE_METHOD_LENGTH",
            "HIGH_CYCLOMATIC_COMPLEXITY",
            "CROSS_FILE_CODE_DUPLICATION"
        )
        for f in code_findings:
            if f.get("rule_id") in god_object_rules:
                anti_patterns.append(AntiPatternFinding(
                    rule_id="GOD_MODULE_BLOAT",
                    title=f"Monolithic Component / God Module ({f.get('rule_id', '')})",
                    severity="High" if f.get("severity") in ("High", "Critical") else "Medium",
                    file_path=f.get("file_path", "unknown"),
                    description=f"File exceeds structural complexity thresholds ({f.get('title')}), violating the Single Responsibility Principle.",
                    remediation="Extract cohesive business subdomains into isolated service classes or micro-packages."
                ))

        # 3. Inspect Separation of Concerns in Directory Hierarchy
        has_api_or_controllers = any(re.search(r"(api|router|route|controller|endpoint|views?)", f, re.IGNORECASE) for f in files)
        has_services_or_domain = any(re.search(r"(service|domain|core|business)", f, re.IGNORECASE) for f in files)
        has_models_or_entities = any(re.search(r"(model|entity|schema|dto)", f, re.IGNORECASE) for f in files)

        layering_penalties = 0.0
        if len(files) >= 5 and not (has_api_or_controllers and has_services_or_domain and has_models_or_entities):
            layering_penalties += 20.0
            anti_patterns.append(AntiPatternFinding(
                rule_id="LACK_OF_TIERED_ABSTRACTION",
                title="Missing Layered Architecture Boundaries",
                severity="High",
                file_path="root/",
                description="Project lacks clear separation between presentation (API), business domain (Service), and persistence (Data).",
                remediation="Adopt a 3-tier Layered or Hexagonal architecture separating routes, domain logic, and repositories."
            ))

        # 4. 12-Factor App Cloud-Native Readiness
        # Factor III: Config in environment
        config_violations = [f for f in code_findings if f.get("rule_id") == "HARDCODED_SECRET_OR_KEY" or "hardcoded" in f.get("title", "").lower()]
        tf_config_penalty = len(config_violations) * 12.0

        # Factor VI: Stateless processes
        state_violations = [f for f in code_findings if f.get("rule_id") == "MUTABLE_GLOBAL_STATE"]
        tf_state_penalty = len(state_violations) * 10.0

        # Factor XI: Logs as event streams / raw print calls
        print_findings = [f for f in code_findings if "print(" in f.get("title", "").lower()]
        tf_log_penalty = len(print_findings) * 5.0

        twelve_factor_score = max(20.0, min(100.0, 100.0 - (tf_config_penalty + tf_state_penalty + tf_log_penalty)))

        # 5. Pattern Compliance Score
        ap_penalty = sum(15.0 if ap.severity == "Critical" else 10.0 if ap.severity == "High" else 5.0 for ap in anti_patterns)
        pattern_score = max(20.0, min(100.0, 100.0 - ap_penalty - layering_penalties))

        # 6. Target Architecture Blueprint
        target_blueprint = {
            "style": "Clean Architecture / Hexagonal Service-Repository",
            "layers": [
                {
                    "layer": "Presentation / Interface Layer",
                    "components": ["FastAPI Routers", "Request Validation DTOs", "HTTP Error Mappers"],
                    "rule": "Handles serialization and HTTP protocols. Never contains domain business logic or direct database queries."
                },
                {
                    "layer": "Application / Service Layer",
                    "components": ["Business Services", "Workflow Orchestrators", "Event Handlers"],
                    "rule": "Enforces domain rules, authorization logic, and coordinates data access."
                },
                {
                    "layer": "Domain Model Layer",
                    "components": ["Domain Entities", "Value Objects", "Invariants"],
                    "rule": "Pure business entities independent of frameworks and persistence tools."
                },
                {
                    "layer": "Infrastructure / Persistence Layer",
                    "components": ["SQLAlchemy ORM Models", "External API Clients", "Cache Adapters"],
                    "rule": "Implements repository interfaces for database, network, and disk I/O."
                }
            ]
        }

        # 7. Modernization Migration Plan
        migration_plan = [
            {
                "phase": "Phase 1: Boundary Isolation & Cycle Resolution (Sprint 1-2)",
                "goal": "Break circular import cycles and decouple presentation routes from database queries.",
                "tasks": [
                    "Resolve identified circular dependency chains by applying Dependency Inversion." if graph_data["circular_dependencies"] else "Maintain clean acyclic module dependency structure.",
                    "Extract SQL operations out of API endpoints into dedicated Service classes.",
                    "Audit codebase for hardcoded configs and migrate to environment variables."
                ]
            },
            {
                "phase": "Phase 2: Hotspot Deconstruction (Sprint 3-4)",
                "goal": "Break apart monolithic God modules and reduce cyclomatic complexity.",
                "tasks": [
                    f"Refactor identified God modules: {[ap.file_path for ap in anti_patterns if ap.rule_id == 'GOD_MODULE_BLOAT'][:3]}.",
                    "Replace deeply nested branching with early-exit guard clauses.",
                    "Extract duplicated cross-module code into reusable internal domain libraries."
                ]
            },
            {
                "phase": "Phase 3: Resiliency & Cloud-Native Hardening (Sprint 5-6)",
                "goal": "Achieve 12-Factor App compliance and automated regression safety.",
                "tasks": [
                    "Configure structured JSON logging to stdout for centralized observability.",
                    "Implement graceful termination handlers for SIGTERM in worker processes.",
                    "Expand automated test coverage around core domain interfaces to >= 80%."
                ]
            }
        ]

        return {
            "pattern_compliance_score": round(pattern_score, 1),
            "twelve_factor_readiness_score": round(twelve_factor_score, 1),
            "architecture_grade": "A" if pattern_score >= 85 else "B" if pattern_score >= 70 else "C" if pattern_score >= 50 else "D",
            "anti_patterns_count": len(anti_patterns),
            "anti_patterns": [
                {
                    "rule_id": ap.rule_id,
                    "title": ap.title,
                    "severity": ap.severity,
                    "file_path": ap.file_path,
                    "description": ap.description,
                    "remediation": ap.remediation
                }
                for ap in anti_patterns
            ],
            "dependency_graph": graph_data,
            "target_architecture_blueprint": target_blueprint,
            "migration_plan": migration_plan,
            "coverage_notes": f"Graph synthesized from {len(files)} repository module path(s) and {graph_data['total_dependencies']} directed dependency relationship(s)." if files else "No source files registered for architecture graph synthesis."
        }
