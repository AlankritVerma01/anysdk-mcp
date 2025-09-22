# anysdk-mcp/mcp_sdk_bridge/core/schema.py

"""
Schema Generation Module

Converts SDK method signatures and types into MCP tool schemas.
"""

from typing import Dict, Any, List, Optional, Union, get_type_hints, get_origin, get_args
from dataclasses import dataclass
import json
import inspect
import re
from datetime import datetime, date
from pathlib import Path
from enum import Enum
from .discover import SDKMethod, SDKCapability


@dataclass
class MCPToolSchema:
    """MCP Tool schema representation"""
    name: str
    description: str
    inputSchema: Dict[str, Any]


class SchemaGenerator:
    """Generates MCP tool schemas from SDK methods with rich type support"""
    
    def __init__(self):
        self.type_mappings = {
            "str": {"type": "string"},
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "list": {"type": "array"},
            "dict": {"type": "object"},
            "Any": {"type": "string", "description": "Any type (as string)"},
            # Enhanced type mappings
            "datetime": {"type": "string", "format": "date-time"},
            "date": {"type": "string", "format": "date"},
            "Path": {"type": "string", "format": "path"},
            "pathlib.Path": {"type": "string", "format": "path"},
            "bytes": {"type": "string", "format": "byte"},
            "UUID": {"type": "string", "format": "uuid"},
        }
    
    def _parse_docstring(self, docstring: Optional[str]) -> Dict[str, Any]:
        """Parse docstring to extract parameter descriptions and overall description"""
        if not docstring:
            return {"description": "", "param_descriptions": {}}
        
        # Clean up docstring
        lines = [line.strip() for line in docstring.strip().split('\n')]
        
        # Extract main description (everything before parameters section)
        description_lines = []
        param_descriptions = {}
        
        in_params_section = False
        current_param = None
        
        for line in lines:
            if not line:
                continue
                
            # Check for parameter sections (Google, NumPy, or Sphinx style)
            if re.match(r'^(Parameters?|Args?|Arguments?):', line, re.IGNORECASE):
                in_params_section = True
                continue
            elif re.match(r'^(Returns?|Return|Yields?|Raises?|Examples?|Note):', line, re.IGNORECASE):
                in_params_section = False
                continue
            
            if in_params_section:
                # Google style: param_name (type): description
                google_match = re.match(r'^\s*(\w+)\s*\([^)]*\):\s*(.+)', line)
                if google_match:
                    param_name, param_desc = google_match.groups()
                    param_descriptions[param_name] = param_desc.strip()
                    current_param = param_name
                    continue
                
                # Sphinx style: :param param_name: description
                sphinx_match = re.match(r'^\s*:param\s+(\w+):\s*(.+)', line)
                if sphinx_match:
                    param_name, param_desc = sphinx_match.groups()
                    param_descriptions[param_name] = param_desc.strip()
                    current_param = param_name
                    continue
                
                # NumPy style: param_name : type
                numpy_match = re.match(r'^\s*(\w+)\s*:\s*(.+)', line)
                if numpy_match:
                    param_name, param_desc = numpy_match.groups()
                    param_descriptions[param_name] = param_desc.strip()
                    current_param = param_name
                    continue
                
                # Continuation of previous parameter description
                if current_param and line.startswith('    '):
                    param_descriptions[current_param] += ' ' + line.strip()
                    continue
            
            if not in_params_section:
                description_lines.append(line)
        
        return {
            "description": ' '.join(description_lines).strip(),
            "param_descriptions": param_descriptions
        }
    
    def _analyze_type_annotation(self, annotation: Any) -> Dict[str, Any]:
        """Analyze type annotation to create rich JSON schema"""
        if annotation is None or annotation == inspect.Parameter.empty:
            return {"type": "string"}
        
        # Handle string type annotations (common in older Python)
        if isinstance(annotation, str):
            return self._convert_type(annotation)
        
        # Get origin and args for generic types
        origin = get_origin(annotation)
        args = get_args(annotation)
        
        # Handle Union types (including Optional)
        if origin is Union:
            if len(args) == 2 and type(None) in args:
                # This is Optional[T]
                non_none_type = args[0] if args[1] is type(None) else args[1]
                schema = self._analyze_type_annotation(non_none_type)
                schema["nullable"] = True
                return schema
            else:
                # General Union - use anyOf
                return {
                    "anyOf": [self._analyze_type_annotation(arg) for arg in args]
                }
        
        # Handle List/Sequence types
        if origin in (list, List):
            item_type = args[0] if args else str
            return {
                "type": "array",
                "items": self._analyze_type_annotation(item_type)
            }
        
        # Handle Dict types
        if origin in (dict, Dict):
            if len(args) >= 2:
                return {
                    "type": "object",
                    "additionalProperties": self._analyze_type_annotation(args[1])
                }
            return {"type": "object"}
        
        # Handle Enum types
        if inspect.isclass(annotation) and issubclass(annotation, Enum):
            return {
                "type": "string",
                "enum": [e.value for e in annotation],
                "description": f"Enum values: {', '.join(str(e.value) for e in annotation)}"
            }
        
        # Handle basic types
        if annotation == str:
            return {"type": "string"}
        elif annotation == int:
            return {"type": "integer"}
        elif annotation == float:
            return {"type": "number"}
        elif annotation == bool:
            return {"type": "boolean"}
        elif annotation == datetime:
            return {"type": "string", "format": "date-time"}
        elif annotation == date:
            return {"type": "string", "format": "date"}
        elif annotation in (Path, "pathlib.Path"):
            return {"type": "string", "format": "path"}
        
        # Fallback to string representation
        return {"type": "string", "description": f"Type: {annotation}"}
    
    def _extract_function_signature(self, func: Any) -> Dict[str, Any]:
        """Extract enhanced parameter information from function signature"""
        try:
            sig = inspect.signature(func)
            type_hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
            
            params = {}
            for name, param in sig.parameters.items():
                if name == 'self':
                    continue
                
                # Get type from hints or annotation
                param_type = type_hints.get(name, param.annotation)
                type_schema = self._analyze_type_annotation(param_type)
                
                # Handle default values
                has_default = param.default != inspect.Parameter.empty
                default_value = param.default if has_default else None
                
                # Convert certain default values to JSON-serializable
                if default_value is not None:
                    if isinstance(default_value, (datetime, date)):
                        default_value = default_value.isoformat()
                    elif isinstance(default_value, Path):
                        default_value = str(default_value)
                    elif isinstance(default_value, Enum):
                        default_value = default_value.value
                
                params[name] = {
                    "type": param_type,
                    "required": not has_default,
                    "default": default_value,
                    "schema": type_schema
                }
            
            return params
        except Exception:
            # Fallback to basic parameter extraction
            return {}
    
    def generate_tool_schema(self, method: SDKMethod) -> MCPToolSchema:
        """Generate enhanced MCP tool schema from SDK method"""
        properties = {}
        required = []
        
        # Parse docstring for richer descriptions
        docstring_info = self._parse_docstring(method.description)
        param_descriptions = docstring_info["param_descriptions"]
        main_description = docstring_info["description"] or method.description
        
        # Try to extract enhanced signature info if method has a function reference
        enhanced_params = {}
        if hasattr(method, 'function') and method.function:
            enhanced_params = self._extract_function_signature(method.function)
        
        for param_name, param_info in method.parameters.items():
            # Skip 'self' parameter
            if param_name == "self":
                continue
            
            # Use enhanced type analysis if available
            if param_name in enhanced_params:
                enhanced_param = enhanced_params[param_name]
                param_schema = enhanced_param["schema"]
                
                # Add description from docstring if available
                if param_name in param_descriptions:
                    param_schema["description"] = param_descriptions[param_name]
                
                # Add default value
                if enhanced_param["default"] is not None:
                    param_schema["default"] = enhanced_param["default"]
                
                properties[param_name] = param_schema
                
                if enhanced_param["required"]:
                    required.append(param_name)
            else:
                # Fallback to basic type conversion
                param_type = self._convert_type(param_info["type"])
                
                # Add description from docstring if available
                if param_name in param_descriptions:
                    param_type["description"] = param_descriptions[param_name]
                
                properties[param_name] = param_type.copy()
                
                # Skip **kwargs parameters from required list (they're always optional)
                if param_info["required"] and not param_info.get("is_kwargs", False):
                    required.append(param_name)
                elif param_info.get("default") is not None:
                    properties[param_name]["default"] = param_info["default"]
        
        # Handle **kwargs if present
        if any("**" in name for name in method.parameters.keys()):
            # Add additionalProperties to allow extra parameters
            input_schema = {
                "type": "object",
                "properties": properties,
                "additionalProperties": {
                    "type": "string",
                    "description": "Additional parameters supported by this method"
                }
            }
        else:
            input_schema = {
                "type": "object",
                "properties": properties
            }
        
        if required:
            input_schema["required"] = required
        
        return MCPToolSchema(
            name=self._generate_tool_name(method),
            description=main_description,
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
