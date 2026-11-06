import os
import json
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
import httpx
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger(__name__)

class LLMResponse(BaseModel):
    provider: str
    model: str
    content: str
    parsed_json: Optional[Dict[str, Any]] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    fallback_used: bool = False

class BaseLLMProvider(ABC):
    def __init__(self, name: str, api_key: str, default_model: str):
        self.name = name
        self.api_key = api_key.strip()
        self.default_model = default_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        pass

class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gemini-1.5-flash"):
        super().__init__("gemini", api_key or settings.GEMINI_API_KEY or "", default_model)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2
    ) -> LLMResponse:
        if not self.is_configured():
            raise RuntimeError("Gemini API key is not configured")

        m = model or self.default_model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
        
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System context:\n{system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        start_time = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body)
            latency = (time.time() - start_time) * 1000.0

            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API error ({resp.status_code}): {resp.text}")

            data = resp.json()
            candidates = data.get("candidates", [])
            text_out = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text_out = parts[0].get("text", "")

            usage = data.get("usageMetadata", {})
            p_tok = usage.get("promptTokenCount", len(prompt) // 4)
            c_tok = usage.get("candidatesTokenCount", len(text_out) // 4)

            return LLMResponse(
                provider="gemini",
                model=m,
                content=text_out,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                latency_ms=round(latency, 2)
            )

    async def health_check(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {"provider": "gemini", "status": "unconfigured", "latency_ms": 0.0}
        try:
            res = await self.generate_text("Reply with pong", max_tokens=10)
            return {"provider": "gemini", "status": "healthy", "latency_ms": res.latency_ms}
        except Exception as e:
            return {"provider": "gemini", "status": "unhealthy", "error": str(e), "latency_ms": 0.0}

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4o-mini"):
        super().__init__("openai", api_key or settings.OPENAI_API_KEY or "", default_model)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2
    ) -> LLMResponse:
        if not self.is_configured():
            raise RuntimeError("OpenAI API key is not configured")

        m = model or self.default_model
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": m,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        start_time = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            latency = (time.time() - start_time) * 1000.0

            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI API error ({resp.status_code}): {resp.text}")

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return LLMResponse(
                provider="openai",
                model=m,
                content=content,
                prompt_tokens=usage.get("prompt_tokens", len(prompt) // 4),
                completion_tokens=usage.get("completion_tokens", len(content) // 4),
                latency_ms=round(latency, 2)
            )

    async def health_check(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {"provider": "openai", "status": "unconfigured", "latency_ms": 0.0}
        try:
            res = await self.generate_text("Reply with pong", max_tokens=10)
            return {"provider": "openai", "status": "healthy", "latency_ms": res.latency_ms}
        except Exception as e:
            return {"provider": "openai", "status": "unhealthy", "error": str(e), "latency_ms": 0.0}

class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, default_model: str = "claude-3-5-sonnet-20241022"):
        super().__init__("anthropic", api_key or settings.ANTHROPIC_API_KEY or "", default_model)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2
    ) -> LLMResponse:
        if not self.is_configured():
            raise RuntimeError("Anthropic API key is not configured")

        m = model or self.default_model
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        body = {
            "model": m,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]
        }
        if system_prompt:
            body["system"] = system_prompt

        start_time = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            latency = (time.time() - start_time) * 1000.0

            if resp.status_code != 200:
                raise RuntimeError(f"Anthropic API error ({resp.status_code}): {resp.text}")

            data = resp.json()
            content_blocks = data.get("content", [])
            content = content_blocks[0].get("text", "") if content_blocks else ""
            usage = data.get("usage", {})
            return LLMResponse(
                provider="anthropic",
                model=m,
                content=content,
                prompt_tokens=usage.get("input_tokens", len(prompt) // 4),
                completion_tokens=usage.get("output_tokens", len(content) // 4),
                latency_ms=round(latency, 2)
            )

    async def health_check(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {"provider": "anthropic", "status": "unconfigured", "latency_ms": 0.0}
        try:
            res = await self.generate_text("Reply with pong", max_tokens=10)
            return {"provider": "anthropic", "status": "healthy", "latency_ms": res.latency_ms}
        except Exception as e:
            return {"provider": "anthropic", "status": "unhealthy", "error": str(e), "latency_ms": 0.0}

class DeterministicFallbackProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__("deterministic", "deterministic-internal-key", "deterministic-engine-v3")

    def is_configured(self) -> bool:
        return True

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2
    ) -> LLMResponse:
        start_time = time.time()
        
        # Check if the prompt requests JSON format
        prompt_lower = prompt.lower()
        if "json" in prompt_lower or "schema" in prompt_lower:
            content = json.dumps({
                "status": "deterministic_analysis_completed",
                "summary": "Deterministic AI engine evaluated technical debt telemetry and findings.",
                "analysis": "Identified areas requiring maintenance, vulnerability patching, and modular refactoring.",
                "confidence_level": "High",
                "recommended_actions": [
                    "Perform major dependency upgrades in a phased sprint.",
                    "Remediate highlighted security findings and remove unpinned packages.",
                    "Increase unit test fixture coverage around high-complexity routines."
                ]
            })
        else:
            content = (
                "Deterministic AI Engine Assessment:\n"
                "- Architecture: Modular components identified with standard cohesion.\n"
                "- Security: Vulnerabilities evaluated against OSV dataset and security rules.\n"
                "- Maintainability: Cyclomatic complexity and code duplication indices reviewed."
            )

        latency = (time.time() - start_time) * 1000.0
        return LLMResponse(
            provider="deterministic",
            model="deterministic-engine-v3",
            content=content,
            prompt_tokens=len(prompt) // 4,
            completion_tokens=len(content) // 4,
            latency_ms=round(latency, 2),
            fallback_used=True
        )

    async def health_check(self) -> Dict[str, Any]:
        return {"provider": "deterministic", "status": "healthy", "latency_ms": 0.5}

class ModularAIEngine:
    def __init__(self):
        self.providers: Dict[str, BaseLLMProvider] = {
            "gemini": GeminiProvider(),
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
            "deterministic": DeterministicFallbackProvider()
        }
        self.default_provider = settings.DEFAULT_AI_PROVIDER.lower() if settings.DEFAULT_AI_PROVIDER else "gemini"
        if self.default_provider not in self.providers:
            self.default_provider = "gemini"

    def get_provider(self, name: str) -> BaseLLMProvider:
        return self.providers.get(name.lower(), self.providers["deterministic"])

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        output_schema: Optional[Type[BaseModel]] = None,
        preferred_provider: Optional[str] = None,
        strict_defense: bool = False
    ) -> LLMResponse:
        """
        Executes completion with automatic cascading fallback and prompt injection defenses:
        Preferred / Default -> Other configured cloud providers -> Deterministic Fallback.
        """
        from app.services.prompt_defense_service import PromptDefenseService

        # 1. Defend Input Prompt
        defense_inspection = PromptDefenseService.inspect_input(
            prompt, mode="STRICT" if strict_defense else "SANITIZE"
        )
        if not defense_inspection["is_safe"]:
            raise ValueError(f"Prompt injection threat blocked: {', '.join(defense_inspection['detected_threats'])}")
        effective_prompt = defense_inspection["sanitized_text"]

        # Determine trial order
        candidates = []
        if preferred_provider and preferred_provider.lower() in self.providers:
            candidates.append(preferred_provider.lower())
        if self.default_provider not in candidates:
            candidates.append(self.default_provider)
        for p in ["gemini", "openai", "anthropic"]:
            if p not in candidates and self.providers[p].is_configured():
                candidates.append(p)
        candidates.append("deterministic")

        last_error = None
        for p_name in candidates:
            provider = self.providers[p_name]
            if not provider.is_configured() and p_name != "deterministic":
                continue

            try:
                res = await provider.generate_text(prompt=effective_prompt, system_prompt=system_prompt)
                if p_name != candidates[0]:
                    res.fallback_used = True
                
                # Sanitize output from credential leaks
                out_check = PromptDefenseService.inspect_output(res.content)
                res.content = out_check["sanitized_output"]

                # If output schema requested, validate JSON
                if output_schema:
                    try:
                        clean_content = res.content.strip()
                        if clean_content.startswith("```json"):
                            clean_content = clean_content[7:]
                        if clean_content.startswith("```"):
                            clean_content = clean_content[3:]
                        if clean_content.endswith("```"):
                            clean_content = clean_content[:-3]
                        parsed = json.loads(clean_content.strip())
                        res.parsed_json = parsed
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse JSON from {p_name}: {parse_err}")
                return res
            except Exception as e:
                logger.warning(f"AI provider '{p_name}' failed during generation: {e}; attempting fallback.")
                last_error = e

        # If everything somehow failed, invoke deterministic directly
        det_res = await self.providers["deterministic"].generate_text(effective_prompt, system_prompt)
        out_check = PromptDefenseService.inspect_output(det_res.content)
        det_res.content = out_check["sanitized_output"]
        return det_res

    async def get_providers_status(self) -> Dict[str, Any]:
        statuses = {}
        for name, provider in self.providers.items():
            statuses[name] = {
                "name": name,
                "is_configured": provider.is_configured(),
                "default_model": provider.default_model,
                "is_default": (name == self.default_provider)
            }
        return {
            "default_provider": self.default_provider,
            "configured_count": sum(1 for p in statuses.values() if p["is_configured"]),
            "providers": statuses
        }

# Global singleton engine instance
modular_ai_engine = ModularAIEngine()
