"""
Signal endpoints for trading signal discovery and acceptance.
Provides protected API routes with JWT authentication and Pulsar integration using FastAPI/Pydantic v2 best practices.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

# Router for signal endpoints
router = APIRouter()


# Pydantic models for signal endpoints using v2 patterns

class SignalResponse(BaseModel):
    """Response model for signal data."""
    id: str
    symbol: str
    exchange: str
    signal_type: str
    confidence: float
    target_price: float
    stop_loss: float
    generated_at: str
    expires_at: str
    rationale: str
    risk_score: float
    position_size: float


class SignalAcceptRequest(BaseModel):
    """Request model for signal acceptance with Pydantic v2 validation."""
    position_size: Annotated[float, Field(ge=0.001, le=1.0, description="Position size (0.1% to 100%)")]
    risk_tolerance: Annotated[Optional[str], Field(default="medium", pattern=r"^(low|medium|high)$")]
    notes: Annotated[Optional[str], Field(default=None, max_length=500)]
    
    @field_validator('position_size', mode='after')
    @classmethod
    def validate_position_size(cls, v: float) -> float:
        """Validate position size is within acceptable range."""
        if v <= 0 or v > 1:
            raise ValueError('Position size must be between 0.1% and 100%')
        return v


class SignalAcceptResponse(BaseModel):
    """Response model for signal acceptance."""
    status: str = "accepted"
    signal_id: str
    accepted_at: str
    position_size: float
    message: str = "Signal accepted successfully"


class SignalsListResponse(BaseModel):
    """Response model for signals list."""
    signals: List[SignalResponse]
    total: int
    page: int
    page_size: int


# Mock data for development - using future dates
_now = datetime.now(timezone.utc)
_future_expiry = (_now + timedelta(hours=6)).isoformat().replace('+00:00', 'Z')
_recent_generated = (_now - timedelta(hours=1)).isoformat().replace('+00:00', 'Z')

MOCK_SIGNALS = [
    {
        "id": "signal_001",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "signal_type": "BUY",
        "confidence": 0.85,
        "target_price": 2500.0,
        "stop_loss": 2300.0,
        "generated_at": _recent_generated,
        "expires_at": _future_expiry,
        "rationale": "Strong momentum with RSI oversold conditions",
        "risk_score": 0.25,
        "position_size": 0.05
    },
    {
        "id": "signal_002",
        "symbol": "TCS",
        "exchange": "NSE", 
        "signal_type": "SELL",
        "confidence": 0.78,
        "target_price": 3200.0,
        "stop_loss": 3400.0,
        "generated_at": _recent_generated,
        "expires_at": _future_expiry,
        "rationale": "Bearish divergence with volume analysis",
        "risk_score": 0.30,
        "position_size": 0.03
    }
]


# Helper functions

def get_signals_from_cache() -> List[Dict[str, Any]]:
    """
    Get signals from cache/database.
    
    Returns:
        List[Dict]: List of signal data
    """
    return MOCK_SIGNALS


def get_signal_by_id(signal_id: str) -> Optional[Dict[str, Any]]:
    """
    Get signal by ID.
    
    Args:
        signal_id: Signal ID
        
    Returns:
        Dict: Signal data if found, None otherwise
    """
    for signal in MOCK_SIGNALS:
        if signal["id"] == signal_id:
            return signal
    return None


def is_signal_expired(signal: Dict[str, Any]) -> bool:
    """
    Check if signal is expired.
    
    Args:
        signal: Signal data
        
    Returns:
        bool: True if expired
    """
    try:
        expires_at = datetime.fromisoformat(signal["expires_at"].replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > expires_at
    except Exception:
        return True


def publish_to_pulsar(signal_data: Dict[str, Any]) -> bool:
    """
    Publish signal acceptance to Pulsar topic.
    
    Args:
        signal_data: Signal acceptance data
        
    Returns:
        bool: True if published successfully
    """
    try:
        # Mock implementation - in production this would use Pulsar client
        logger.info(f"Publishing signal acceptance to Pulsar: {signal_data}")
        return True
    except Exception as e:
        logger.error(f"Failed to publish to Pulsar: {e}")
        return False


def get_pulsar_client():
    """
    Get Pulsar client instance.
    
    Returns:
        Pulsar client instance
    """
    # Mock implementation
    from unittest.mock import Mock
    return Mock()


# API Endpoints using FastAPI dependency injection patterns

@router.get("/signals", response_model=SignalsListResponse)
async def get_signals(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 10,
    symbol: Annotated[Optional[str], Query(description="Filter by symbol")] = None,
    signal_type: Annotated[Optional[str], Query(pattern=r"^(BUY|SELL)$", description="Filter by signal type")] = None,
    min_confidence: Annotated[Optional[float], Query(ge=0.0, le=1.0, description="Minimum confidence")] = None,
    current_user: Annotated[dict, Depends(get_current_user)] = None
):
    """
    Get trading signals with pagination and filtering.
    
    Args:
        page: Page number (1-based)
        page_size: Number of signals per page (1-100)
        symbol: Optional symbol filter
        signal_type: Optional signal type filter (BUY/SELL)
        min_confidence: Optional minimum confidence filter (0.0-1.0)
        current_user: Current authenticated user
        
    Returns:
        SignalsListResponse: Paginated signals with metadata
    """
    try:
        # Get signals from cache
        signals = get_signals_from_cache()
        
        # Apply filters
        if symbol:
            signals = [s for s in signals if s["symbol"].upper() == symbol.upper()]
        
        if signal_type:
            signals = [s for s in signals if s["signal_type"] == signal_type]
        
        if min_confidence is not None:
            signals = [s for s in signals if s["confidence"] >= min_confidence]
        
        # Apply pagination
        total = len(signals)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_signals = signals[start_idx:end_idx]
        
        return SignalsListResponse(
            signals=[SignalResponse(**signal) for signal in paginated_signals],
            total=total,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signal service unavailable"
        )


@router.post("/signals/{signal_id}/accept", response_model=SignalAcceptResponse)
async def accept_signal(
    signal_id: str,
    accept_data: SignalAcceptRequest,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """
    Accept a trading signal.
    
    Args:
        signal_id: ID of the signal to accept
        accept_data: Signal acceptance data
        current_user: Current authenticated user
        
    Returns:
        SignalAcceptResponse: Acceptance confirmation
    """
    # Get signal by ID
    signal = get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found"
        )
    
    # Check if signal is expired
    if is_signal_expired(signal):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signal has expired"
        )
    
    # Prepare signal acceptance data
    acceptance_data = {
        "signal_id": signal_id,
        "user_id": current_user.get("user_id"),
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "position_size": accept_data.position_size,
        "risk_tolerance": accept_data.risk_tolerance,
        "notes": accept_data.notes,
        "signal_data": signal
    }
    
    # Publish to Pulsar
    published = publish_to_pulsar(acceptance_data)
    if not published:
        logger.warning(f"Failed to publish signal acceptance for {signal_id}")
        # Continue anyway - acceptance is recorded
    
    # Broadcast signal acceptance via WebSocket
    try:
        from app.api.websockets import broadcast_signal_acceptance
        await broadcast_signal_acceptance(
            user_id=current_user["user_id"],
            signal_id=signal_id,
            acceptance_data=accept_data.model_dump()
        )
    except Exception as e:
        logger.error(f"Failed to broadcast signal acceptance: {e}")
        # Don't fail the request if WebSocket broadcast fails
    
    return SignalAcceptResponse(
        signal_id=signal_id,
        accepted_at=acceptance_data["accepted_at"],
        position_size=accept_data.position_size
    ) 