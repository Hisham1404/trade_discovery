"""
Event Schema Definitions for Apache Pulsar Integration

Defines structured event schemas for cross-cluster communication using Pydantic models
Compatible with Pulsar JsonSchema and AvroSchema serialization
"""

from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Dict, Any, Optional, Literal
from enum import Enum


class SignalDirection(str, Enum):
    """Valid signal directions"""
    BUY = "BUY"
    SELL = "SELL"


class SignalStatus(str, Enum):
    """Valid signal statuses"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXECUTED = "executed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AlertSeverity(str, Enum):
    """Risk alert severity levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(str, Enum):
    """Types of risk alerts"""
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    TARGET_REACHED = "TARGET_REACHED"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    POSITION_SIZE_BREACH = "POSITION_SIZE_BREACH"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    CORRELATION_BREAK = "CORRELATION_BREAK"


class SignalAcceptedEvent(BaseModel):
    """
    Event published when a user accepts a trading signal
    Topic: events.signal.accepted
    """
    event_type: str = Field(default='signal.accepted.v1', description="Event type identifier")
    signal_id: str = Field(..., description="Unique signal identifier")
    user_id: str = Field(..., description="User who accepted the signal")
    symbol: str = Field(..., description="Trading symbol (e.g., RELIANCE, TATASTEEL)")
    direction: SignalDirection = Field(..., description="BUY or SELL direction")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Signal confidence (0.0-1.0)")
    stop_loss: float = Field(..., gt=0, description="Stop loss price")
    target: float = Field(..., gt=0, description="Target price")
    timestamp: datetime = Field(..., description="Event timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional signal metadata")
    
    @validator('target', 'stop_loss')
    def validate_prices(cls, v):
        """Ensure prices are positive"""
        if v <= 0:
            raise ValueError('Price must be positive')
        return v
    
    @validator('metadata')
    def validate_metadata(cls, v):
        """Ensure metadata is a dictionary"""
        if not isinstance(v, dict):
            raise ValueError('Metadata must be a dictionary')
        return v
    
    class Config:
        """Pydantic configuration"""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SignalStatusUpdateEvent(BaseModel):
    """
    Event published when signal status changes
    Topic: events.signal.status
    """
    event_type: str = Field(default='signal.status.updated.v1', description="Event type identifier")
    signal_id: str = Field(..., description="Signal identifier")
    user_id: str = Field(..., description="User identifier")
    old_status: SignalStatus = Field(..., description="Previous signal status")
    new_status: SignalStatus = Field(..., description="New signal status")
    timestamp: datetime = Field(..., description="Status change timestamp")
    execution_price: Optional[float] = Field(None, description="Execution price if applicable")
    execution_quantity: Optional[float] = Field(None, description="Executed quantity if applicable")
    reason: Optional[str] = Field(None, description="Reason for status change")
    
    @validator('execution_price', 'execution_quantity')
    def validate_execution_data(cls, v):
        """Validate execution data if provided"""
        if v is not None and v <= 0:
            raise ValueError('Execution data must be positive')
        return v
    
    class Config:
        """Pydantic configuration"""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class RiskAlertEvent(BaseModel):
    """
    Event published for risk management alerts
    Topic: events.risk.alert
    """
    event_type: str = Field(default='risk.alert.v1', description="Event type identifier")
    alert_id: str = Field(..., description="Unique alert identifier")
    signal_id: str = Field(..., description="Related signal identifier")
    user_id: str = Field(..., description="Affected user identifier")
    alert_type: AlertType = Field(..., description="Type of risk alert")
    severity: AlertSeverity = Field(..., description="Alert severity level")
    message: str = Field(..., description="Human-readable alert message")
    timestamp: datetime = Field(..., description="Alert timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Alert-specific data")
    current_price: Optional[float] = Field(None, description="Current market price")
    threshold_value: Optional[float] = Field(None, description="Threshold that was breached")
    
    @validator('current_price', 'threshold_value')
    def validate_price_data(cls, v):
        """Validate price data if provided"""
        if v is not None and v <= 0:
            raise ValueError('Price data must be positive')
        return v
    
    class Config:
        """Pydantic configuration"""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MarketDataUpdateEvent(BaseModel):
    """
    Event for real-time market data updates
    Topic: events.market.data
    """
    event_type: str = Field(default='market.data.updated.v1', description="Event type identifier")
    symbol: str = Field(..., description="Trading symbol")
    price: float = Field(..., gt=0, description="Current price")
    volume: float = Field(..., ge=0, description="Trading volume")
    bid: Optional[float] = Field(None, gt=0, description="Best bid price")
    ask: Optional[float] = Field(None, gt=0, description="Best ask price")
    timestamp: datetime = Field(..., description="Market data timestamp")
    exchange: str = Field(default="NSE", description="Stock exchange")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional market data")
    
    class Config:
        """Pydantic configuration"""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentPerformanceEvent(BaseModel):
    """
    Event for agent performance metrics
    Topic: events.agent.performance
    """
    event_type: str = Field(default='agent.performance.v1', description="Event type identifier")
    agent_id: str = Field(..., description="Agent identifier")
    agent_type: str = Field(..., description="Type of agent (e.g., DAPO, Technical)")
    performance_metrics: Dict[str, float] = Field(..., description="Performance metrics")
    signals_generated: int = Field(..., ge=0, description="Number of signals generated")
    accuracy_score: float = Field(..., ge=0.0, le=1.0, description="Accuracy score")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio if available")
    timestamp: datetime = Field(..., description="Metrics timestamp")
    evaluation_period: str = Field(..., description="Evaluation period (e.g., '1h', '1d')")
    
    @validator('performance_metrics')
    def validate_performance_metrics(cls, v):
        """Ensure performance metrics are valid"""
        if not isinstance(v, dict):
            raise ValueError('Performance metrics must be a dictionary')
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f'Metric {key} must be numeric')
        return v
    
    class Config:
        """Pydantic configuration"""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserActionEvent(BaseModel):
    """
    Event for user action tracking
    Topic: events.user.action
    """
    event_type: str = Field(default='user.action.v1', description="Event type identifier")
    user_id: str = Field(..., description="User identifier")
    action_type: str = Field(..., description="Type of action (e.g., 'signal_accept', 'portfolio_view')")
    resource_id: Optional[str] = Field(None, description="ID of affected resource")
    session_id: str = Field(..., description="User session identifier")
    timestamp: datetime = Field(..., description="Action timestamp")
    ip_address: Optional[str] = Field(None, description="User IP address")
    user_agent: Optional[str] = Field(None, description="User agent string")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional action data")
    
    class Config:
        """Pydantic configuration"""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SystemHealthEvent(BaseModel):
    """
    Event for system health monitoring
    Topic: events.system.health
    """
    event_type: str = Field(default='system.health.v1', description="Event type identifier")
    component: str = Field(..., description="System component name")
    status: Literal['healthy', 'degraded', 'unhealthy'] = Field(..., description="Health status")
    metrics: Dict[str, float] = Field(..., description="Health metrics")
    timestamp: datetime = Field(..., description="Health check timestamp")
    cluster_id: str = Field(..., description="Cluster identifier")
    node_id: Optional[str] = Field(None, description="Node identifier if applicable")
    alert_threshold: Optional[float] = Field(None, description="Alert threshold if crossed")
    
    @validator('metrics')
    def validate_metrics(cls, v):
        """Ensure metrics are valid"""
        if not isinstance(v, dict):
            raise ValueError('Metrics must be a dictionary')
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f'Metric {key} must be numeric')
        return v
    
    class Config:
        """Pydantic configuration"""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Schema registry mapping for easy lookup
SCHEMA_REGISTRY = {
    'events.signal.accepted': SignalAcceptedEvent,
    'events.signal.status': SignalStatusUpdateEvent,
    'events.risk.alert': RiskAlertEvent,
    'events.market.data': MarketDataUpdateEvent,
    'events.agent.performance': AgentPerformanceEvent,
    'events.user.action': UserActionEvent,
    'events.system.health': SystemHealthEvent,
}


def get_schema_class(topic: str) -> BaseModel:
    """
    Get schema class for a given topic
    
    Args:
        topic: Pulsar topic name
        
    Returns:
        Pydantic schema class
        
    Raises:
        ValueError: If topic is not found
    """
    if topic not in SCHEMA_REGISTRY:
        raise ValueError(f"No schema found for topic: {topic}")
    
    return SCHEMA_REGISTRY[topic]


def validate_event(topic: str, event_data: dict) -> BaseModel:
    """
    Validate event data against topic schema
    
    Args:
        topic: Pulsar topic name
        event_data: Event data dictionary
        
    Returns:
        Validated event instance
        
    Raises:
        ValueError: If validation fails
    """
    schema_class = get_schema_class(topic)
    return schema_class(**event_data)


def get_all_topics() -> list:
    """Get list of all supported topics"""
    return list(SCHEMA_REGISTRY.keys())


def get_schema_info(topic: str) -> dict:
    """
    Get schema information for a topic
    
    Args:
        topic: Pulsar topic name
        
    Returns:
        Schema information dictionary
    """
    schema_class = get_schema_class(topic)
    
    return {
        'topic': topic,
        'schema_class': schema_class.__name__,
        'fields': list(schema_class.__fields__.keys()),
        'description': schema_class.__doc__,
        'event_type': schema_class.__fields__['event_type'].default
    } 