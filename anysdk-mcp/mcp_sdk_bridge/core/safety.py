# anysdk-mcp/mcp_sdk_bridge/core/safety.py

"""
Safety and Security Module

Provides safety mechanisms, rate limiting, and security controls for SDK operations.
"""

from typing import Any, Dict, List, Optional, Callable, Set
import time
import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict, deque


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10
    cooldown_seconds: int = 60


@dataclass
class SafetyConfig:
    """Configuration for safety controls"""
    max_response_size_mb: int = 10
    max_execution_time_seconds: int = 300
    allowed_methods: Optional[Set[str]] = None
    blocked_methods: Optional[Set[str]] = None
    require_auth: bool = True
    sanitize_inputs: bool = True
    log_operations: bool = True


@dataclass
class SecurityContext:
    """Security context for operations"""
    user_id: Optional[str] = None
    api_key: Optional[str] = None
    permissions: Set[str] = field(default_factory=set)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class RateLimiter:
    """Rate limiter with multiple time windows"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.requests_per_minute: Dict[str, deque] = defaultdict(deque)
        self.requests_per_hour: Dict[str, deque] = defaultdict(deque)
        self.burst_tokens: Dict[str, int] = defaultdict(lambda: config.burst_size)
        self.last_refill: Dict[str, float] = defaultdict(time.time)
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed under rate limits"""
        now = time.time()
        
        # Clean old requests
        self._clean_old_requests(key, now)
        
        # Check minute limit
        if len(self.requests_per_minute[key]) >= self.config.requests_per_minute:
            return False
        
        # Check hour limit
        if len(self.requests_per_hour[key]) >= self.config.requests_per_hour:
            return False
        
        # Check burst limit (token bucket)
        self._refill_burst_tokens(key, now)
        if self.burst_tokens[key] <= 0:
            return False
        
        return True
    
    def record_request(self, key: str):
        """Record a request"""
        now = time.time()
        self.requests_per_minute[key].append(now)
        self.requests_per_hour[key].append(now)
        self.burst_tokens[key] -= 1
    
    def _clean_old_requests(self, key: str, now: float):
        """Remove old requests outside time windows"""
        minute_ago = now - 60
        hour_ago = now - 3600
        
        # Clean minute window
        while (self.requests_per_minute[key] and 
               self.requests_per_minute[key][0] < minute_ago):
            self.requests_per_minute[key].popleft()
        
        # Clean hour window
        while (self.requests_per_hour[key] and 
               self.requests_per_hour[key][0] < hour_ago):
            self.requests_per_hour[key].popleft()
    
    def _refill_burst_tokens(self, key: str, now: float):
        """Refill burst tokens based on time elapsed"""
        time_since_refill = now - self.last_refill[key]
        tokens_to_add = int(time_since_refill / 60 * self.config.requests_per_minute)
        
        if tokens_to_add > 0:
            self.burst_tokens[key] = min(
                self.config.burst_size,
                self.burst_tokens[key] + tokens_to_add
            )
            self.last_refill[key] = now


class SafetyValidator:
    """Validates operations for safety"""
    
    def __init__(self, config: SafetyConfig):
        self.config = config
    
    def validate_method(self, method_name: str) -> bool:
        """Validate if method is allowed"""
        if self.config.blocked_methods and method_name in self.config.blocked_methods:
            return False
        
        if self.config.allowed_methods and method_name not in self.config.allowed_methods:
            return False
        
        return True
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize inputs"""
        if not self.config.sanitize_inputs:
            return inputs
        
        sanitized = {}
        for key, value in inputs.items():
            sanitized[key] = self._sanitize_value(value)
        
        return sanitized
    
    def validate_response_size(self, response: Any) -> bool:
        """Check if response size is within limits"""
        try:
            # Rough size estimation
            response_str = str(response)
            size_mb = len(response_str.encode('utf-8')) / (1024 * 1024)
            return size_mb <= self.config.max_response_size_mb
        except:
            return True  # Allow if we can't measure
    
    def _sanitize_value(self, value: Any) -> Any:
        """Sanitize individual values"""
        if isinstance(value, str):
            # Basic string sanitization
            return value.strip()[:1000]  # Limit length
        elif isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._sanitize_value(item) for item in value[:100]]  # Limit list size
        else:
            return value


class SecurityManager:
    """Manages security controls and authentication"""
    
    def __init__(self):
        self.api_keys: Dict[str, SecurityContext] = {}
        self.session_tokens: Dict[str, SecurityContext] = {}
    
    def register_api_key(self, api_key: str, context: SecurityContext):
        """Register an API key with security context"""
        key_hash = self._hash_key(api_key)
        self.api_keys[key_hash] = context
    
    def authenticate(self, api_key: str = None, token: str = None) -> Optional[SecurityContext]:
        """Authenticate using API key or token"""
        if api_key:
            key_hash = self._hash_key(api_key)
            return self.api_keys.get(key_hash)
        
        if token:
            return self.session_tokens.get(token)
        
        return None
    
    def check_permission(self, context: SecurityContext, permission: str) -> bool:
        """Check if context has required permission"""
        return permission in context.permissions
    
    def _hash_key(self, key: str) -> str:
        """Hash an API key for storage"""
        return hashlib.sha256(key.encode()).hexdigest()


class SafetyWrapper:
    """Wraps SDK methods with safety controls"""
    
    def __init__(self, 
                 safety_config: SafetyConfig,
                 rate_limit_config: RateLimitConfig = None):
        self.safety_config = safety_config
        self.rate_limiter = RateLimiter(rate_limit_config or RateLimitConfig())
        self.validator = SafetyValidator(safety_config)
        self.security_manager = SecurityManager()
        self.operation_log: List[Dict[str, Any]] = []
        from .serialize import ResponseSerializer
        self.serializer = ResponseSerializer()
    
    def safe_wrap(self, method: Callable, method_name: str):
        """Wrap a method with safety controls"""
        if asyncio.iscoroutinefunction(method):
            @wraps(method)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await self._execute_safely(method, method_name, True, *args, **kwargs)
                except Exception as e:
                    return self.serializer.serialize_error(e, {"method": method_name})
            return async_wrapper
        else:
            @wraps(method)
            def sync_wrapper(*args, **kwargs):
                try:
                    return self._execute_safely_sync(method, method_name, *args, **kwargs)
                except Exception as e:
                    return self.serializer.serialize_error(e, {"method": method_name})
            return sync_wrapper
    
    def _execute_safely_sync(self, method: Callable, method_name: str, *args, **kwargs) -> Any:
        """Execute method safely (synchronous version)"""
        start_time = time.time()
        context = kwargs.pop('_security_context', None)
        
        # Validate method
        if not self.validator.validate_method(method_name):
            raise SecurityError(f"Method {method_name} is not allowed")
        
        # Check authentication
        if self.safety_config.require_auth and not context:
            raise SecurityError("Authentication required")
        
        # Rate limiting
        rate_limit_key = context.user_id if context else "anonymous"
        if not self.rate_limiter.is_allowed(rate_limit_key):
            raise RateLimitError("Rate limit exceeded")
        
        self.rate_limiter.record_request(rate_limit_key)
        
        # Sanitize inputs
        kwargs = self.validator.validate_inputs(kwargs)
        
        # Execute method
        result = method(*args, **kwargs)
        
        # Validate response size
        if not self.validator.validate_response_size(result):
            raise SafetyError("Response size exceeds limit")
        
        # Log operation
        if self.safety_config.log_operations:
            self._log_operation(method_name, context, True, time.time() - start_time)
        
        return result
    
    async def _execute_safely(self, 
                             method: Callable,
                             method_name: str,
                             is_async: bool,
                             *args, **kwargs) -> Any:
        """Execute method with safety checks"""
        start_time = time.time()
        context = kwargs.pop('_security_context', None)
        
        try:
            # Validate method
            if not self.validator.validate_method(method_name):
                raise SecurityError(f"Method {method_name} is not allowed")
            
            # Check authentication
            if self.safety_config.require_auth and not context:
                raise SecurityError("Authentication required")
            
            # Rate limiting
            rate_limit_key = context.user_id if context else "anonymous"
            if not self.rate_limiter.is_allowed(rate_limit_key):
                raise RateLimitError("Rate limit exceeded")
            
            self.rate_limiter.record_request(rate_limit_key)
            
            # Sanitize inputs
            kwargs = self.validator.validate_inputs(kwargs)
            
            # Execute with timeout
            if is_async:
                result = await asyncio.wait_for(
                    method(*args, **kwargs),
                    timeout=self.safety_config.max_execution_time_seconds
                )
            else:
                result = method(*args, **kwargs)
            
            # Validate response size
            if not self.validator.validate_response_size(result):
                raise SafetyError("Response size exceeds limit")
            
            # Log operation
            if self.safety_config.log_operations:
                self._log_operation(method_name, context, True, time.time() - start_time)
            
            return result
            
        except Exception as e:
            # Log failed operation
            if self.safety_config.log_operations:
                self._log_operation(method_name, context, False, time.time() - start_time, str(e))
            raise
    
    def _log_operation(self, 
                      method_name: str,
                      context: Optional[SecurityContext],
                      success: bool,
                      duration: float,
                      error: str = None):
        """Log an operation"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "method": method_name,
            "user_id": context.user_id if context else None,
            "success": success,
            "duration": duration,
            "error": error
        }
        
        self.operation_log.append(log_entry)
        
        # Keep only recent logs (last 1000)
        if len(self.operation_log) > 1000:
            self.operation_log = self.operation_log[-1000:]


class SecurityError(Exception):
    """Security-related error"""
    pass


class RateLimitError(Exception):
    """Rate limit exceeded error"""
    pass


class SafetyError(Exception):
    """Safety-related error"""
    pass
