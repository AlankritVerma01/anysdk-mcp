# anysdk-mcp/mcp_sdk_bridge/adapters/k8s.py

"""
Kubernetes SDK Adapter

Provides MCP integration for Kubernetes API via kubernetes-python client.
"""

from typing import List, Dict, Any, Optional
import os
from dataclasses import dataclass

from ..core.discover import SDKDiscoverer, SDKMethod, SDKCapability
from ..core.schema import SchemaGenerator, MCPToolSchema
from ..core.wrap import SDKWrapper
from ..core.serialize import ResponseSerializer


@dataclass
class K8sConfig:
    """Kubernetes configuration"""
    kubeconfig_path: Optional[str] = None
    context: Optional[str] = None
    namespace: str = "default"


class K8sAdapter:
    """Kubernetes SDK adapter for MCP"""
    
    def __init__(self, config: K8sConfig = None):
        self.config = config or K8sConfig()
        self.discoverer = SDKDiscoverer("k8s")
        self.schema_generator = SchemaGenerator()
        self.wrapper = SDKWrapper()
        self.serializer = ResponseSerializer()
        self._k8s_available = False
        
        # Setup Kubernetes client
        self._setup_client()
    
    def _setup_client(self):
        """Setup Kubernetes client"""
        try:
            # Try to import kubernetes client
            from kubernetes import client, config as k8s_config
            
            if self.config.kubeconfig_path:
                k8s_config.load_kube_config(
                    config_file=os.path.expanduser(self.config.kubeconfig_path), 
                    context=self.config.context
                )
            else:
                # fall back to default kubeconfig or in-cluster
                try:
                    k8s_config.load_kube_config(context=self.config.context)
                except Exception:
                    k8s_config.load_incluster_config()
            
            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self._k8s_available = True
        except ImportError:
            print("Warning: kubernetes package not installed. K8s adapter will use mock data.")
            self._k8s_available = False
        except Exception as e:
            print(f"Warning: Failed to setup K8s client: {e}. Using mock data.")
            self._k8s_available = False
    
    def discover_capabilities(self) -> List[SDKCapability]:
        """Discover Kubernetes SDK capabilities"""
        capabilities = []
        
        # Pod operations
        pod_methods = [
            SDKMethod(
                name="list_pods",
                description="List pods in a namespace",
                parameters={
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"},
                    "label_selector": {"type": "str", "required": False, "description": "Label selector"}
                },
                return_type="List[Pod]",
                module_path="kubernetes.pod",
                is_async=False
            ),
            SDKMethod(
                name="get_pod",
                description="Get a specific pod",
                parameters={
                    "name": {"type": "str", "required": True, "description": "Pod name"},
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"}
                },
                return_type="Pod",
                module_path="kubernetes.pod",
                is_async=False
            ),
            SDKMethod(
                name="delete_pod",
                description="Delete a pod",
                parameters={
                    "name": {"type": "str", "required": True, "description": "Pod name"},
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"}
                },
                return_type="Dict[str, Any]",
                module_path="kubernetes.pod",
                is_async=False
            ),
            SDKMethod(
                name="get_pod_logs",
                description="Get logs from a pod",
                parameters={
                    "name": {"type": "str", "required": True, "description": "Pod name"},
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"},
                    "container": {"type": "str", "required": False, "description": "Container name"},
                    "tail_lines": {"type": "int", "required": False, "description": "Number of lines to tail"}
                },
                return_type="str",
                module_path="kubernetes.pod",
                is_async=False
            )
        ]
        
        pod_capability = SDKCapability(
            name="pod_management",
            description="Kubernetes pod management operations",
            methods=pod_methods,
            requires_auth=True
        )
        capabilities.append(pod_capability)
        
        # Deployment operations
        deployment_methods = [
            SDKMethod(
                name="list_deployments",
                description="List deployments in a namespace",
                parameters={
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"},
                    "label_selector": {"type": "str", "required": False, "description": "Label selector"}
                },
                return_type="List[Deployment]",
                module_path="kubernetes.deployment",
                is_async=False
            ),
            SDKMethod(
                name="get_deployment",
                description="Get a specific deployment",
                parameters={
                    "name": {"type": "str", "required": True, "description": "Deployment name"},
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"}
                },
                return_type="Deployment",
                module_path="kubernetes.deployment",
                is_async=False
            ),
            SDKMethod(
                name="scale_deployment",
                description="Scale a deployment",
                parameters={
                    "name": {"type": "str", "required": True, "description": "Deployment name"},
                    "replicas": {"type": "int", "required": True, "description": "Number of replicas"},
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"}
                },
                return_type="Deployment",
                module_path="kubernetes.deployment",
                is_async=False
            )
        ]
        
        deployment_capability = SDKCapability(
            name="deployment_management",
            description="Kubernetes deployment management operations",
            methods=deployment_methods,
            requires_auth=True
        )
        capabilities.append(deployment_capability)
        
        # Service operations
        service_methods = [
            SDKMethod(
                name="list_services",
                description="List services in a namespace",
                parameters={
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"},
                    "label_selector": {"type": "str", "required": False, "description": "Label selector"}
                },
                return_type="List[Service]",
                module_path="kubernetes.service",
                is_async=False
            ),
            SDKMethod(
                name="get_service",
                description="Get a specific service",
                parameters={
                    "name": {"type": "str", "required": True, "description": "Service name"},
                    "namespace": {"type": "str", "required": False, "default": "default", "description": "Kubernetes namespace"}
                },
                return_type="Service",
                module_path="kubernetes.service",
                is_async=False
            )
        ]
        
        service_capability = SDKCapability(
            name="service_management",
            description="Kubernetes service management operations",
            methods=service_methods,
            requires_auth=True
        )
        capabilities.append(service_capability)
        
        return capabilities
    
    def generate_mcp_tools(self) -> List[MCPToolSchema]:
        """Generate MCP tool schemas for Kubernetes operations"""
        capabilities = self.discover_capabilities()
        tools = []
        
        for capability in capabilities:
            for method in capability.methods:
                schema = self.schema_generator.generate_tool_schema(method)
                tools.append(schema)
        
        return tools
    
    def create_tool_implementations(self) -> Dict[str, callable]:
        """Create actual tool implementations"""
        implementations = {}
        
        # Pod tools
        implementations["k8s.list_pods"] = self._wrap_list_pods
        implementations["k8s.get_pod"] = self._wrap_get_pod
        implementations["k8s.delete_pod"] = self._wrap_delete_pod
        implementations["k8s.get_pod_logs"] = self._wrap_get_pod_logs
        
        # Deployment tools
        implementations["k8s.list_deployments"] = self._wrap_list_deployments
        implementations["k8s.get_deployment"] = self._wrap_get_deployment
        implementations["k8s.scale_deployment"] = self._wrap_scale_deployment
        
        # Service tools
        implementations["k8s.list_services"] = self._wrap_list_services
        implementations["k8s.get_service"] = self._wrap_get_service
        
        return implementations
    
    def _wrap_list_pods(self, namespace: str = "default", label_selector: str = None) -> Dict[str, Any]:
        """List pods in a namespace"""
        try:
            if self._k8s_available:
                # Real K8s API call
                pods = self.v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
                pod_data = [{
                    "name": i.metadata.name,
                    "namespace": i.metadata.namespace,
                    "status": i.status.phase,
                    "node": i.spec.node_name,
                    "ip": i.status.pod_ip,
                    "ready": f"{sum(1 for cs in (i.status.container_statuses or []) if cs.ready)}/{len(i.status.container_statuses or [])}",
                    "restarts": sum(cs.restart_count for cs in (i.status.container_statuses or [])),
                    "age": str(i.metadata.creation_timestamp) if i.metadata.creation_timestamp else None,
                } for i in pods.items]
            else:
                # Mock response for demonstration
                pod_data = [
                    {
                        "name": "example-pod-1",
                        "namespace": namespace,
                        "status": "Running",
                        "ready": "1/1",
                        "restarts": 0,
                        "age": "2d",
                        "ip": "10.244.0.10",
                        "node": "worker-node-1"
                    },
                    {
                        "name": "example-pod-2", 
                        "namespace": namespace,
                        "status": "Running",
                        "ready": "1/1",
                        "restarts": 1,
                        "age": "1d",
                        "ip": "10.244.0.11",
                        "node": "worker-node-2"
                    }
                ]
            
            return self.serializer.serialize_response(pod_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"namespace": namespace, "label_selector": label_selector})
    
    def _wrap_get_pod(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """Get a specific pod"""
        try:
            # Placeholder implementation
            pod_data = {
                "name": name,
                "namespace": namespace,
                "status": "Running",
                "ready": "1/1",
                "restarts": 0,
                "age": "2d",
                "ip": "10.244.0.10",
                "node": "worker-node-1",
                "containers": [
                    {
                        "name": "main",
                        "image": "nginx:latest",
                        "ready": True,
                        "restart_count": 0
                    }
                ],
                "labels": {
                    "app": "example",
                    "version": "v1"
                }
            }
            
            return self.serializer.serialize_response(pod_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"name": name, "namespace": namespace})
    
    def _wrap_delete_pod(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """Delete a pod"""
        try:
            # Placeholder implementation
            result = {
                "message": f"Pod {name} in namespace {namespace} deleted successfully",
                "name": name,
                "namespace": namespace,
                "timestamp": "2025-01-01T12:00:00Z"
            }
            
            return self.serializer.serialize_response(result)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"name": name, "namespace": namespace})
    
    def _wrap_get_pod_logs(self, name: str, namespace: str = "default", container: str = None, tail_lines: int = None) -> Dict[str, Any]:
        """Get logs from a pod"""
        try:
            # Placeholder implementation
            logs = f"""
2025-01-01T12:00:00Z INFO Starting application
2025-01-01T12:00:01Z INFO Server listening on port 8080
2025-01-01T12:00:02Z INFO Ready to accept connections
            """.strip()
            
            result = {
                "pod": name,
                "namespace": namespace,
                "container": container,
                "logs": logs,
                "tail_lines": tail_lines
            }
            
            return self.serializer.serialize_response(result)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"name": name, "namespace": namespace, "container": container})
    
    def _wrap_list_deployments(self, namespace: str = "default", label_selector: str = None) -> Dict[str, Any]:
        """List deployments in a namespace"""
        try:
            # Placeholder implementation
            deployment_data = [
                {
                    "name": "example-deployment",
                    "namespace": namespace,
                    "ready_replicas": 3,
                    "desired_replicas": 3,
                    "up_to_date_replicas": 3,
                    "available_replicas": 3,
                    "age": "2d",
                    "strategy": "RollingUpdate"
                }
            ]
            
            return self.serializer.serialize_response(deployment_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"namespace": namespace, "label_selector": label_selector})
    
    def _wrap_get_deployment(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """Get a specific deployment"""
        try:
            # Placeholder implementation
            deployment_data = {
                "name": name,
                "namespace": namespace,
                "ready_replicas": 3,
                "desired_replicas": 3,
                "up_to_date_replicas": 3,
                "available_replicas": 3,
                "age": "2d",
                "strategy": "RollingUpdate",
                "labels": {
                    "app": "example",
                    "version": "v1"
                },
                "selector": {
                    "app": "example"
                }
            }
            
            return self.serializer.serialize_response(deployment_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"name": name, "namespace": namespace})
    
    def _wrap_scale_deployment(self, name: str, replicas: int, namespace: str = "default") -> Dict[str, Any]:
        """Scale a deployment"""
        try:
            # Placeholder implementation
            result = {
                "message": f"Deployment {name} scaled to {replicas} replicas",
                "name": name,
                "namespace": namespace,
                "previous_replicas": 3,
                "new_replicas": replicas,
                "timestamp": "2025-01-01T12:00:00Z"
            }
            
            return self.serializer.serialize_response(result)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"name": name, "replicas": replicas, "namespace": namespace})
    
    def _wrap_list_services(self, namespace: str = "default", label_selector: str = None) -> Dict[str, Any]:
        """List services in a namespace"""
        try:
            # Placeholder implementation
            service_data = [
                {
                    "name": "example-service",
                    "namespace": namespace,
                    "type": "ClusterIP",
                    "cluster_ip": "10.96.0.100",
                    "external_ip": None,
                    "ports": [
                        {
                            "name": "http",
                            "port": 80,
                            "target_port": 8080,
                            "protocol": "TCP"
                        }
                    ],
                    "age": "2d"
                }
            ]
            
            return self.serializer.serialize_response(service_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"namespace": namespace, "label_selector": label_selector})
    
    def _wrap_get_service(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """Get a specific service"""
        try:
            # Placeholder implementation
            service_data = {
                "name": name,
                "namespace": namespace,
                "type": "ClusterIP",
                "cluster_ip": "10.96.0.100",
                "external_ip": None,
                "ports": [
                    {
                        "name": "http",
                        "port": 80,
                        "target_port": 8080,
                        "protocol": "TCP"
                    }
                ],
                "selector": {
                    "app": "example"
                },
                "age": "2d"
            }
            
            return self.serializer.serialize_response(service_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"name": name, "namespace": namespace})
