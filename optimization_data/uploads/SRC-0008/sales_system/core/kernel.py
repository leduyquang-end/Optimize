# core/kernel.py
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import uuid
import logging
from core.plugins import Plugin, PluginContext, PluginStatus

logger = logging.getLogger(__name__)

class SalesKernel:
    """Microkernel core system"""
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._contexts: Dict[str, PluginContext] = {}
        self._hooks: Dict[str, List[Callable]] = {}
        self._system_state: Dict[str, Any] = {}
    
    def register_plugin(self, plugin: Plugin) -> bool:
        """Register a plugin with the kernel"""
        plugin_id = plugin.get_id()
        
        if plugin_id in self._plugins:
            logger.warning(f"Plugin {plugin_id} already registered")
            return False
        
        try:
            context = PluginContext(
                plugin_id=plugin_id,
                status=PluginStatus.INACTIVE,
                config=plugin.get_default_config(),
                data={}
            )
            
            self._contexts[plugin_id] = context
            self._plugins[plugin_id] = plugin
            
            # Initialize plugin
            plugin.initialize(context)
            context.status = PluginStatus.ACTIVE
            
            logger.info(f"Plugin registered: {plugin.get_name()} v{plugin.get_version()}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register plugin {plugin_id}: {e}")
            return False
    
    def unregister_plugin(self, plugin_id: str) -> bool:
        """Unregister a plugin"""
        if plugin_id not in self._plugins:
            return False
        
        try:
            self._plugins[plugin_id].destroy()
            del self._plugins[plugin_id]
            del self._contexts[plugin_id]
            logger.info(f"Plugin unregistered: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister plugin {plugin_id}: {e}")
            return False
    
    def execute_plugin(self, plugin_id: str, **kwargs) -> Any:
        """Execute a plugin operation"""
        if plugin_id not in self._plugins:
            raise ValueError(f"Plugin not found: {plugin_id}")
        
        context = self._contexts[plugin_id]
        if context.status != PluginStatus.ACTIVE:
            raise ValueError(f"Plugin {plugin_id} is not active")
        
        try:
            result = self._plugins[plugin_id].execute(**kwargs)
            
            # Execute hooks after plugin execution
            hook_key = f"{plugin_id}.after_execute"
            if hook_key in self._hooks:
                for hook in self._hooks[hook_key]:
                    hook(result, kwargs)
            
            return result
            
        except Exception as e:
            context.status = PluginStatus.ERROR
            logger.error(f"Plugin execution failed: {e}")
            raise
    
    def get_plugin_context(self, plugin_id: str) -> Optional[PluginContext]:
        """Get plugin context"""
        return self._contexts.get(plugin_id)
    
    def get_plugin_status(self, plugin_id: str) -> Optional[str]:
        """Get plugin status"""
        context = self._contexts.get(plugin_id)
        return context.status.value if context else None
    
    def register_hook(self, hook_name: str, callback: Callable):
        """Register a hook callback"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)
    
    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """Get plugin instance"""
        return self._plugins.get(plugin_id)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all registered plugins"""
        return [
            {
                "id": plugin.get_id(),
                "name": plugin.get_name(),
                "version": plugin.get_version(),
                "status": self._contexts[plugin.get_id()].status.value
            }
            for plugin in self._plugins.values()
        ]
    
    def set_system_state(self, key: str, value: Any):
        """Set system state"""
        self._system_state[key] = value
    
    def get_system_state(self, key: str, default: Any = None) -> Any:
        """Get system state"""
        return self._system_state.get(key, default)

# Global kernel instance
sales_kernel = SalesKernel()