# anysdk-mcp/mcp_sdk_bridge/core/planapply.py

"""
Plan/Apply Pattern Module

Implements the plan/apply pattern for safe execution of write operations.
"""

import uuid
import time
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class ExecutionPlan:
    """Represents a planned operation"""
    plan_id: str
    tool_name: str
    args: Dict[str, Any]
    risk_level: str
    description: str
    created_at: datetime
    expires_at: datetime
    status: str = "pending"  # pending, applied, expired, cancelled


class Planner:
    """Manages execution plans for write operations"""
    
    def __init__(self, default_ttl_minutes: int = 30):
        self.plans: Dict[str, ExecutionPlan] = {}
        self.default_ttl_minutes = default_ttl_minutes
    
    def plan(self, 
             tool_name: str, 
             args: Dict[str, Any], 
             risk_level: str,
             description: str = None,
             ttl_minutes: int = None) -> Dict[str, Any]:
        """Create an execution plan"""
        plan_id = str(uuid.uuid4())
        ttl = ttl_minutes or self.default_ttl_minutes
        
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=ttl)
        
        plan = ExecutionPlan(
            plan_id=plan_id,
            tool_name=tool_name,
            args=args,
            risk_level=risk_level,
            description=description or f"Execute {tool_name}",
            created_at=now,
            expires_at=expires_at
        )
        
        self.plans[plan_id] = plan
        
        # Clean up expired plans
        self._cleanup_expired_plans()
        
        return {
            "plan_id": plan_id,
            "tool_name": tool_name,
            "args": args,
            "risk_level": risk_level,
            "description": plan.description,
            "expires_at": expires_at.isoformat(),
            "ttl_minutes": ttl,
            "status": "pending",
            "instructions": f"To execute this plan, call {tool_name}.apply with plan_id: {plan_id}"
        }
    
    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID"""
        self._cleanup_expired_plans()
        return self.plans.get(plan_id)
    
    def apply(self, plan_id: str, executor: Callable[[], Any]) -> Dict[str, Any]:
        """Apply a planned operation"""
        plan = self.get_plan(plan_id)
        
        if not plan:
            return {
                "error": {
                    "type": "PlanNotFound",
                    "message": f"Plan {plan_id} not found or expired",
                    "plan_id": plan_id
                }
            }
        
        if plan.status != "pending":
            return {
                "error": {
                    "type": "PlanAlreadyApplied",
                    "message": f"Plan {plan_id} has already been {plan.status}",
                    "plan_id": plan_id,
                    "status": plan.status
                }
            }
        
        try:
            # Execute the planned operation
            result = executor()
            
            # Mark plan as applied and remove it
            plan.status = "applied"
            del self.plans[plan_id]
            
            return {
                "plan_id": plan_id,
                "status": "applied",
                "tool_name": plan.tool_name,
                "applied_at": datetime.utcnow().isoformat(),
                "result": result
            }
            
        except Exception as e:
            # Mark plan as failed but keep it for debugging
            plan.status = "failed"
            
            return {
                "error": {
                    "type": "ExecutionFailed",
                    "message": str(e),
                    "plan_id": plan_id,
                    "tool_name": plan.tool_name
                }
            }
    
    def cancel_plan(self, plan_id: str) -> Dict[str, Any]:
        """Cancel a pending plan"""
        plan = self.get_plan(plan_id)
        
        if not plan:
            return {
                "error": {
                    "type": "PlanNotFound", 
                    "message": f"Plan {plan_id} not found or expired"
                }
            }
        
        if plan.status != "pending":
            return {
                "error": {
                    "type": "PlanNotPending",
                    "message": f"Plan {plan_id} cannot be cancelled (status: {plan.status})"
                }
            }
        
        plan.status = "cancelled"
        del self.plans[plan_id]
        
        return {
            "plan_id": plan_id,
            "status": "cancelled",
            "cancelled_at": datetime.utcnow().isoformat()
        }
    
    def list_plans(self, include_completed: bool = False) -> Dict[str, Any]:
        """List all plans"""
        self._cleanup_expired_plans()
        
        plans = []
        for plan in self.plans.values():
            if not include_completed and plan.status != "pending":
                continue
                
            plans.append({
                "plan_id": plan.plan_id,
                "tool_name": plan.tool_name,
                "risk_level": plan.risk_level,
                "description": plan.description,
                "status": plan.status,
                "created_at": plan.created_at.isoformat(),
                "expires_at": plan.expires_at.isoformat()
            })
        
        return {
            "plans": plans,
            "total": len(plans),
            "pending": len([p for p in plans if p["status"] == "pending"])
        }
    
    def _cleanup_expired_plans(self):
        """Remove expired plans"""
        now = datetime.utcnow()
        expired_ids = []
        
        for plan_id, plan in self.plans.items():
            if now > plan.expires_at and plan.status == "pending":
                plan.status = "expired"
                expired_ids.append(plan_id)
        
        for plan_id in expired_ids:
            del self.plans[plan_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get planner statistics"""
        self._cleanup_expired_plans()
        
        status_counts = {}
        for plan in self.plans.values():
            status_counts[plan.status] = status_counts.get(plan.status, 0) + 1
        
        return {
            "total_plans": len(self.plans),
            "status_breakdown": status_counts,
            "default_ttl_minutes": self.default_ttl_minutes
        }