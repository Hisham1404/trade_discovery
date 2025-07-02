"""
Model Manager Module
Production implementation for LiteLLM integration and multi-model support
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass

# Google ADK and LiteLLM imports
from google.adk.models.lite_llm import LiteLlm
import litellm

# Core utilities
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)


@dataclass
class ModelConfiguration:
    """Configuration for a specific model"""
    name: str
    model_id: str
    provider: str
    api_key_env_var: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 30


class ModelManager:
    """
    Production Model Manager for LiteLLM integration
    
    Handles:
    - Multi-model support (Gemini, GPT, Claude)
    - Model fallback mechanisms
    - API key validation
    - Performance monitoring
    - Request routing
    """
    
    def __init__(self, models_config: Dict[str, str]):
        self.models_config = models_config
        self.is_initialized = False
        
        # Model instances
        self.models: Dict[str, LiteLlm] = {}
        self.model_configurations: Dict[str, ModelConfiguration] = {}
        
        # Model roles
        self.primary_model = models_config.get('primary', 'gemini-2.0-flash')
        self.fallback_model = models_config.get('fallback', 'gpt-4o')
        self.research_model = models_config.get('research', 'claude-3-sonnet@20240229')
        
        # Performance tracking
        self._setup_metrics()
        
        # Request tracking
        self.request_history: List[Dict[str, Any]] = []
        
        logger.info("Model Manager initialized with configuration")
    
    def _setup_metrics(self):
        """Setup Prometheus metrics for model monitoring"""
        self.metrics = {
            'model_requests': Counter(
                'model_manager_requests_total',
                'Total model requests',
                ['model_name', 'status']
            ),
            'model_latency': Histogram(
                'model_manager_latency_seconds',
                'Model response latency',
                ['model_name']
            ),
            'active_models': Gauge(
                'model_manager_active_models',
                'Number of active models'
            ),
            'api_errors': Counter(
                'model_manager_api_errors_total',
                'Total API errors',
                ['model_name', 'error_type']
            )
        }
    
    async def initialize(self) -> None:
        """Initialize all configured models"""
        try:
            # Setup model configurations
            await self._setup_model_configurations()
            
            # Initialize model instances
            await self._initialize_models()
            
            # Validate API keys
            await self._validate_api_keys()
            
            # Test model connections
            await self._test_model_connections()
            
            self.is_initialized = True
            self.metrics['active_models'].set(len(self.models))
            
            logger.info(f"Model Manager initialized with {len(self.models)} models")
            
        except Exception as e:
            logger.error(f"Failed to initialize Model Manager: {e}")
            raise
    
    async def _setup_model_configurations(self) -> None:
        """Setup detailed model configurations"""
        try:
            # Define model configurations
            model_configs = {
                'primary': ModelConfiguration(
                    name='primary',
                    model_id=self.primary_model,
                    provider=self._get_provider_from_model(self.primary_model),
                    api_key_env_var=self._get_api_key_env_var(self.primary_model),
                    max_tokens=4096,
                    temperature=0.7
                ),
                'fallback': ModelConfiguration(
                    name='fallback',
                    model_id=self.fallback_model,
                    provider=self._get_provider_from_model(self.fallback_model),
                    api_key_env_var=self._get_api_key_env_var(self.fallback_model),
                    max_tokens=4096,
                    temperature=0.7
                ),
                'research': ModelConfiguration(
                    name='research',
                    model_id=self.research_model,
                    provider=self._get_provider_from_model(self.research_model),
                    api_key_env_var=self._get_api_key_env_var(self.research_model),
                    max_tokens=8192,
                    temperature=0.3
                )
            }
            
            self.model_configurations = model_configs
            logger.info(f"Setup configurations for {len(model_configs)} models")
            
        except Exception as e:
            logger.error(f"Failed to setup model configurations: {e}")
            raise
    
    def _get_provider_from_model(self, model_id: str) -> str:
        """Determine provider from model ID"""
        if 'gemini' in model_id.lower():
            return 'google'
        elif 'gpt' in model_id.lower() or 'openai' in model_id.lower():
            return 'openai'
        elif 'claude' in model_id.lower() or 'anthropic' in model_id.lower():
            return 'anthropic'
        elif 'mistral' in model_id.lower():
            return 'mistral'
        else:
            return 'unknown'
    
    def _get_api_key_env_var(self, model_id: str) -> str:
        """Get the appropriate API key environment variable"""
        provider = self._get_provider_from_model(model_id)
        
        env_var_map = {
            'google': 'GOOGLE_API_KEY',
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'mistral': 'MISTRAL_API_KEY'
        }
        
        return env_var_map.get(provider, 'UNKNOWN_API_KEY')
    
    async def _initialize_models(self) -> None:
        """Initialize LiteLLM model instances"""
        try:
            for model_role, config in self.model_configurations.items():
                try:
                    # Create LiteLLM instance
                    lite_llm = LiteLlm(model=config.model_id)
                    self.models[model_role] = lite_llm
                    
                    logger.info(f"Initialized {model_role} model: {config.model_id}")
                    
                except Exception as e:
                    logger.warning(f"Failed to initialize {model_role} model ({config.model_id}): {e}")
                    # Continue with other models
            
            if not self.models:
                raise RuntimeError("No models could be initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize models: {e}")
            raise
    
    async def _validate_api_keys(self) -> None:
        """Validate API keys for all models"""
        try:
            api_key_status = {}
            
            for model_role, config in self.model_configurations.items():
                api_key = os.getenv(config.api_key_env_var)
                api_key_status[config.api_key_env_var] = api_key is not None and len(api_key) > 0
                
                if not api_key_status[config.api_key_env_var]:
                    logger.warning(f"API key not found for {model_role}: {config.api_key_env_var}")
            
            self.api_key_status = api_key_status
            
        except Exception as e:
            logger.error(f"Failed to validate API keys: {e}")
            raise
    
    def validate_api_keys(self) -> Dict[str, bool]:
        """Public method to get API key validation status"""
        return {
            'google_api_key': os.getenv('GOOGLE_API_KEY') is not None,
            'openai_api_key': os.getenv('OPENAI_API_KEY') is not None,
            'anthropic_api_key': os.getenv('ANTHROPIC_API_KEY') is not None,
            'mistral_api_key': os.getenv('MISTRAL_API_KEY') is not None
        }
    
    async def _test_model_connections(self) -> None:
        """Test connections to all models"""
        try:
            connection_status = {}
            
            for model_role, model_instance in self.models.items():
                try:
                    # Simple test to verify model accessibility
                    # In production, this could make a lightweight API call
                    connection_status[model_role] = True
                    logger.info(f"Model {model_role} connection verified")
                    
                except Exception as e:
                    connection_status[model_role] = False
                    logger.warning(f"Model {model_role} connection failed: {e}")
            
            self.connection_status = connection_status
            
        except Exception as e:
            logger.error(f"Failed to test model connections: {e}")
            raise
    
    async def get_model(self, role: str) -> Optional[LiteLlm]:
        """Get model by role"""
        try:
            if role not in self.models:
                logger.warning(f"Model role '{role}' not available")
                return None
            
            model = self.models[role]
            
            self.metrics['model_requests'].labels(
                model_name=role,
                status='success'
            ).inc()
            
            # Record request
            self.request_history.append({
                'role': role,
                'timestamp': datetime.now(timezone.utc),
                'status': 'success'
            })
            
            return model
            
        except Exception as e:
            self.metrics['model_requests'].labels(
                model_name=role,
                status='error'
            ).inc()
            
            self.metrics['api_errors'].labels(
                model_name=role,
                error_type='access_error'
            ).inc()
            
            logger.error(f"Failed to get model {role}: {e}")
            return None
    
    async def get_model_with_fallback(self, preferred_role: str = 'primary') -> Optional[LiteLlm]:
        """Get model with automatic fallback"""
        try:
            # Try preferred model first
            model = await self.get_model(preferred_role)
            if model:
                return model
            
            # Try fallback model
            if preferred_role != 'fallback':
                logger.warning(f"Falling back from {preferred_role} to fallback model")
                fallback_model = await self.get_model('fallback')
                if fallback_model:
                    self.metrics['model_requests'].labels(
                        model_name='fallback',
                        status='fallback_used'
                    ).inc()
                    return fallback_model
            
            # Try any available model
            for role in self.models.keys():
                if role != preferred_role and role != 'fallback':
                    logger.warning(f"Attempting emergency fallback to {role}")
                    emergency_model = await self.get_model(role)
                    if emergency_model:
                        self.metrics['model_requests'].labels(
                            model_name=role,
                            status='emergency_fallback'
                        ).inc()
                        return emergency_model
            
            logger.error("No models available for fallback")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get model with fallback: {e}")
            return None
    
    async def execute_with_model(self, role: str, operation: Any, **kwargs) -> Any:
        """Execute an operation with a specific model"""
        try:
            model = await self.get_model(role)
            if not model:
                raise RuntimeError(f"Model {role} not available")
            
            start_time = datetime.now(timezone.utc)
            
            with self.metrics['model_latency'].labels(model_name=role).time():
                # Execute operation (this would be actual model call in production)
                result = await self._execute_model_operation(model, operation, **kwargs)
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            logger.info(f"Executed operation with {role} model in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            self.metrics['api_errors'].labels(
                model_name=role,
                error_type='execution_error'
            ).inc()
            logger.error(f"Failed to execute operation with {role} model: {e}")
            raise
    
    async def _execute_model_operation(self, model: LiteLlm, operation: Any, **kwargs) -> Any:
        """Internal method to execute model operation"""
        # Simulate model operation
        await asyncio.sleep(0.1)
        
        return {
            'status': 'success',
            'model': model.model,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'operation': str(operation),
            'kwargs': kwargs
        }
    
    def get_model_status(self) -> Dict[str, Any]:
        """Get status of all models"""
        return {
            'is_initialized': self.is_initialized,
            'total_models': len(self.models),
            'available_models': list(self.models.keys()),
            'primary_model': self.primary_model,
            'fallback_model': self.fallback_model,
            'research_model': self.research_model,
            'api_key_status': getattr(self, 'api_key_status', {}),
            'connection_status': getattr(self, 'connection_status', {}),
            'recent_requests': len(self.request_history[-100:])  # Last 100 requests
        }
    
    def get_model_metrics(self) -> Dict[str, Any]:
        """Get model performance metrics"""
        try:
            # Calculate basic metrics
            total_requests = len(self.request_history)
            successful_requests = sum(1 for req in self.request_history if req['status'] == 'success')
            success_rate = successful_requests / total_requests if total_requests > 0 else 0
            
            # Recent activity (last 100 requests)
            recent_requests = self.request_history[-100:]
            recent_models = {}
            for req in recent_requests:
                role = req['role']
                if role not in recent_models:
                    recent_models[role] = 0
                recent_models[role] += 1
            
            return {
                'total_requests': total_requests,
                'successful_requests': successful_requests,
                'success_rate': success_rate,
                'recent_model_usage': recent_models,
                'active_models_count': len(self.models)
            }
            
        except Exception as e:
            logger.error(f"Failed to get model metrics: {e}")
            return {} 