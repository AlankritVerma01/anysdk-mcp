# anysdk-mcp/mcp_sdk_bridge/core/schema.py

"""
Schema Generation Module

Converts SDK method signatures and types into MCP tool schemas.
"""

from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
import json
from .discover import SDKMethod, SDKCapability


@dataclass
class MCPToolSchema:
    """MCP Tool schema representation"""
    name: str
    description: str
    inputSchema: Dict[str, Any]


class SchemaGenerator:
    """Generates MCP tool schemas from SDK methods"""
    
    def __init__(self):
        self.type_mappings = {
            "str": {"type": "string"},
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "list": {"type": "array"},
            "dict": {"type": "object"},
            "Any": {"type": "string", "description": "Any type (as string)"},
        }
    
    def generate_tool_schema(self, method: SDKMethod) -> MCPToolSchema:
        """Generate MCP tool schema from SDK method"""
        properties = {}
        required = []
        
        for param_name, param_info in method.parameters.items():
            # Skip 'self' parameter
            if param_name == "self":
                continue
                
            param_type = self._convert_type(param_info["type"])
            properties[param_name] = param_type.copy()
            
            if param_info["required"]:
                required.append(param_name)
            elif param_info["default"] is not None:
                properties[param_name]["default"] = param_info["default"]
        
        input_schema = {
            "type": "object",
            "properties": properties
        }
        
        if required:
            input_schema["required"] = required
        
        return MCPToolSchema(
            name=self._generate_tool_name(method),
            description=method.description,
            inputSchema=input_schema
        )
    
    def _convert_type(self, python_type: str) -> Dict[str, Any]:
        """Convert Python type to JSON schema type"""
        # Handle generic types like List[str], Dict[str, int], etc.
        if "[" in python_type and "]" in python_type:
            base_type = python_type.split("[")[0]
            if base_type == "List":
                return {"type": "array", "items": {"type": "string"}}
            elif base_type == "Dict":
                return {"type": "object"}
            elif base_type == "Optional":
                inner_type = python_type[python_type.find("[")+1:python_type.rfind("]")]
                converted = self._convert_type(inner_type)
                converted["nullable"] = True
                return converted
        
        # Handle Union types
        if python_type.startswith("Union["):
            return {"type": "string", "description": f"Union type: {python_type}"}
        
        # Simple type mapping
        return self.type_mappings.get(python_type, {"type": "string"})
    
    def _generate_tool_name(self, method: SDKMethod) -> str:
        """Generate a tool name from method info"""
        # Extract SDK name from module path
        sdk_name = method.module_path.split(".")[0] if "." in method.module_path else "sdk"
        return f"{sdk_name.lower()}.{method.name}"
    
    def generate_schemas_for_capability(self, capability: SDKCapability) -> List[MCPToolSchema]:
        """Generate schemas for all methods in a capability"""
        schemas = []
        for method in capability.methods:
            schema = self.generate_tool_schema(method)
            schemas.append(schema)
        return schemas
    
    def export_schemas_json(self, schemas: List[MCPToolSchema]) -> str:
        """Export schemas as JSON string"""
        schema_dicts = []
        for schema in schemas:
            schema_dicts.append({
                "name": schema.name,
                "description": schema.description,
                "inputSchema": schema.inputSchema
            })
        return json.dumps(schema_dicts, indent=2)
