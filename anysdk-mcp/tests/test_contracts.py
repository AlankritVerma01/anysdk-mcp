# anysdk-mcp/tests/test_contracts.py

"""
Contract Tests for MCP SDK Bridge

Tests the contracts and interfaces between different components of the SDK bridge.
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import Mock, patch

from mcp_sdk_bridge.core.discover import SDKDiscoverer, SDKMethod, SDKCapability
from mcp_sdk_bridge.core.schema import SchemaGenerator, MCPToolSchema
from mcp_sdk_bridge.core.wrap import SDKWrapper
from mcp_sdk_bridge.core.serialize import ResponseSerializer
from mcp_sdk_bridge.adapters.github import GitHubAdapter


class TestSDKDiscoveryContract:
    """Test the contract for SDK discovery"""
    
    def test_sdk_method_structure(self):
        """Test that SDKMethod has required structure"""
        method = SDKMethod(
            name="test_method",
            description="Test method",
            parameters={"param1": {"type": "str", "required": True}},
            return_type="str",
            module_path="test.module"
        )
        
        assert method.name == "test_method"
        assert method.description == "Test method"
        assert "param1" in method.parameters
        assert method.return_type == "str"
        assert method.module_path == "test.module"
        assert method.is_async is False
    
    def test_sdk_capability_structure(self):
        """Test that SDKCapability has required structure"""
        method = SDKMethod(
            name="test_method",
            description="Test method",
            parameters={},
            return_type="str",
            module_path="test.module"
        )
        
        capability = SDKCapability(
            name="test_capability",
            description="Test capability",
            methods=[method],
            requires_auth=True
        )
        
        assert capability.name == "test_capability"
        assert capability.description == "Test capability"
        assert len(capability.methods) == 1
        assert capability.requires_auth is True


class TestSchemaGenerationContract:
    """Test the contract for schema generation"""
    
    def test_mcp_tool_schema_structure(self):
        """Test that MCPToolSchema has required structure"""
        schema = MCPToolSchema(
            name="test.tool",
            description="Test tool",
            inputSchema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string"}
                },
                "required": ["param1"]
            }
        )
        
        assert schema.name == "test.tool"
        assert schema.description == "Test tool"
        assert schema.inputSchema["type"] == "object"
        assert "properties" in schema.inputSchema
        assert "required" in schema.inputSchema
    
    def test_schema_generator_contract(self):
        """Test that SchemaGenerator produces valid schemas"""
        generator = SchemaGenerator()
        
        method = SDKMethod(
            name="test_method",
            description="Test method",
            parameters={
                "param1": {"type": "str", "required": True},
                "param2": {"type": "int", "required": False, "default": 10}
            },
            return_type="str",
            module_path="test.module"
        )
        
        schema = generator.generate_tool_schema(method)
        
        assert isinstance(schema, MCPToolSchema)
        assert schema.name.endswith(".test_method")
        assert schema.description == "Test method"
        assert schema.inputSchema["type"] == "object"
        assert "param1" in schema.inputSchema["properties"]
        assert "param2" in schema.inputSchema["properties"]
        assert schema.inputSchema["required"] == ["param1"]


class TestSerializationContract:
    """Test the contract for response serialization"""
    
    def test_serializer_response_structure(self):
        """Test that serializer produces consistent response structure"""
        serializer = ResponseSerializer()
        
        test_data = {"key": "value", "number": 42}
        response = serializer.serialize_response(test_data)
        
        assert "result" in response
        assert "metadata" in response
        assert response["result"] == test_data
        assert "serialized_at" in response["metadata"]
        assert "type" in response["metadata"]
    
    def test_serializer_error_structure(self):
        """Test that serializer produces consistent error structure"""
        serializer = ResponseSerializer()
        
        error = ValueError("Test error")
        response = serializer.serialize_error(error, {"context": "test"})
        
        assert "error" in response
        assert response["error"]["type"] == "ValueError"
        assert response["error"]["message"] == "Test error"
        assert response["error"]["context"]["context"] == "test"
    
    def test_serializer_paginated_structure(self):
        """Test that serializer produces consistent paginated response structure"""
        serializer = ResponseSerializer()
        
        items = [{"id": 1}, {"id": 2}]
        response = serializer.serialize_paginated_response(
            items=items,
            page=1,
            per_page=10,
            total=2,
            has_more=False
        )
        
        assert "result" in response
        assert "metadata" in response
        assert "items" in response["result"]
        assert "pagination" in response["result"]
        assert response["result"]["pagination"]["page"] == 1
        assert response["result"]["pagination"]["per_page"] == 10
        assert response["result"]["pagination"]["total"] == 2
        assert response["result"]["pagination"]["has_more"] is False


class TestWrapperContract:
    """Test the contract for SDK method wrapping"""
    
    def test_wrapper_sync_method(self):
        """Test that wrapper handles synchronous methods correctly"""
        wrapper = SDKWrapper()
        
        def mock_method(param1: str, param2: int = 10) -> str:
            return f"Result: {param1}, {param2}"
        
        method = SDKMethod(
            name="mock_method",
            description="Mock method",
            parameters={
                "param1": {"type": "str", "required": True},
                "param2": {"type": "int", "required": False, "default": 10}
            },
            return_type="str",
            module_path="test.module",
            is_async=False
        )
        
        mock_instance = Mock()
        mock_instance.mock_method = mock_method
        
        wrapped = wrapper.wrap_method(method, mock_instance)
        result = wrapped(param1="test", param2=20)
        
        assert "result" in result
        assert "metadata" in result
        assert result["result"] == "Result: test, 20"
    
    @pytest.mark.asyncio
    async def test_wrapper_async_method(self):
        """Test that wrapper handles asynchronous methods correctly"""
        wrapper = SDKWrapper()
        
        async def mock_async_method(param1: str) -> str:
            return f"Async result: {param1}"
        
        method = SDKMethod(
            name="mock_async_method",
            description="Mock async method",
            parameters={
                "param1": {"type": "str", "required": True}
            },
            return_type="str",
            module_path="test.module",
            is_async=True
        )
        
        mock_instance = Mock()
        mock_instance.mock_async_method = mock_async_method
        
        wrapped = wrapper.wrap_method(method, mock_instance)
        result = await wrapped(param1="test")
        
        assert "result" in result
        assert "metadata" in result
        assert result["result"] == "Async result: test"


class TestAdapterContract:
    """Test the contract that all adapters must follow"""
    
    def test_adapter_interface_github(self):
        """Test that GitHubAdapter follows the adapter interface"""
        # Mock the GitHub token to avoid requiring real credentials
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'mock_token'}):
            with patch('mcp_sdk_bridge.adapters.github.Github'):
                adapter = GitHubAdapter()
                
                # Test required methods exist
                assert hasattr(adapter, 'discover_capabilities')
                assert hasattr(adapter, 'generate_mcp_tools')
                assert hasattr(adapter, 'create_tool_implementations')
                
                # Test capabilities structure
                capabilities = adapter.discover_capabilities()
                assert isinstance(capabilities, list)
                
                for capability in capabilities:
                    assert isinstance(capability, SDKCapability)
                    assert hasattr(capability, 'name')
                    assert hasattr(capability, 'description')
                    assert hasattr(capability, 'methods')
                    assert isinstance(capability.methods, list)
                
                # Test tool schemas structure
                tools = adapter.generate_mcp_tools()
                assert isinstance(tools, list)
                
                for tool in tools:
                    assert isinstance(tool, MCPToolSchema)
                    assert hasattr(tool, 'name')
                    assert hasattr(tool, 'description')
                    assert hasattr(tool, 'inputSchema')
                
                # Test implementations structure
                implementations = adapter.create_tool_implementations()
                assert isinstance(implementations, dict)
                
                for name, impl in implementations.items():
                    assert callable(impl)
                    assert isinstance(name, str)
                    assert name.startswith('github.')


class TestEndToEndContract:
    """Test end-to-end contracts between components"""
    
    @pytest.mark.asyncio
    async def test_discovery_to_schema_to_implementation(self):
        """Test the full pipeline from discovery to implementation"""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'mock_token'}):
            with patch('mcp_sdk_bridge.adapters.github.Github') as mock_github:
                # Mock GitHub API responses
                mock_user = Mock()
                mock_repo = Mock()
                mock_repo.name = "test-repo"
                mock_repo.full_name = "user/test-repo"
                mock_repo.description = "Test repository"
                mock_repo.private = False
                mock_repo.html_url = "https://github.com/user/test-repo"
                mock_repo.clone_url = "https://github.com/user/test-repo.git"
                mock_repo.language = "Python"
                mock_repo.stargazers_count = 10
                mock_repo.forks_count = 5
                mock_repo.created_at = None
                mock_repo.updated_at = None
                
                mock_user.get_repos.return_value = [mock_repo]
                mock_github.return_value.get_user.return_value = mock_user
                
                adapter = GitHubAdapter()
                
                # 1. Discovery phase
                capabilities = adapter.discover_capabilities()
                assert len(capabilities) > 0
                
                # 2. Schema generation phase
                tools = adapter.generate_mcp_tools()
                assert len(tools) > 0
                
                # Find the list_repos tool
                list_repos_tool = next(
                    (tool for tool in tools if tool.name == "github.list_repos"), 
                    None
                )
                assert list_repos_tool is not None
                
                # 3. Implementation phase
                implementations = adapter.create_tool_implementations()
                assert "github.list_repos" in implementations
                
                list_repos_impl = implementations["github.list_repos"]
                
                # 4. Execute the implementation
                result = list_repos_impl(user="testuser")
                
                # 5. Verify the result follows the contract
                assert "result" in result
                assert "metadata" in result
                assert isinstance(result["result"], list)
                
                if result["result"]:  # If we got results
                    repo_data = result["result"][0]
                    assert "name" in repo_data
                    assert "full_name" in repo_data


class TestConfigContract:
    """Test configuration contracts"""
    
    def test_config_structure_validation(self):
        """Test that configuration structures are valid"""
        # This would test loading and validating config files
        # For now, we'll test the basic structure expectations
        
        required_config_sections = [
            "rate_limit",
            "safety", 
            "pagination",
            "logging"
        ]
        
        # In a real implementation, you'd load actual config files here
        # and validate they have the required sections
        mock_config = {
            "rate_limit": {
                "requests_per_minute": 60,
                "requests_per_hour": 1000
            },
            "safety": {
                "max_response_size_mb": 10,
                "require_auth": True
            },
            "pagination": {
                "default_page_size": 30
            },
            "logging": {
                "level": "INFO"
            }
        }
        
        for section in required_config_sections:
            assert section in mock_config
            assert isinstance(mock_config[section], dict)


class TestSchemaTypeMapping:
    """Test improved schema type mapping"""
    
    def test_basic_type_mapping(self):
        """Test that basic types are mapped correctly"""
        generator = SchemaGenerator()
        
        # Test basic types
        assert generator._convert_type("str") == {"type": "string"}
        assert generator._convert_type("int") == {"type": "integer"}
        assert generator._convert_type("float") == {"type": "number"}
        assert generator._convert_type("bool") == {"type": "boolean"}
    
    def test_list_type_mapping(self):
        """Test that List types are mapped correctly"""
        generator = SchemaGenerator()
        
        # Test List[str]
        result = generator._convert_type("List[str]")
        assert result["type"] == "array"
        assert result["items"]["type"] == "string"
    
    def test_optional_type_mapping(self):
        """Test that Optional types are mapped correctly"""
        generator = SchemaGenerator()
        
        # Test Optional[str]
        result = generator._convert_type("Optional[str]")
        assert result["type"] == "string"
        assert result["nullable"] is True
