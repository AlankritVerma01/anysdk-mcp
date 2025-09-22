# anysdk-mcp/mcp_sdk_bridge/ai/enrich.py

"""
LLM Enrichment Module

Uses LLMs to enhance SDK method descriptions and classify operation risks
when heuristics are insufficient. Includes cost tracking and caching.
"""

import os
import json
import hashlib
from typing import Dict, Any, Optional, Tuple, Literal
from dataclasses import dataclass, asdict
from pathlib import Path
import time
from datetime import datetime, timedelta

# Optional OpenAI import - graceful degradation if not available
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

@dataclass
class EnrichmentConfig:
    """Configuration for LLM enrichment"""
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    max_cost_usd: float = 5.0
    temperature: float = 0.0
    cache_enrichments: bool = True
    cache_file: str = ".mcp_cache/enrichment.json"
    api_key: Optional[str] = None
    
    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY")

@dataclass 
class CostTracking:
    """Track LLM API costs"""
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    request_count: int = 0
    last_reset: datetime = None
    
    def __post_init__(self):
        if not self.last_reset:
            self.last_reset = datetime.now()

@dataclass
class EnrichmentResult:
    """Result of LLM enrichment"""
    enhanced_description: str
    operation_type: Optional[Literal["read", "write"]] = None
    risk_level: Optional[Literal["low", "medium", "high"]] = None
    confidence: float = 0.0
    cached: bool = False
    cost_usd: float = 0.0
    tokens_used: int = 0

class LLMEnricher:
    """LLM-powered enhancement for SDK method descriptions and classification"""
    
    def __init__(self, config: EnrichmentConfig):
        self.config = config
        self.cost_tracking = CostTracking()
        self.cache: Dict[str, Dict[str, Any]] = {}
        
        # Load cache if it exists
        if self.config.cache_enrichments:
            self._load_cache()
        
        # Load cost tracking
        self._load_cost_tracking()
        
        # Setup OpenAI client if available
        if OPENAI_AVAILABLE and self.config.api_key:
            openai.api_key = self.config.api_key
        
    def _load_cache(self):
        """Load enrichment cache from disk"""
        try:
            cache_path = Path(self.config.cache_file)
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    self.cache = data.get("enrichments", {})
        except Exception:
            self.cache = {}
    
    def _save_cache(self):
        """Save enrichment cache to disk"""
        if not self.config.cache_enrichments:
            return
            
        try:
            cache_path = Path(self.config.cache_file)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "enrichments": self.cache,
                "cost_tracking": asdict(self.cost_tracking),
                "last_updated": datetime.now().isoformat()
            }
            
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save enrichment cache: {e}")
    
    def _load_cost_tracking(self):
        """Load cost tracking from cache"""
        try:
            cache_path = Path(self.config.cache_file)
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    cost_data = data.get("cost_tracking", {})
                    if cost_data:
                        self.cost_tracking = CostTracking(**cost_data)
        except Exception:
            pass
    
    def _generate_cache_key(self, method_name: str, docstring: str, signature: str) -> str:
        """Generate cache key for method enrichment"""
        content = f"{method_name}|{docstring}|{signature}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _check_budget(self) -> bool:
        """Check if we're within budget"""
        return self.cost_tracking.total_cost_usd < self.config.max_cost_usd
    
    def _estimate_cost(self, text: str) -> float:
        """Estimate cost for text processing (rough approximation)"""
        # Very rough estimation: ~4 chars per token, gpt-4o-mini pricing
        estimated_tokens = len(text) // 4 + 50  # +50 for system prompt
        # gpt-4o-mini: $0.00015 per 1K input tokens, $0.0006 per 1K output tokens
        input_cost = (estimated_tokens / 1000) * 0.00015
        output_cost = (100 / 1000) * 0.0006  # Assume ~100 output tokens
        return input_cost + output_cost
    
    def _call_openai(self, prompt: str, system_prompt: str) -> Tuple[str, int, float]:
        """Call OpenAI API with cost tracking"""
        if not OPENAI_AVAILABLE or not self.config.api_key:
            raise RuntimeError("OpenAI not available or API key not set")
        
        try:
            response = openai.ChatCompletion.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.temperature,
                max_tokens=200  # Keep responses concise
            )
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            
            # Calculate cost (rough - would need exact pricing)
            cost = self._estimate_cost(prompt + content)
            
            # Update tracking
            self.cost_tracking.total_cost_usd += cost
            self.cost_tracking.total_tokens += tokens_used
            self.cost_tracking.request_count += 1
            
            return content, tokens_used, cost
            
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {e}")
    
    def enrich_description(self, method_name: str, docstring: str, signature: str = "") -> EnrichmentResult:
        """Enhance method description using LLM"""
        if not self.config.enabled or not self._check_budget():
            return EnrichmentResult(
                enhanced_description=docstring or f"Method: {method_name}",
                cached=False
            )
        
        # Check cache first
        cache_key = self._generate_cache_key(method_name, docstring or "", signature)
        if cache_key in self.cache:
            cached_result = self.cache[cache_key]
            return EnrichmentResult(
                enhanced_description=cached_result["description"],
                operation_type=cached_result.get("operation_type"),
                risk_level=cached_result.get("risk_level"),
                confidence=cached_result.get("confidence", 0.0),
                cached=True
            )
        
        # Prepare prompt
        system_prompt = """You are an expert at analyzing SDK methods and creating concise, helpful descriptions for developers.

Your task is to:
1. Create a clear, concise description (max 150 chars) of what the method does
2. Classify if it's a "read" or "write" operation
3. Assess risk level: "low", "medium", or "high"
4. Provide confidence (0.0-1.0) in your classification

Respond in JSON format:
{
  "description": "Clear description of what this method does",
  "operation_type": "read|write", 
  "risk_level": "low|medium|high",
  "confidence": 0.8
}

Guidelines:
- Read operations: get, list, describe, show, fetch, retrieve
- Write operations: create, delete, update, modify, set, add, remove, start, stop
- Low risk: read operations, safe queries
- Medium risk: updates, configuration changes
- High risk: deletions, system changes, destructive operations"""

        user_prompt = f"""Method: {method_name}
Signature: {signature}
Docstring: {docstring or "No docstring available"}

Please analyze this SDK method and provide the JSON response."""

        try:
            response_text, tokens_used, cost = self._call_openai(user_prompt, system_prompt)
            
            # Parse JSON response
            try:
                response_data = json.loads(response_text)
                result = EnrichmentResult(
                    enhanced_description=response_data.get("description", docstring or method_name),
                    operation_type=response_data.get("operation_type"),
                    risk_level=response_data.get("risk_level"),
                    confidence=response_data.get("confidence", 0.0),
                    cost_usd=cost,
                    tokens_used=tokens_used,
                    cached=False
                )
                
                # Cache the result
                if self.config.cache_enrichments:
                    self.cache[cache_key] = {
                        "description": result.enhanced_description,
                        "operation_type": result.operation_type,
                        "risk_level": result.risk_level,
                        "confidence": result.confidence,
                        "timestamp": datetime.now().isoformat()
                    }
                    self._save_cache()
                
                return result
                
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return EnrichmentResult(
                    enhanced_description=response_text[:150] if len(response_text) > 150 else response_text,
                    cost_usd=cost,
                    tokens_used=tokens_used,
                    cached=False
                )
                
        except Exception as e:
            print(f"Warning: LLM enrichment failed for {method_name}: {e}")
            return EnrichmentResult(
                enhanced_description=docstring or f"Method: {method_name}",
                cached=False
            )
    
    def classify_risk(self, method_name: str, docstring: str = "") -> Tuple[str, str, float]:
        """Classify operation type and risk when heuristics are unclear"""
        result = self.enrich_description(method_name, docstring)
        
        return (
            result.operation_type or "read",
            result.risk_level or "low", 
            result.confidence
        )
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost and usage summary"""
        return {
            "total_cost_usd": round(self.cost_tracking.total_cost_usd, 4),
            "total_tokens": self.cost_tracking.total_tokens,
            "request_count": self.cost_tracking.request_count,
            "budget_remaining": round(self.config.max_cost_usd - self.cost_tracking.total_cost_usd, 4),
            "cache_size": len(self.cache),
            "last_reset": self.cost_tracking.last_reset.isoformat() if self.cost_tracking.last_reset else None
        }
    
    def reset_costs(self):
        """Reset cost tracking (useful for testing or monthly resets)"""
        self.cost_tracking = CostTracking()
        self._save_cache()

def create_enricher(config: Dict[str, Any]) -> Optional[LLMEnricher]:
    """Factory function to create LLM enricher from config"""
    llm_config = config.get("llm", {})
    features_config = config.get("features", {})
    
    if not features_config.get("llm_enrichment", False):
        return None
    
    enrichment_config = EnrichmentConfig(
        enabled=True,
        provider=llm_config.get("provider", "openai"),
        model=llm_config.get("model", "gpt-4o-mini"),
        max_cost_usd=llm_config.get("max_cost_usd", 5.0),
        temperature=llm_config.get("temperature", 0.0),
        cache_enrichments=llm_config.get("cache_enrichments", True),
        cache_file=llm_config.get("cache_file", ".mcp_cache/enrichment.json"),
        api_key=llm_config.get("api_key") or os.environ.get("OPENAI_API_KEY")
    )
    
    return LLMEnricher(enrichment_config)
