import os
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.services.modular_ai_engine import ModularAIEngine, modular_ai_engine
from app.services.prompt_defense_service import PromptDefenseService

logger = logging.getLogger(__name__)

class RefactoringRecipeSchema(BaseModel):
    target_file: str
    primary_issue: str
    strategy: str
    step_by_step: List[str]
    finding_ids: Optional[List[str]] = Field(default_factory=list)
    expected_impact: Optional[str] = None

class ModernizationRoadmapSchema(BaseModel):
    immediate_30_days: List[str]
    medium_term_60_days: List[str]
    long_term_90_days: List[str]

class RecommendationsSchema(BaseModel):
    executive_summary: str
    architecture_overview: str
    refactoring_recipes: List[RefactoringRecipeSchema]
    modernization_roadmap: ModernizationRoadmapSchema
    grounding_finding_ids: Optional[List[str]] = Field(default_factory=list)

class AIEngineeringAssistant:
    """
    Commercial AI Engineering Assistant for TechDebt AI v3.1.0.
    Produces evidence-grounded architectural explanations, refactoring strategies,
    30/60/90-day modernization roadmaps, and executive summaries with strict schema validation
    and finding traceability.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        engine: Optional[ModularAIEngine] = None
    ):
        self.gemini_key = (gemini_api_key or settings.GEMINI_API_KEY or "").strip()
        self.openai_key = (openai_api_key or settings.OPENAI_API_KEY or "").strip()
        self.model_name = model_name or settings.AI_MODEL_NAME
        self.engine = engine or ModularAIEngine(
            gemini_api_key=self.gemini_key,
            openai_api_key=self.openai_key,
            default_model=self.model_name
        )

    async def generate_engineering_recommendations(
        self,
        project_name: str,
        overall_score: float,
        risk_classification: str,
        hotspots: List[Dict[str, Any]],
        code_findings: List[Dict[str, Any]],
        dependencies: List[Dict[str, Any]],
        total_remediation_hours: float
    ) -> Dict[str, Any]:
        """
        Generates actionable technical debt remediation package grounded in actual repository findings.
        """
        if self.gemini_key or self.openai_key:
            try:
                llm_response = await self._call_llm_assistant(
                    project_name, overall_score, risk_classification, hotspots, code_findings, dependencies, total_remediation_hours
                )
                if llm_response:
                    return llm_response
            except Exception as e:
                logger.warning(f"LLM API request encountered exception: {e}; utilizing deterministic assistant.")

        return self._generate_deterministic_recommendations(
            project_name, overall_score, risk_classification, hotspots, code_findings, dependencies, total_remediation_hours
        )

    def _generate_deterministic_recommendations(
        self,
        project_name: str,
        overall_score: float,
        risk_classification: str,
        hotspots: List[Dict[str, Any]],
        code_findings: List[Dict[str, Any]],
        dependencies: List[Dict[str, Any]],
        total_remediation_hours: float
    ) -> Dict[str, Any]:
        """
        Deterministic, zero-hallucination engineering recommendations grounded strictly in findings.
        """
        # 1. Executive Summary
        exec_summary = (
            f"Repository '{project_name}' has an evaluated composite health score of {overall_score}/100 "
            f"({risk_classification}). The static source analysis and dependency inspection identified "
            f"{len(code_findings)} code finding(s) and {len(dependencies)} package dependencies, requiring "
            f"an estimated {total_remediation_hours} engineering hours to remediate critical architectural and security debt."
        )

        # 2. Top Refactoring Recipes
        refactoring_recipes = []
        for hs in hotspots[:5]:
            file_path = hs.get("file_path", "")
            comp = hs.get("complexity", 1)
            loc = hs.get("loc", 0)
            recipes_for_file = [
                f for f in code_findings if f.get("file_path") == file_path
            ]
            primary_issue = recipes_for_file[0]["title"] if recipes_for_file else f"High cyclomatic complexity ({comp})"

            refactoring_recipes.append({
                "target_file": file_path,
                "complexity": comp,
                "lines_of_code": loc,
                "primary_issue": primary_issue,
                "strategy": "Extract Subroutines and Apply Guard Clauses",
                "step_by_step": [
                    f"Analyze control flow branches inside '{file_path}'.",
                    "Replace deeply nested if-else ladders with early-return guard clauses.",
                    "Extract distinct business logic blocks into standalone utility modules or helper classes.",
                    "Introduce comprehensive unit tests before splitting monolithic methods."
                ],
                "expected_impact": f"Reduces cyclomatic complexity by up to 50% and improves testability."
            })

        # 3. 30 / 60 / 90 Day Modernization Roadmap
        roadmap = {
            "immediate_30_days": [
                "Triage and resolve all Critical severity security findings and potential hardcoded credentials.",
                "Upgrade end-of-life and critical vulnerability dependencies discovered in manifests.",
                "Establish automated pre-commit hooks to prevent adding methods with cyclomatic complexity > 15."
            ],
            "medium_term_60_days": [
                f"Refactor top 3 technical debt hotspots: {', '.join(h['file_path'] for h in hotspots[:3]) if hotspots else 'core modules'}.",
                "Eliminate cross-file duplicated code blocks by extracting shared domain packages.",
                "Increase unit test file density towards the recommended 25% ratio."
            ],
            "long_term_90_days": [
                "Modernize major semantic framework versions across outdated dependencies.",
                "Implement strict boundary layers between domain logic and external infrastructure.",
                "Schedule recurring automated weekly reviews to prevent future technical debt regression."
            ]
        }

        known_finding_ids = [str(f.get("id")) for f in code_findings if f.get("id")]

        return {
            "origin": "rule_based",
            "provider": "deterministic",
            "model": "deterministic-engine-v3",
            "finding_traceability": known_finding_ids[:5],
            "cost_usd": 0.0,
            "executive_summary": exec_summary,
            "architecture_overview": (
                f"Multi-tiered architecture evaluating {len(dependencies)} dependencies across "
                f"{len(hotspots)} active modules with primary language footprint in "
                f"{hotspots[0].get('language', 'supported ecosystems') if hotspots else 'supported ecosystems'}."
            ),
            "refactoring_recipes": refactoring_recipes,
            "modernization_roadmap": roadmap,
            "estimated_remediation_hours": total_remediation_hours
        }

    async def chat(
        self,
        project_name: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        telemetry: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Multi-turn conversational assistant grounded in actual project telemetry.
        Defends against prompt injection and provides actionable architectural advice.
        """
        conversation_history = conversation_history or []
        telemetry = telemetry or {}

        # 1. Inspect user message for prompt injection
        inspection = PromptDefenseService.inspect_input(user_message, mode="SANITIZE")
        clean_user_message = inspection["sanitized_text"]

        # 2. Build grounded telemetry context
        score = telemetry.get("health_score", 80.0)
        risk_class = telemetry.get("risk_classification", "Good")
        findings = telemetry.get("findings", [])
        hotspots = telemetry.get("hotspots", [])
        dependencies = telemetry.get("dependencies", [])

        grounding_evidence = [
            f"Project: {project_name}",
            f"Health Score: {score}/100 ({risk_class})",
            f"Active Findings: {len(findings)}",
            f"Tracked Dependencies: {len(dependencies)}"
        ]
        if hotspots:
            grounding_evidence.append(f"Top Hotspot: {hotspots[0].get('file_path', 'unknown')}")

        # Wrap telemetry inside cryptographic fence
        telemetry_raw = json.dumps({
            "project_name": project_name,
            "health_score": score,
            "risk_classification": risk_class,
            "top_findings": findings[:5],
            "hotspots": hotspots[:3],
            "sample_dependencies": dependencies[:5]
        })
        fenced_telemetry, _ = PromptDefenseService.wrap_untrusted_input(telemetry_raw, label="codebase_telemetry")

        system_prompt = (
            "You are TechDebt AI's Principal Engineering Assistant. "
            "You provide senior architectural guidance, refactoring plans, and technical debt reduction strategies. "
            "Always ground your reasoning in the supplied codebase telemetry.\n\n"
            f"{fenced_telemetry}"
        )

        # Assemble prompt with conversation history
        prompt_parts = []
        for turn in conversation_history[-4:]:  # keep last 4 turns for context
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "")
            prompt_parts.append(f"{role}: {content}")
        prompt_parts.append(f"User: {clean_user_message}")
        full_prompt = "\n\n".join(prompt_parts)

        # 3. Invoke Modular AI Engine with mapped preferred provider
        pref_provider = "gemini" if self.gemini_key else ("openai" if self.openai_key else "deterministic")
        ai_resp = await self.engine.generate_completion(
            prompt=full_prompt,
            system_prompt=system_prompt,
            preferred_provider=pref_provider
        )

        response_text = ai_resp.content

        # Fallback response generation if model returned default deterministic response
        msg_lower = clean_user_message.lower()
        if "deterministic" in ai_resp.provider and "Deterministic AI Engine" in response_text:
            if "refactor" in msg_lower or "hotspot" in msg_lower:
                top_hs = hotspots[0].get("file_path", "the core module") if hotspots else "core business logic"
                response_text = (
                    f"### Refactoring Recommendation for **{project_name}**\n\n"
                    f"Based on repository findings, the primary candidate for refactoring is **{top_hs}**.\n\n"
                    "**Recommended Strategy:**\n"
                    "1. **Guard Clauses:** Replace deeply nested branch ladders with early-exit guard clauses to reduce cyclomatic complexity.\n"
                    "2. **Method Extraction:** Extract isolated helper methods for domain business logic.\n"
                    "3. **Decoupling:** Introduce an interface abstraction between domain models and external I/O.\n\n"
                    f"Current repository health score is **{score}/100** ({risk_class})."
                )
            elif "security" in msg_lower or "cve" in msg_lower or "vulnerab" in msg_lower:
                crit_count = sum(1 for f in findings if f.get("severity") in ("Critical", "High"))
                response_text = (
                    f"### Security Posture Summary for **{project_name}**\n\n"
                    f"Repository scan shows **{crit_count} Critical/High severity finding(s)**.\n\n"
                    "- Prioritize updating dependencies with active CVE exposures.\n"
                    "- Replace raw SQL string formatting with parameterized query builders.\n"
                    "- Remove dangerous functions (such as dynamic eval or insecure deserialization).\n"
                )
            elif "depend" in msg_lower or "upgrade" in msg_lower:
                response_text = (
                    f"### Dependency Management Guidance for **{project_name}**\n\n"
                    f"The project tracks **{len(dependencies)} dependencies**.\n\n"
                    "- Isolate major upgrades into dedicated branches with complete regression test validation.\n"
                    "- Replace unmaintained or deprecated packages with modern, actively maintained alternatives.\n"
                    "- Enforce lockfile pinning to prevent supply-chain discrepancies."
                )
            else:
                response_text = (
                    f"### Architecture Assessment for **{project_name}**\n\n"
                    f"Your codebase is currently rated **{score}/100** ({risk_class}) with "
                    f"**{len(findings)} active finding(s)** across {len(hotspots)} analyzed files.\n\n"
                    "Key remediation priorities:\n"
                    "1. Eliminate high-complexity routines in core service hotspots.\n"
                    "2. Patch high-priority security findings and vulnerable libraries.\n"
                    "3. Expand automated unit test coverage to ensure regression resilience."
                )

        suggested_followups = [
            f"How do I refactor the top hotspot in {project_name}?",
            "What dependencies should we upgrade first?",
            "Show me a 30-day technical debt remediation plan."
        ]

        return {
            "origin": "llm_generated" if not ai_resp.fallback_used and ai_resp.provider != "deterministic" else "rule_based",
            "response": response_text,
            "project_name": project_name,
            "grounding_evidence": grounding_evidence,
            "suggested_followups": suggested_followups,
            "provider_used": ai_resp.provider,
            "model_used": ai_resp.model,
            "latency_ms": ai_resp.latency_ms,
            "fallback_used": ai_resp.fallback_used
        }

    async def _call_llm_assistant(
        self,
        project_name: str,
        overall_score: float,
        risk_classification: str,
        hotspots: List[Dict[str, Any]],
        code_findings: List[Dict[str, Any]],
        dependencies: List[Dict[str, Any]],
        total_remediation_hours: float = 10.0
    ) -> Optional[Dict[str, Any]]:
        """Invokes external LLM through ModularAIEngine with Pydantic schema validation and finding traceability."""
        prompt = (
            f"You are a Principal Software Architect. Analyze the technical debt of '{project_name}'.\n"
            f"Score: {overall_score}/100 ({risk_classification})\n"
            f"Estimated Remediation Hours: {total_remediation_hours}h\n"
            f"Ground your recommendations strictly in these real code findings:\n"
            f"Hotspots: {json.dumps(hotspots[:5])}\n"
            f"Findings Sample: {json.dumps(code_findings[:10])}\n"
            f"Dependencies: {len(dependencies)} packages\n"
            f"Return valid JSON adhering to the required schema with:\n"
            f"- executive_summary\n"
            f"- architecture_overview\n"
            f"- refactoring_recipes (target_file, primary_issue, strategy, step_by_step, finding_ids, expected_impact)\n"
            f"- modernization_roadmap (immediate_30_days, medium_term_60_days, long_term_90_days)\n"
            f"- grounding_finding_ids\n"
        )

        pref_provider = "gemini" if self.gemini_key else ("openai" if self.openai_key else "deterministic")
        res = await self.engine.generate_completion(
            prompt=prompt,
            system_prompt="You are TechDebt AI's Principal Engineering Assistant. Ground recommendations strictly in findings.",
            output_schema=RecommendationsSchema,
            preferred_provider=pref_provider
        )

        if res and res.parsed_json and not res.fallback_used:
            data = dict(res.parsed_json)
            known_ids = {str(cf.get("id")) for cf in code_findings if cf.get("id")}
            raw_grounding = data.get("grounding_finding_ids") or []
            verified_ids = [fid for fid in raw_grounding if fid in known_ids]

            data["origin"] = "llm_generated"
            data["provider"] = res.provider
            data["model"] = res.model
            data["finding_traceability"] = verified_ids if verified_ids else list(known_ids)[:5]
            data["latency_ms"] = res.latency_ms
            data["cost_usd"] = round((res.prompt_tokens / 1000.0 * 0.00015) + (res.completion_tokens / 1000.0 * 0.0006), 6)
            data["estimated_remediation_hours"] = total_remediation_hours
            return data

        return None

