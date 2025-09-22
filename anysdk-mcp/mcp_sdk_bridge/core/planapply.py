# anysdk-mcp/mcp_sdk_bridge/core/planapply.py

"""
Plan/Apply Pattern Implementation

Provides safe execution of write operations through a two-step plan/apply process.
"""

import json
import time
import uuid
from typing import Any, Dict, Callable, Optional
from dataclasses import dataclass, asdict


@dataclass
class ExecutionPlan:
    """Represents a planned operation"""
    plan_id: str
    tool_name: str
    args: Dict[str, Any]
    created_at: float
    expires_at: float
    risk_level: str
    description: str


class PlanExecutionError(Exception):
    """Raised when plan execution fails"""
    pass


class Planner:
    """
    Manages the plan/apply lifecycle for write operations.
    
    This provides a safety mechanism where write operations must be:
    1. Planned first (returns a plan_id and preview)
    2. Applied later (executes the planned operation)
    """
    
    def __init__(self, default_ttl_seconds: int = 600):
        self.default_ttl_seconds = default_ttl_seconds
        self._plans: Dict[str, ExecutionPlan] = {}
    
    def plan(
        self, 
        tool_name: str, 
        args: Dict[str, Any], 
        risk_level: str = "medium",
        description: str = None,
        ttl_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create an execution plan for a write operation.
        
        Args:
            tool_name: Name of the tool/method to execute
            args: Arguments to pass to the tool
            risk_level: Risk level (low/medium/high)
            description: Human-readable description of the operation
            ttl_seconds: Time-to-live for the plan (default: 600s)
            
        Returns:
            Plan details including plan_id and preview
        """
        plan_id = str(uuid.uuid4())
        now = time.time()
        ttl = ttl_seconds or self.default_ttl_seconds
        
        plan = ExecutionPlan(
            plan_id=plan_id,
            tool_name=tool_name,
            args=args,
            created_at=now,
            expires_at=now + ttl,
            risk_level=risk_level,
            description=description or f"Execute {tool_name}"
        )
        
        self._plans[plan_id] = plan
        
        # Clean up expired plans
        self._cleanup_expired_plans()
        
        return {
            "plan_id": plan_id,
            "preview": {
                "tool": tool_name,
                "args": args,
                "risk_level": risk_level,
                "description": plan.description,
                "arg_summary": ", ".join(f"{k}={repr(v)[:80]}" for k, v in args.items())
            },
            "expires_in_seconds": int(ttl),
            "expires_at": plan.expires_at
        }
    
    def apply(self, plan_id: str, executor: Callable[[], Any]) -> Any:
        """
        Apply a previously created execution plan.
        
        Args:
            plan_id: The plan ID returned from plan()
            executor: Function that executes the planned operation
            
        Returns:
            Result of the executed operation
            
        Raises:
            PlanExecutionError: If plan is invalid, expired, or execution fails
        """
        # Clean up expired plans first
        self._cleanup_expired_plans()
        
        if plan_id not in self._plans:
            raise PlanExecutionError(f"Unknown or expired plan_id: {plan_id}")
        
        plan = self._plans.pop(plan_id)  # Remove plan after retrieval (single use)
        
        # Double-check expiration
        if time.time() > plan.expires_at:
            raise PlanExecutionError(f"Plan {plan_id} has expired")
        
        try:
            result = executor()
            return {
                "success": True,
                "result": result,
                "executed_plan": {
                    "tool": plan.tool_name,
                    "args": plan.args,
                    "executed_at": time.time()
                }
            }
        except Exception as e:
            raise PlanExecutionError(f"Plan execution failed: {str(e)}") from e
    
    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get plan details without consuming it"""
        self._cleanup_expired_plans()
        return self._plans.get(plan_id)
    
    def list_plans(self) -> Dict[str, ExecutionPlan]:
        """List all active plans"""
        self._cleanup_expired_plans()
        return self._plans.copy()
    
    def cancel_plan(self, plan_id: str) -> bool:
        """Cancel a plan"""
        return self._plans.pop(plan_id, None) is not None
    
    def _cleanup_expired_plans(self):
        """Remove expired plans"""
        now = time.time()
        expired_ids = [
            plan_id for plan_id, plan in self._plans.items()
            if now > plan.expires_at
        ]
        for plan_id in expired_ids:
            del self._plans[plan_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get planner statistics"""
        self._cleanup_expired_plans()
        return {
            "active_plans": len(self._plans),
            "plans_by_risk": {
                risk: sum(1 for p in self._plans.values() if p.risk_level == risk)
                for risk in ["low", "medium", "high"]
            }
        }
