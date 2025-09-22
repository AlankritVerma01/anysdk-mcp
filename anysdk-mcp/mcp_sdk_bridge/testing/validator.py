# anysdk-mcp/mcp_sdk_bridge/testing/validator.py

"""
Tool Validation System

Provides automated testing and validation for MCP tools.
"""

import inspect
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from ..core.discover import SDKMethod


@dataclass
class ValidationResult:
    """Result of tool validation"""
    tool_name: str
    success: bool
    error: Optional[str] = None
    suggested_fix: Optional[str] = None
    example_usage: Optional[Dict[str, Any]] = None


class ToolValidator:
    """Validates MCP tools and suggests fixes"""
    
    def __init__(self):
        self.validation_cache: Dict[str, ValidationResult] = {}
    
    def validate_tool_schema(self, method: SDKMethod, schema: Dict[str, Any]) -> ValidationResult:
        """Validate that a tool schema matches the method signature"""
        tool_name = f"github.{method.name}"
        
        try:
            # Check if all required parameters are in schema
            schema_props = schema.get("properties", {})
            required_params = schema.get("required", [])
            
            method_required = [
                name for name, info in method.parameters.items() 
                if info.get("required", False)
            ]
            
            missing_required = set(method_required) - set(required_params)
            if missing_required:
                return ValidationResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Missing required parameters in schema: {missing_required}",
                    suggested_fix=f"Add required parameters: {list(missing_required)}"
                )
            
            # Generate example usage
            example = self._generate_example_usage(method)
            
            return ValidationResult(
                tool_name=tool_name,
                success=True,
                example_usage=example
            )
            
        except Exception as e:
            return ValidationResult(
                tool_name=tool_name,
                success=False,
                error=f"Schema validation error: {str(e)}"
            )
    
    def _generate_example_usage(self, method: SDKMethod) -> Dict[str, Any]:
        """Generate example usage for a method"""
        example = {}
        
        for param_name, param_info in method.parameters.items():
            param_type = param_info.get("type", "str")
            
            # Generate example values based on parameter name and type
            if "query" in param_name.lower():
                example[param_name] = "python"
            elif "name" in param_name.lower():
                example[param_name] = "example-repo"
            elif "user" in param_name.lower():
                example[param_name] = "octocat"
            elif "owner" in param_name.lower():
                example[param_name] = "github"
            elif "repo" in param_name.lower():
                example[param_name] = "Hello-World"
            elif param_type == "bool":
                example[param_name] = False
            elif param_type == "int":
                example[param_name] = 10
            elif param_type == "str":
                example[param_name] = f"example_{param_name}"
            else:
                example[param_name] = f"<{param_type}>"
        
        return example
    
    def validate_all_tools(self, adapter) -> List[ValidationResult]:
        """Validate all tools from an adapter"""
        results = []
        
        try:
            methods = adapter.discovered_methods
            schemas = adapter.generate_mcp_tools()
            
            schema_map = {schema.name: schema.inputSchema for schema in schemas}
            
            for method in methods:
                tool_name = f"github.{method.name}"
                if tool_name in schema_map:
                    result = self.validate_tool_schema(method, schema_map[tool_name])
                    results.append(result)
        
        except Exception as e:
            results.append(ValidationResult(
                tool_name="validation_error",
                success=False,
                error=f"Failed to validate tools: {str(e)}"
            ))
        
        return results


class ToolTester:
    """Tests MCP tools with safe example inputs"""
    
    def __init__(self, adapter):
        self.adapter = adapter
        self.validator = ToolValidator()
    
    def test_tool_safely(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Test a tool with given parameters safely"""
        try:
            implementations = self.adapter.create_tool_implementations()
            
            if tool_name not in implementations:
                return {
                    "success": False,
                    "error": f"Tool {tool_name} not found",
                    "available_tools": list(implementations.keys())[:10]
                }
            
            # Get the tool implementation
            tool_impl = implementations[tool_name]
            
            # Test with safe parameters (read-only operations only)
            if self._is_safe_to_test(tool_name):
                result = tool_impl(**params)
                return {
                    "success": True,
                    "result": result,
                    "tool_name": tool_name,
                    "parameters_used": params
                }
            else:
                return {
                    "success": False,
                    "error": f"Tool {tool_name} is not safe to test automatically (write operation)",
                    "suggestion": "Use plan/apply pattern for write operations"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "tool_name": tool_name,
                "parameters_used": params
            }
    
    def _is_safe_to_test(self, tool_name: str) -> bool:
        """Check if a tool is safe to test (read-only)"""
        unsafe_patterns = [
            "create", "delete", "update", "modify", "edit", "remove", "add",
            "post", "put", "patch", "fork", "clone", "push", "merge"
        ]
        
        tool_lower = tool_name.lower()
        return not any(pattern in tool_lower for pattern in unsafe_patterns)
    
    def run_tool_health_check(self) -> Dict[str, Any]:
        """Run a comprehensive health check on all tools"""
        results = {
            "total_tools": 0,
            "valid_tools": 0,
            "invalid_tools": 0,
            "safe_to_test": 0,
            "test_results": [],
            "validation_errors": []
        }
        
        try:
            # Validate all tools
            validation_results = self.validator.validate_all_tools(self.adapter)
            results["total_tools"] = len(validation_results)
            
            for validation in validation_results:
                if validation.success:
                    results["valid_tools"] += 1
                    
                    # Try to test safe tools
                    if self._is_safe_to_test(validation.tool_name) and validation.example_usage:
                        test_result = self.test_tool_safely(
                            validation.tool_name, 
                            validation.example_usage
                        )
                        results["test_results"].append(test_result)
                        
                        if test_result.get("success"):
                            results["safe_to_test"] += 1
                else:
                    results["invalid_tools"] += 1
                    results["validation_errors"].append({
                        "tool": validation.tool_name,
                        "error": validation.error,
                        "fix": validation.suggested_fix
                    })
        
        except Exception as e:
            results["error"] = f"Health check failed: {str(e)}"
        
        return results
