# anysdk-mcp/mcp_sdk_bridge/core/classify.py

"""
Operation Type Classifier

Automatically classifies SDK methods as read or write operations.
"""

import re
from typing import Literal

# Common prefixes that indicate read operations
READ_PREFIXES = (
    "get", "list", "read", "watch", "describe", "search", "count", "head",
    "show", "find", "query", "fetch", "retrieve", "check", "verify", "validate"
)

# Common prefixes that indicate write operations  
WRITE_PREFIXES = (
    "create", "update", "replace", "patch", "delete", "remove", "add",
    "merge", "set", "put", "post", "apply", "exec", "scale", "start", "stop", 
    "restart", "deploy", "rollback", "edit", "modify", "change", "insert",
    "upsert", "save", "write", "upload", "push", "pull", "sync", "refresh"
)

OperationType = Literal["read", "write"]


def classify_method(name: str) -> OperationType:
    """
    Classify a method name as read or write operation.
    
    Args:
        name: Method name (e.g., "list_namespaced_pod", "create_deployment", "getUserRepos")
        
    Returns:
        "read" or "write" based on method name analysis
    """
    n = name.lower()
    
    # Handle k8s method names like list_namespaced_pod / read_namespaced_pod / create_namespaced_*
    for prefix in READ_PREFIXES:
        if n.startswith(prefix + "_") or n.startswith(prefix):
            return "read"
    
    for prefix in WRITE_PREFIXES:
        if n.startswith(prefix + "_") or n.startswith(prefix):
            return "write"
    
    # Heuristic: look for verbs anywhere in the name (camelCase / snake_case)
    write_pattern = r"(create|update|replace|patch|delete|remove|add|merge|apply|exec|scale|start|stop|restart|deploy|modify|change|edit|save|write|upload|push|sync)"
    if re.search(write_pattern, n):
        return "write"
    
    # Default to read for safety (better to require confirmation unnecessarily than to miss a destructive operation)
    return "read"


def is_destructive(name: str) -> bool:
    """
    Check if a method is potentially destructive (subset of write operations).
    
    Args:
        name: Method name
        
    Returns:
        True if the operation could be destructive
    """
    n = name.lower()
    destructive_patterns = r"(delete|remove|destroy|terminate|kill|drop|truncate|purge|wipe|clear)"
    return bool(re.search(destructive_patterns, n))


def get_operation_risk_level(name: str) -> Literal["low", "medium", "high"]:
    """
    Assess the risk level of an operation.
    
    Args:
        name: Method name
        
    Returns:
        Risk level: "low" (read), "medium" (write), "high" (destructive)
    """
    op_type = classify_method(name)
    
    if op_type == "read":
        return "low"
    elif is_destructive(name):
        return "high"
    else:
        return "medium"

