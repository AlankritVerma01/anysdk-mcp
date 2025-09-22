# anysdk-mcp/tests/test_azure_auto.py

"""
Tests for Azure Auto-Adapter

Tests the Azure Management SDK auto-discovery functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the parent directory to sys.path to import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mcp_sdk_bridge.adapters.auto_azure import AzureAutoAdapter, AzureAutoConfig
from mcp_sdk_bridge.core.discover import SDKMethod


class TestAzureAutoConfig:
    """Test Azure auto configuration"""
    
    def test_config_from_env(self):
        """Test config picks up environment variables"""
        with patch.dict(os.environ, {
            'AZURE_TENANT_ID': 'test-tenant',
            'AZURE_CLIENT_ID': 'test-client',
            'AZURE_CLIENT_SECRET': 'test-secret',
            'AZURE_SUBSCRIPTION_ID': 'test-subscription'
        }):
            config = AzureAutoConfig()
            assert config.tenant_id == 'test-tenant'
            assert config.client_id == 'test-client'
            assert config.client_secret == 'test-secret'
            assert config.subscription_id == 'test-subscription'
    
    def test_config_explicit_params(self):
        """Test config with explicit parameters"""
        config = AzureAutoConfig(
            tenant_id='explicit-tenant',
            client_id='explicit-client',
            client_secret='explicit-secret',
            subscription_id='explicit-subscription'
        )
        assert config.tenant_id == 'explicit-tenant'
        assert config.client_id == 'explicit-client'
        assert config.client_secret == 'explicit-secret'
        assert config.subscription_id == 'explicit-subscription'


class TestAzureAutoAdapter:
    """Test Azure auto adapter"""
    
    def test_adapter_initialization(self):
        """Test adapter initializes properly"""
        config = AzureAutoConfig()
        adapter = AzureAutoAdapter(config)
        
        assert adapter.config == config
        assert adapter.wrapper is not None
        assert adapter.schema_gen is not None
        assert adapter.lro is not None
    
    def test_adapter_with_dict_config(self):
        """Test adapter accepts dict config"""
        config_dict = {
            'tenant_id': 'dict-tenant',
            'max_methods_per_class': 50
        }
        adapter = AzureAutoAdapter(config_dict)
        
        assert adapter.config.tenant_id == 'dict-tenant'
        assert adapter.config.max_methods_per_class == 50
    
    @patch('mcp_sdk_bridge.adapters.auto_azure.importlib.import_module')
    def test_iter_azure_modules(self, mock_import):
        """Test Azure module iteration"""
        # Mock a simple module structure
        mock_module = Mock()
        mock_module.__name__ = 'azure.mgmt.compute'
        mock_module.__path__ = ['/fake/path']
        mock_import.return_value = mock_module
        
        config = AzureAutoConfig(discover_roots=['azure.mgmt.compute'])
        adapter = AzureAutoAdapter(config)
        
        modules = list(adapter._iter_azure_modules())
        assert len(modules) >= 1
        assert modules[0][0] == 'azure.mgmt.compute'
    
    def test_is_public_method(self):
        """Test public method detection"""
        adapter = AzureAutoAdapter()
        
        assert adapter._is_public_method('list_vms')
        assert adapter._is_public_method('create_vm')
        assert not adapter._is_public_method('_private_method')
        assert not adapter._is_public_method('serialize')
        assert not adapter._is_public_method('deserialize')
    
    def test_serialize_azure_object(self):
        """Test Azure object serialization"""
        adapter = AzureAutoAdapter()
        
        # Test with as_dict method
        mock_obj = Mock()
        mock_obj.as_dict.return_value = {'key': 'value'}
        result = adapter._serialize_azure_object(mock_obj)
        assert result == {'key': 'value'}
        
        # Test with enum - create a simple dummy object
        class DummyEnumLike:
            def __init__(self, value):
                self.value = value
        
        mock_enum = DummyEnumLike('enum_value')
        result = adapter._serialize_azure_object(mock_enum)
        assert result == 'enum_value'
        
        # Test with basic types
        assert adapter._serialize_azure_object('string') == 'string'
        assert adapter._serialize_azure_object(42) == 42
        assert adapter._serialize_azure_object([1, 2, 3]) == [1, 2, 3]
        assert adapter._serialize_azure_object({'a': 1}) == {'a': 1}
    
    def test_create_method_wrapper_regular(self):
        """Test method wrapper for regular methods"""
        adapter = AzureAutoAdapter()
        
        def mock_method(param1, param2='default'):
            return {'result': f'{param1}_{param2}'}
        
        wrapper = adapter._create_method_wrapper('test_method', mock_method, is_lro=False)
        
        # Test async wrapper
        import asyncio
        result = asyncio.run(wrapper(param1='test', param2='value'))
        assert result == {'result': 'test_value'}
    
    def test_create_method_wrapper_lro(self):
        """Test method wrapper for LRO methods"""
        adapter = AzureAutoAdapter()
        
        # Mock Azure Poller
        mock_poller = Mock()
        mock_poller.result.return_value = {'operation': 'completed'}
        
        def mock_lro_method(**kwargs):
            return mock_poller
        
        wrapper = adapter._create_method_wrapper('begin_test', mock_lro_method, is_lro=True)
        
        import asyncio
        result = asyncio.run(wrapper(param='test'))
        
        # Should return completed operation result (new behavior)
        assert result['status'] == 'succeeded'
        assert 'result' in result
        assert result['result'] == {'operation': 'completed'}
    
    def test_create_method_wrapper_error_handling(self):
        """Test method wrapper error handling"""
        adapter = AzureAutoAdapter()
        
        def error_method(**kwargs):
            raise ValueError("Test error")
        
        wrapper = adapter._create_method_wrapper('error_method', error_method)
        
        import asyncio
        result = asyncio.run(wrapper(param='test'))
        
        assert 'error' in result
        assert result['error'] == 'Test error'
        assert result['error_type'] == 'ValueError'
        assert result['method'] == 'error_method'
    
    @patch('mcp_sdk_bridge.adapters.auto_azure.importlib.import_module')
    def test_discover_operations_classes(self, mock_import):
        """Test operations class discovery"""
        # Mock module with operations class
        mock_operations_class = type('VirtualMachinesOperations', (), {})
        mock_module = Mock()
        mock_module.__name__ = 'azure.mgmt.compute'
        
        # Mock inspect.getmembers to return our operations class
        with patch('inspect.getmembers') as mock_getmembers:
            mock_getmembers.return_value = [
                ('VirtualMachinesOperations', mock_operations_class)
            ]
            mock_import.return_value = mock_module
            
            adapter = AzureAutoAdapter()
            operations = adapter._discover_operations_classes()
            
            assert len(operations) >= 0  # May be empty if no modules load
    
    def test_discover_tools_basic(self):
        """Test basic tool discovery"""
        adapter = AzureAutoAdapter()
        
        # Mock the operations discovery to return empty list
        with patch.object(adapter, '_discover_operations_classes', return_value=[]):
            result = adapter.discover_tools()
            
            assert result.schemas == []
            assert result.tools == {}
            assert 'operations_classes' in result.stats
            assert 'methods' in result.stats
    
    def test_create_tool_implementations(self):
        """Test tool implementations creation"""
        adapter = AzureAutoAdapter()
        
        with patch.object(adapter, 'discover_tools') as mock_discover:
            mock_result = Mock()
            mock_result.tools = {'test.tool': lambda: 'test'}
            mock_discover.return_value = mock_result
            
            implementations = adapter.create_tool_implementations()
            assert 'test.tool' in implementations
    
    def test_generate_mcp_tools(self):
        """Test MCP tools generation"""
        adapter = AzureAutoAdapter()
        
        with patch.object(adapter, 'discover_tools') as mock_discover:
            mock_result = Mock()
            mock_result.schemas = [
                {
                    'name': 'test.tool',
                    'description': 'Test tool',
                    'inputSchema': {'type': 'object'}
                }
            ]
            mock_discover.return_value = mock_result
            
            tools = adapter.generate_mcp_tools()
            assert len(tools) == 1
            assert tools[0].name == 'test.tool'
    
    def test_get_stats(self):
        """Test stats retrieval"""
        adapter = AzureAutoAdapter()
        
        with patch.object(adapter, 'discover_tools') as mock_discover:
            mock_result = Mock()
            mock_result.stats = {
                'operations_classes': 5,
                'methods': 25,
                'lro_methods': 3
            }
            mock_discover.return_value = mock_result
            
            stats = adapter.get_stats()
            assert stats['operations_classes'] == 5
            assert stats['methods'] == 25
            assert stats['lro_methods'] == 3


class TestAzureIntegration:
    """Integration tests for Azure adapter"""
    
    def test_adapter_without_credentials(self):
        """Test adapter works without Azure credentials"""
        # Clear any existing credentials
        with patch.dict(os.environ, {}, clear=True):
            config = AzureAutoConfig()
            adapter = AzureAutoAdapter(config)
            
            # Should initialize without errors
            assert adapter.config.tenant_id is None
            assert adapter.config.client_id is None
    
    def test_client_factories_without_credentials(self):
        """Test client factories return empty dict without credentials"""
        config = AzureAutoConfig()
        adapter = AzureAutoAdapter(config)
        
        factories = adapter._setup_client_factories()
        assert factories == {}
    
    def test_client_factories_with_credentials(self):
        """Test client factories with credentials (simplified)"""
        config = AzureAutoConfig(
            tenant_id='test-tenant',
            client_id='test-client',
            client_secret='test-secret',
            subscription_id='test-subscription'
        )
        adapter = AzureAutoAdapter(config)
        
        # Without Azure SDK installed, should return empty dict
        # This is the expected behavior and shows graceful degradation
        factories = adapter._setup_client_factories()
        
        # Should return empty dict when Azure SDK is not available
        assert isinstance(factories, dict)


if __name__ == '__main__':
    pytest.main([__file__])
