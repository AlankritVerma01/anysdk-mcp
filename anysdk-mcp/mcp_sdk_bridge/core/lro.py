# anysdk-mcp/mcp_sdk_bridge/core/lro.py

"""
Long Running Operations (LRO) Module

Handles long-running operations from SDK methods with polling and status tracking.
"""

from typing import Any, Dict, Optional, Callable, Union, List
import asyncio
import time
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from .serialize import ResponseSerializer


class OperationStatus(Enum):
    """Status of a long-running operation"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class LROConfig:
    """Configuration for long-running operations"""
    poll_interval: float = 2.0  # seconds
    max_poll_attempts: int = 300  # 10 minutes at 2s intervals
    timeout: Optional[float] = None  # seconds
    status_field: str = "status"
    result_field: str = "result"
    error_field: str = "error"


@dataclass
class OperationResult:
    """Result of a long-running operation"""
    operation_id: str
    status: OperationStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: Optional[float] = None  # 0.0 to 1.0
    metadata: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class LROHandler:
    """Handles long-running operations"""
    
    def __init__(self, serializer: Optional[ResponseSerializer] = None):
        self.serializer = serializer or ResponseSerializer()
        self.active_operations: Dict[str, OperationResult] = {}
    
    async def start_operation(self,
                            operation_func: Callable,
                            operation_id: str = None,
                            config: LROConfig = None,
                            **kwargs) -> OperationResult:
        """Start a long-running operation"""
        if operation_id is None:
            operation_id = self._generate_operation_id()
        
        if config is None:
            config = LROConfig()
        
        # Initialize operation tracking
        operation = OperationResult(
            operation_id=operation_id,
            status=OperationStatus.PENDING,
            started_at=datetime.utcnow()
        )
        
        self.active_operations[operation_id] = operation
        
        try:
            # Start the operation
            if asyncio.iscoroutinefunction(operation_func):
                initial_result = await operation_func(**kwargs)
            else:
                initial_result = operation_func(**kwargs)
            
            # Check if operation completed immediately
            if self._is_operation_complete(initial_result, config):
                operation.status = OperationStatus.SUCCEEDED
                operation.result = self._extract_result(initial_result, config)
                operation.completed_at = datetime.utcnow()
            else:
                # Start polling
                operation.status = OperationStatus.RUNNING
                asyncio.create_task(
                    self._poll_operation(operation_id, initial_result, config)
                )
        
        except Exception as e:
            operation.status = OperationStatus.FAILED
            operation.error = str(e)
            operation.completed_at = datetime.utcnow()
        
        return operation
    
    async def _poll_operation(self,
                            operation_id: str,
                            poll_target: Any,
                            config: LROConfig):
        """Poll an operation until completion"""
        operation = self.active_operations.get(operation_id)
        if not operation:
            return
        
        poll_count = 0
        start_time = time.time()
        
        while poll_count < config.max_poll_attempts:
            try:
                # Check timeout
                if config.timeout and (time.time() - start_time) > config.timeout:
                    operation.status = OperationStatus.FAILED
                    operation.error = "Operation timed out"
                    operation.completed_at = datetime.utcnow()
                    break
                
                # Poll for status
                if hasattr(poll_target, 'get_status'):
                    status_result = await poll_target.get_status()
                elif callable(poll_target):
                    status_result = await poll_target() if asyncio.iscoroutinefunction(poll_target) else poll_target()
                else:
                    # Assume poll_target is the result itself
                    status_result = poll_target
                
                # Check if complete
                if self._is_operation_complete(status_result, config):
                    operation.result = self._extract_result(status_result, config)
                    operation.status = OperationStatus.SUCCEEDED
                    operation.completed_at = datetime.utcnow()
                    break
                
                # Check if failed
                if self._is_operation_failed(status_result, config):
                    operation.status = OperationStatus.FAILED
                    operation.error = self._extract_error(status_result, config)
                    operation.completed_at = datetime.utcnow()
                    break
                
                # Update progress if available
                progress = self._extract_progress(status_result)
                if progress is not None:
                    operation.progress = progress
                
                # Wait before next poll
                await asyncio.sleep(config.poll_interval)
                poll_count += 1
                
            except Exception as e:
                operation.status = OperationStatus.FAILED
                operation.error = f"Polling error: {str(e)}"
                operation.completed_at = datetime.utcnow()
                break
        
        # If we exhausted poll attempts
        if poll_count >= config.max_poll_attempts and operation.status == OperationStatus.RUNNING:
            operation.status = OperationStatus.FAILED
            operation.error = "Maximum poll attempts exceeded"
            operation.completed_at = datetime.utcnow()
    
    def get_operation_status(self, operation_id: str) -> Optional[OperationResult]:
        """Get the status of an operation"""
        return self.active_operations.get(operation_id)
    
    def cancel_operation(self, operation_id: str) -> bool:
        """Cancel an operation"""
        operation = self.active_operations.get(operation_id)
        if operation and operation.status in [OperationStatus.PENDING, OperationStatus.RUNNING]:
            operation.status = OperationStatus.CANCELLED
            operation.completed_at = datetime.utcnow()
            return True
        return False
    
    def list_operations(self, status_filter: Optional[OperationStatus] = None) -> List[OperationResult]:
        """List all operations, optionally filtered by status"""
        operations = list(self.active_operations.values())
        
        if status_filter:
            operations = [op for op in operations if op.status == status_filter]
        
        return operations
    
    def cleanup_completed_operations(self, max_age_hours: int = 24):
        """Clean up old completed operations"""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for op_id, operation in self.active_operations.items():
            if (operation.status in [OperationStatus.SUCCEEDED, OperationStatus.FAILED, OperationStatus.CANCELLED] 
                and operation.completed_at 
                and operation.completed_at < cutoff_time):
                to_remove.append(op_id)
        
        for op_id in to_remove:
            del self.active_operations[op_id]
        
        return len(to_remove)
    
    def _generate_operation_id(self) -> str:
        """Generate a unique operation ID"""
        return f"op_{int(datetime.utcnow().timestamp() * 1000000)}"
    
    def _is_operation_complete(self, result: Any, config: LROConfig) -> bool:
        """Check if operation is complete"""
        if isinstance(result, dict):
            status = result.get(config.status_field, "").lower()
            return status in ["completed", "succeeded", "done", "finished"]
        
        # If result has a status attribute
        if hasattr(result, 'status'):
            status = str(result.status).lower()
            return status in ["completed", "succeeded", "done", "finished"]
        
        # Default: assume simple results are complete
        return True
    
    def _is_operation_failed(self, result: Any, config: LROConfig) -> bool:
        """Check if operation failed"""
        if isinstance(result, dict):
            status = result.get(config.status_field, "").lower()
            return status in ["failed", "error", "cancelled"]
        
        if hasattr(result, 'status'):
            status = str(result.status).lower()
            return status in ["failed", "error", "cancelled"]
        
        return False
    
    def _extract_result(self, result: Any, config: LROConfig) -> Any:
        """Extract the actual result from operation response"""
        if isinstance(result, dict) and config.result_field in result:
            return result[config.result_field]
        
        if hasattr(result, 'result'):
            return result.result
        
        return result
    
    def _extract_error(self, result: Any, config: LROConfig) -> str:
        """Extract error message from operation response"""
        if isinstance(result, dict) and config.error_field in result:
            return str(result[config.error_field])
        
        if hasattr(result, 'error'):
            return str(result.error)
        
        return "Unknown error"
    
    def _extract_progress(self, result: Any) -> Optional[float]:
        """Extract progress from operation response"""
        if isinstance(result, dict):
            for key in ['progress', 'percent_complete', 'completion']:
                if key in result:
                    try:
                        progress = float(result[key])
                        return min(max(progress, 0.0), 1.0)  # Clamp to 0-1
                    except (ValueError, TypeError):
                        continue
        
        if hasattr(result, 'progress'):
            try:
                progress = float(result.progress)
                return min(max(progress, 0.0), 1.0)
            except (ValueError, TypeError):
                pass
        
        return None
