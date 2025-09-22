# anysdk-mcp/mcp_sdk_bridge/core/classify.py

"""
Operation Classification Module

Classifies SDK methods as read/write operations and assigns risk levels.
"""

import re
from typing import Literal


def classify_method(method_name: str) -> Literal["read", "write"]:
    """Classify a method as read or write operation"""
    method_lower = method_name.lower()
    
    # Write operation patterns - match word boundaries and common prefixes
    write_patterns = [
        r'^create', r'_create', r'^post', r'_post', r'^add', r'_add', r'^insert', r'_insert',
        r'^delete', r'_delete', r'^remove', r'_remove', r'^drop', r'_drop', r'^destroy', r'_destroy',
        r'^update', r'_update', r'^put', r'_put', r'^patch', r'_patch', r'^modify', r'_modify', r'^edit', r'_edit',
        r'^set', r'_set', r'^write', r'_write', r'^save', r'_save', r'^store', r'_store',
        r'^start', r'_start', r'^stop', r'_stop', r'^restart', r'_restart', r'^kill', r'_kill', r'^terminate', r'_terminate',
        r'^scale', r'_scale', r'^resize', r'_resize', r'^move', r'_move', r'^copy', r'_copy', r'^clone', r'_clone',
        r'^fork', r'_fork', r'^merge', r'_merge', r'^push', r'_push', r'^commit', r'_commit',
        r'^apply', r'_apply', r'^execute', r'_execute', r'^run', r'_run', r'^trigger', r'_trigger'
    ]
    
    # Check for write patterns
    for pattern in write_patterns:
        if re.search(pattern, method_lower):
            return "write"
    
    # Default to read
    return "read"


def get_operation_risk_level(method_name: str) -> Literal["low", "medium", "high"]:
    """Get the risk level of an operation"""
    method_lower = method_name.lower()
    
    # High risk patterns (destructive operations)
    high_risk_patterns = [
        r'^delete', r'_delete', r'^remove', r'_remove', r'^drop', r'_drop', r'^destroy', r'_destroy',
        r'^kill', r'_kill', r'^terminate', r'_terminate', r'^force', r'_force', r'^purge', r'_purge',
        r'namespace', r'cluster', r'node', r'volume'
    ]
    
    # Medium risk patterns (modifying operations)
    medium_risk_patterns = [
        r'^create', r'_create', r'^update', r'_update', r'^patch', r'_patch', r'^modify', r'_modify',
        r'^scale', r'_scale', r'^restart', r'_restart', r'^start', r'_start', r'^stop', r'_stop',
        r'^set', r'_set', r'^write', r'_write', r'^save', r'_save', r'^apply', r'_apply',
        r'^merge', r'_merge', r'^commit', r'_commit', r'^push', r'_push'
    ]
    
    # Check for high risk
    for pattern in high_risk_patterns:
        if re.search(pattern, method_lower):
            return "high"
    
    # Check for medium risk
    for pattern in medium_risk_patterns:
        if re.search(pattern, method_lower):
            return "medium"
    
    # Default to low risk (read operations)
    return "low"


def is_safe_for_auto_execution(method_name: str) -> bool:
    """Check if a method is safe for automatic execution without user confirmation"""
    risk_level = get_operation_risk_level(method_name)
    operation_type = classify_method(method_name)
    
    # Only read operations with low risk are safe for auto execution
    return operation_type == "read" and risk_level == "low"


def get_method_description_suffix(method_name: str) -> str:
    """Get a description suffix based on method classification"""
    op_type = classify_method(method_name)
    risk_level = get_operation_risk_level(method_name)
    
    if op_type == "read":
        return f"[Read operation, Risk: {risk_level}]"
    else:
        return f"[Write operation, Risk: {risk_level}] - Use .plan first, then .apply"