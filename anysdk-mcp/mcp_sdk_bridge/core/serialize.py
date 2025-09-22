# anysdk-mcp/mcp_sdk_bridge/core/serialize.py

"""
Response Serialization Module

Handles serialization of SDK responses into MCP-compatible formats.
"""

from typing import Any, Dict, List, Union
import json
from datetime import datetime, date
from decimal import Decimal
from dataclasses import is_dataclass, asdict
from enum import Enum


class ResponseSerializer:
    """Serializes SDK responses for MCP compatibility"""
    
    def __init__(self, max_depth: int = 10):
        self.max_depth = max_depth
    
    def serialize_response(self, data: Any, depth: int = 0) -> Dict[str, Any]:
        """Serialize response data into MCP format"""
        if depth > self.max_depth:
            return {"error": "Maximum serialization depth exceeded"}
        
        try:
            serialized = self._serialize_value(data, depth)
            return {
                "result": serialized,
                "metadata": {
                    "serialized_at": datetime.utcnow().isoformat(),
                    "type": type(data).__name__
                }
            }
        except Exception as e:
            return {
                "error": {
                    "type": "SerializationError",
                    "message": str(e),
                    "data_type": type(data).__name__
                }
            }
    
    def _serialize_value(self, value: Any, depth: int = 0) -> Any:
        """Recursively serialize a value"""
        if depth > self.max_depth:
            return f"<max_depth_exceeded: {type(value).__name__}>"
        
        # Handle None
        if value is None:
            return None
        
        # Handle basic types
        if isinstance(value, (str, int, float, bool)):
            return value
        
        # Handle datetime objects
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        
        # Handle Decimal
        if isinstance(value, Decimal):
            return float(value)
        
        # Handle Enum
        if isinstance(value, Enum):
            return value.value
        
        # Handle dataclasses
        if is_dataclass(value):
            return self._serialize_value(asdict(value), depth + 1)
        
        # Handle dictionaries
        if isinstance(value, dict):
            return {
                str(k): self._serialize_value(v, depth + 1) 
                for k, v in value.items()
            }
        
        # Handle lists and tuples
        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(item, depth + 1) for item in value]
        
        # Handle objects with __dict__
        if hasattr(value, '__dict__'):
            return self._serialize_value(value.__dict__, depth + 1)
        
        # Handle objects with custom serialization
        if hasattr(value, 'to_dict'):
            return self._serialize_value(value.to_dict(), depth + 1)
        
        if hasattr(value, '__json__'):
            return self._serialize_value(value.__json__(), depth + 1)
        
        # Fallback to string representation
        return str(value)
    
    def serialize_paginated_response(self, 
                                   items: List[Any], 
                                   page: int = 1, 
                                   per_page: int = 100,
                                   total: int = None,
                                   has_more: bool = False) -> Dict[str, Any]:
        """Serialize paginated response"""
        serialized_items = [self._serialize_value(item) for item in items]
        
        return {
            "result": {
                "items": serialized_items,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "has_more": has_more,
                    "count": len(serialized_items)
                }
            },
            "metadata": {
                "serialized_at": datetime.utcnow().isoformat(),
                "type": "paginated_response"
            }
        }
    
    def serialize_streaming_chunk(self, chunk: Any, chunk_id: str = None) -> Dict[str, Any]:
        """Serialize a streaming response chunk"""
        return {
            "chunk": {
                "id": chunk_id or str(datetime.utcnow().timestamp()),
                "data": self._serialize_value(chunk),
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    
    def serialize_error(self, error: Exception, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Serialize error responses"""
        return {
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "context": context or {},
                "timestamp": datetime.utcnow().isoformat()
            }
        }


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for complex types"""
    
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, Enum):
            return obj.value
        if is_dataclass(obj):
            return asdict(obj)
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        if hasattr(obj, '__json__'):
            return obj.__json__()
        return super().default(obj)
