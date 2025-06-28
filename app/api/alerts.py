"""
Alert configuration REST endpoints for trading signal alerts.
Allows users to configure custom alerts based on signal criteria, agent performance, and market conditions.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

# Router for alert endpoints
router = APIRouter()


# Pydantic models for alert endpoints

class AlertCriteria(BaseModel):
    """Alert criteria configuration."""
    symbol: Optional[str] = Field(None, description="Stock symbol (e.g., RELIANCE, TCS)")
    symbols: Optional[List[str]] = Field(None, description="Multiple symbols")
    sector: Optional[str] = Field(None, description="Market sector filter")
    signal_type: Optional[Literal["BUY", "SELL"]] = Field(None, description="Signal type filter")
    min_confidence: float = Field(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold")
    max_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Maximum confidence threshold")
    min_target_price: Optional[float] = Field(None, gt=0, description="Minimum target price")
    max_target_price: Optional[float] = Field(None, gt=0, description="Maximum target price")
    risk_score_max: float = Field(1.0, ge=0.0, le=1.0, description="Maximum acceptable risk score")
    agent_ids: Optional[List[str]] = Field(None, description="Specific agent IDs to monitor")

    @field_validator('max_confidence')
    @classmethod
    def validate_confidence_range(cls, v, info):
        """Ensure max_confidence >= min_confidence"""
        if 'min_confidence' in info.data and v < info.data['min_confidence']:
            raise ValueError('max_confidence must be >= min_confidence')
        return v


class NotificationChannel(BaseModel):
    """Notification channel configuration."""
    type: Literal["email", "sms", "push", "webhook"] = Field(..., description="Notification type")
    enabled: bool = Field(True, description="Whether this channel is enabled")
    address: str = Field(..., description="Email, phone number, push token, or webhook URL")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Channel-specific settings")

    @field_validator('address')
    @classmethod
    def validate_address_format(cls, v, info):
        """Validate address format based on notification type"""
        if 'type' not in info.data:
            return v
            
        notification_type = info.data['type']
        
        if notification_type == 'email':
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v):
                raise ValueError('Invalid email address format')
        elif notification_type == 'sms':
            import re
            phone_pattern = r'^\+91[6-9]\d{9}$'
            if not re.match(phone_pattern, v):
                raise ValueError('Invalid Indian phone number format. Use +91XXXXXXXXXX')
        elif notification_type == 'webhook':
            import re
            url_pattern = r'^https?://.*'
            if not re.match(url_pattern, v):
                raise ValueError('Webhook URL must start with http:// or https://')
        
        return v


class AlertSchedule(BaseModel):
    """Alert scheduling configuration."""
    enabled: bool = Field(True, description="Whether scheduling is enabled")
    start_time: Optional[str] = Field(None, pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="Start time HH:MM")
    end_time: Optional[str] = Field(None, pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="End time HH:MM")
    days_of_week: List[int] = Field(default=[1,2,3,4,5], description="Days of week (1=Monday, 7=Sunday)")
    timezone: str = Field("Asia/Kolkata", description="Timezone for scheduling")

    @field_validator('days_of_week')
    @classmethod
    def validate_days_of_week(cls, v):
        """Validate days of week are in valid range"""
        if not all(1 <= day <= 7 for day in v):
            raise ValueError('Days of week must be between 1 (Monday) and 7 (Sunday)')
        return v


class AlertCreateRequest(BaseModel):
    """Request model for creating a new alert."""
    name: str = Field(..., min_length=1, max_length=100, description="Alert name")
    description: Optional[str] = Field(None, max_length=500, description="Alert description")
    criteria: AlertCriteria = Field(..., description="Alert criteria")
    notification_channels: List[NotificationChannel] = Field(..., min_length=1, description="Notification channels")
    schedule: AlertSchedule = Field(default_factory=AlertSchedule, description="Alert schedule")
    enabled: bool = Field(True, description="Whether alert is enabled")
    priority: Literal["low", "medium", "high", "critical"] = Field("medium", description="Alert priority")


class AlertUpdateRequest(BaseModel):
    """Request model for updating an existing alert."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Alert name")
    description: Optional[str] = Field(None, max_length=500, description="Alert description")
    criteria: Optional[AlertCriteria] = Field(None, description="Alert criteria")
    notification_channels: Optional[List[NotificationChannel]] = Field(None, description="Notification channels")
    schedule: Optional[AlertSchedule] = Field(None, description="Alert schedule")
    enabled: Optional[bool] = Field(None, description="Whether alert is enabled")
    priority: Optional[Literal["low", "medium", "high", "critical"]] = Field(None, description="Alert priority")


class AlertResponse(BaseModel):
    """Response model for alert data."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., description="Alert ID")
    user_id: str = Field(..., description="User ID who owns the alert")
    name: str = Field(..., description="Alert name")
    description: Optional[str] = Field(None, description="Alert description")
    criteria: AlertCriteria = Field(..., description="Alert criteria")
    notification_channels: List[NotificationChannel] = Field(..., description="Notification channels")
    schedule: AlertSchedule = Field(..., description="Alert schedule")
    enabled: bool = Field(..., description="Whether alert is enabled")
    priority: str = Field(..., description="Alert priority")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    triggered_count: int = Field(0, description="Number of times alert has been triggered")
    last_triggered_at: Optional[str] = Field(None, description="Last trigger timestamp")
    effectiveness_score: float = Field(0.0, description="Alert effectiveness score (0.0-1.0)")


class AlertsListResponse(BaseModel):
    """Response model for paginated alerts list."""
    alerts: List[AlertResponse] = Field(..., description="List of alerts")
    total: int = Field(..., description="Total number of alerts")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")
    total_pages: int = Field(..., description="Total pages")


# Mock database storage (replace with real database in production)
alerts_db: Dict[str, Dict] = {}
alert_counter = 1


def generate_alert_id() -> str:
    """Generate a unique alert ID."""
    global alert_counter
    alert_id = f"alert_{alert_counter:06d}"
    alert_counter += 1
    return alert_id


def get_user_alerts(user_id: str, enabled_only: bool = False) -> List[Dict]:
    """Get all alerts for a user."""
    user_alerts = [
        alert for alert in alerts_db.values() 
        if alert["user_id"] == user_id and (not enabled_only or alert["enabled"])
    ]
    return sorted(user_alerts, key=lambda x: x["created_at"], reverse=True)


def get_alert_by_id(alert_id: str, user_id: str) -> Optional[Dict]:
    """Get alert by ID if it belongs to the user."""
    alert = alerts_db.get(alert_id)
    if alert and alert["user_id"] == user_id:
        return alert
    return None


# API Endpoints

@router.post("/alerts", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreateRequest,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Create a new alert configuration.
    
    Args:
        alert_data: Alert configuration data
        current_user: Current authenticated user
        
    Returns:
        AlertResponse: Created alert data
    """
    alert_id = generate_alert_id()
    now = datetime.now(timezone.utc).isoformat()
    
    alert = {
        "id": alert_id,
        "user_id": current_user["user_id"],
        "name": alert_data.name,
        "description": alert_data.description,
        "criteria": alert_data.criteria.model_dump(),
        "notification_channels": [ch.model_dump() for ch in alert_data.notification_channels],
        "schedule": alert_data.schedule.model_dump(),
        "enabled": alert_data.enabled,
        "priority": alert_data.priority,
        "created_at": now,
        "updated_at": None,
        "triggered_count": 0,
        "last_triggered_at": None,
        "effectiveness_score": 0.0
    }
    
    alerts_db[alert_id] = alert
    logger.info(f"Created alert {alert_id} for user {current_user['user_id']}")
    
    return AlertResponse(**alert)


@router.get("/alerts", response_model=AlertsListResponse)
async def get_alerts(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    enabled_only: Annotated[bool, Query(description="Show only enabled alerts")] = False,
    priority: Annotated[Optional[str], Query(description="Filter by priority")] = None,
    current_user: Annotated[dict, Depends(get_current_user)] = None
):
    """
    Get user's alerts with pagination and filtering.
    
    Args:
        page: Page number
        page_size: Items per page
        enabled_only: Show only enabled alerts
        priority: Filter by priority level
        current_user: Current authenticated user
        
    Returns:
        AlertsListResponse: Paginated alerts list
    """
    user_alerts = get_user_alerts(current_user["user_id"], enabled_only)
    
    # Filter by priority if specified
    if priority:
        user_alerts = [alert for alert in user_alerts if alert["priority"] == priority]
    
    # Pagination
    total = len(user_alerts)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_alerts = user_alerts[start_idx:end_idx]
    
    alerts_response = [AlertResponse(**alert) for alert in paginated_alerts]
    
    return AlertsListResponse(
        alerts=alerts_response,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Get alert by ID.
    
    Args:
        alert_id: Alert ID
        current_user: Current authenticated user
        
    Returns:
        AlertResponse: Alert data
    """
    alert = get_alert_by_id(alert_id, current_user["user_id"])
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    return AlertResponse(**alert)


@router.put("/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: str,
    alert_data: AlertUpdateRequest,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Update an existing alert.
    
    Args:
        alert_id: Alert ID
        alert_data: Updated alert data
        current_user: Current authenticated user
        
    Returns:
        AlertResponse: Updated alert data
    """
    alert = get_alert_by_id(alert_id, current_user["user_id"])
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    # Update fields
    update_data = alert_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "criteria" and value:
            alert["criteria"] = value
        elif field == "notification_channels" and value:
            alert["notification_channels"] = [ch.model_dump() if hasattr(ch, 'model_dump') else ch for ch in value]
        elif field == "schedule" and value:
            alert["schedule"] = value.model_dump() if hasattr(value, 'model_dump') else value
        else:
            alert[field] = value
    
    alert["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    logger.info(f"Updated alert {alert_id} for user {current_user['user_id']}")
    
    return AlertResponse(**alert)


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: str,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Delete an alert.
    
    Args:
        alert_id: Alert ID
        current_user: Current authenticated user
    """
    alert = get_alert_by_id(alert_id, current_user["user_id"])
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    # Remove from database
    del alerts_db[alert_id]
    
    logger.info(f"Deleted alert {alert_id} for user {current_user['user_id']}")


@router.post("/alerts/test/{alert_id}")
async def test_alert(
    alert_id: str,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Test an alert with a mock signal to verify configuration.
    
    Args:
        alert_id: Alert ID to test
        current_user: Current authenticated user
        
    Returns:
        Dict: Test result
    """
    alert = get_alert_by_id(alert_id, current_user["user_id"])
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    # Create mock signal that should trigger the alert
    criteria = AlertCriteria(**alert["criteria"])
    mock_signal = {
        "id": "test_signal_123",
        "symbol": criteria.symbol or "RELIANCE",
        "signal_type": criteria.signal_type or "BUY",
        "confidence": (criteria.min_confidence + criteria.max_confidence) / 2,
        "target_price": criteria.min_target_price or 2500.0,
        "risk_score": criteria.risk_score_max * 0.8,
        "agent_id": criteria.agent_ids[0] if criteria.agent_ids else "test_agent",
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    
    return {
        "alert_id": alert_id,
        "test_signal": mock_signal,
        "should_trigger": True,
        "test_timestamp": datetime.now(timezone.utc).isoformat()
    }
