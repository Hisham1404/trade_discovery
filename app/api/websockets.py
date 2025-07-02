"""
WebSocket endpoints for real-time signal updates and notifications.
Implements authenticated WebSocket connections with JWT validation and message broadcasting.
Enhanced with production-grade features including reconnection logic and message queuing.
"""

import logging
import uuid
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from fastapi.exceptions import WebSocketException

from app.services.enhanced_websocket_manager import enhanced_websocket_manager
from app.services.jwt_manager import get_token_payload
from app.services.session_manager import get_session

logger = logging.getLogger(__name__)

# Router for WebSocket endpoints
router = APIRouter()


async def authenticate_websocket(token: str) -> Optional[dict]:
    """
    Authenticate WebSocket connection using JWT token.
    
    Args:
        token: JWT token from query parameter
        
    Returns:
        dict: User data if authentication successful, None otherwise
    """
    try:
        # Validate JWT token
        payload = get_token_payload(token)
        if not payload:
            return None
            
        user_id = payload.get("user_id")
        if not user_id:
            return None
            
        # Validate Redis session (optional for WebSocket - JWT validation is primary)
        # In production, you might require active sessions
        session_data = get_session(f"session:{user_id}")
        # For now, we allow WebSocket connections with just valid JWT
        # if not session_data:
        #     return None
            
        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "is_verified": payload.get("is_verified", False),
            "is_2fa_enabled": payload.get("is_2fa_enabled", False),
            "session_id": session_data.get("session_id") if session_data else None
        }
        
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
        return None


@router.websocket("/signals")
async def websocket_signals_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT authentication token"),
    client_id: Optional[str] = Query(None, description="Client identifier for reconnection"),
    reconnection_token: Optional[str] = Query(None, description="Reconnection token for dropped connections")
):
    """
    Enhanced WebSocket endpoint for real-time signal updates.
    Supports reconnection logic, message queuing, and subscription-based filtering.
    Requires JWT authentication via query parameter.
    
    Args:
        websocket: WebSocket connection
        token: JWT authentication token
        client_id: Optional client identifier for reconnection
        reconnection_token: Optional reconnection token for client recovery
    """
    # Generate client ID if not provided
    if not client_id:
        client_id = str(uuid.uuid4())
    
    try:
        # Handle reconnection attempt first
        if reconnection_token and client_id:
            logger.info(f"Attempting reconnection for client {client_id}")
            success = await enhanced_websocket_manager.reconnect(websocket, client_id, reconnection_token)
            if success:
                logger.info(f"Successfully reconnected client {client_id}")
                await handle_websocket_session(client_id, websocket)
                return
            else:
                logger.warning(f"Failed to reconnect client {client_id}")
                # Fall through to new connection attempt
        
        # Regular authentication for new connections
        if not token:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Authentication token required"
            )
            
        user_data = await authenticate_websocket(token)
        if not user_data:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid authentication token"
            )
            
        user_id = user_data["user_id"]
        session_id = user_data.get("session_id")
        
        # Connect to enhanced WebSocket manager
        success = await enhanced_websocket_manager.connect(websocket, user_id, client_id, session_id)
        if not success:
            return
            
        logger.info(f"Enhanced WebSocket client connected: user_id={user_id}, client_id={client_id}")
        
        # Handle the WebSocket session
        await handle_websocket_session(client_id, websocket)
        
    except WebSocketException as e:
        logger.warning(f"WebSocket authentication failed: {e.reason}")
        await websocket.close(code=e.code, reason=e.reason)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        # Clean up connection
        await enhanced_websocket_manager.disconnect(client_id)


async def handle_websocket_session(client_id: str, websocket: WebSocket):
    """
    Handle the WebSocket session for message processing.
    
    Args:
        client_id: Client identifier
        websocket: WebSocket connection
    """
    try:
        # Get connection info for user context
        if client_id not in enhanced_websocket_manager.client_connections:
            logger.error(f"Connection info not found for client {client_id}")
            return
            
        connection_info = enhanced_websocket_manager.client_connections[client_id]
        user_id = connection_info.user_id
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                await handle_websocket_message(client_id, user_id, data)
                
            except WebSocketDisconnect:
                logger.info(f"Enhanced WebSocket client disconnected: user_id={user_id}, client_id={client_id}")
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                # Continue listening for messages
                
    except Exception as e:
        logger.error(f"Error in WebSocket session for client {client_id}: {e}")


async def handle_websocket_message(client_id: str, user_id: int, message: dict):
    """
    Handle incoming WebSocket messages from clients with enhanced functionality.
    
    Args:
        client_id: Client identifier
        user_id: Authenticated user ID
        message: Received message
    """
    try:
        message_type = message.get("type")
        
        if message_type == "ping":
            # Handle enhanced heartbeat ping
            pong_response = await enhanced_websocket_manager.handle_ping_pong(client_id, message)
            
            # Send pong back to client
            if client_id in enhanced_websocket_manager.client_connections:
                connection_info = enhanced_websocket_manager.client_connections[client_id]
                await enhanced_websocket_manager.send_to_connection(connection_info, pong_response)
                
        elif message_type == "subscribe":
            # Handle subscription to signal types with enhanced filtering
            signal_types = message.get("data", {}).get("signal_types", [])
            await enhanced_websocket_manager.subscribe_to_signals(user_id, signal_types)
            
            # Send subscription confirmation
            response = {
                "type": "subscription_confirmed",
                "data": {
                    "signal_types": signal_types,
                    "status": "subscribed",
                    "filtering_enabled": True
                }
            }
            
            if client_id in enhanced_websocket_manager.client_connections:
                connection_info = enhanced_websocket_manager.client_connections[client_id]
                await enhanced_websocket_manager.send_to_connection(connection_info, response)
                
        elif message_type == "set_preferences":
            # Handle user preference updates for message filtering
            preferences = message.get("data", {})
            await enhanced_websocket_manager.set_user_preferences(user_id, preferences)
            
            # Send preferences confirmation
            response = {
                "type": "preferences_updated",
                "data": {
                    "preferences": preferences,
                    "status": "updated"
                }
            }
            
            if client_id in enhanced_websocket_manager.client_connections:
                connection_info = enhanced_websocket_manager.client_connections[client_id]
                await enhanced_websocket_manager.send_to_connection(connection_info, response)
                
        elif message_type == "get_connection_info":
            # Handle request for connection information
            response = {
                "type": "connection_info",
                "data": {
                    "client_id": client_id,
                    "user_id": user_id,
                    "total_connections": enhanced_websocket_manager.get_connection_count(),
                    "user_connections": enhanced_websocket_manager.get_user_connection_count(user_id),
                    "features": {
                        "reconnection_supported": True,
                        "message_queuing": True,
                        "subscription_filtering": True,
                        "preference_filtering": True,
                        "rate_limiting": True
                    }
                }
            }
            
            if client_id in enhanced_websocket_manager.client_connections:
                connection_info = enhanced_websocket_manager.client_connections[client_id]
                await enhanced_websocket_manager.send_to_connection(connection_info, response)
                
        elif message_type == "unsubscribe":
            # Handle unsubscription from signal types
            signal_types = message.get("data", {}).get("signal_types", [])
            
            # Remove subscriptions (simple implementation)
            user_subscriptions = enhanced_websocket_manager.user_subscriptions[user_id]
            for signal_type in signal_types:
                user_subscriptions.discard(signal_type)
            
            # Update connection subscriptions
            if user_id in enhanced_websocket_manager.connections:
                for conn_info in enhanced_websocket_manager.connections[user_id]:
                    for signal_type in signal_types:
                        conn_info.subscriptions.discard(signal_type)
            
            # Send unsubscription confirmation
            response = {
                "type": "unsubscription_confirmed",
                "data": {
                    "signal_types": signal_types,
                    "status": "unsubscribed"
                }
            }
            
            if client_id in enhanced_websocket_manager.client_connections:
                connection_info = enhanced_websocket_manager.client_connections[client_id]
                await enhanced_websocket_manager.send_to_connection(connection_info, response)
                
        else:
            logger.warning(f"Unknown message type from user {user_id}: {message_type}")
            
            # Send error response for unknown message types
            error_response = {
                "type": "error",
                "data": {
                    "error": "unknown_message_type",
                    "message": f"Unknown message type: {message_type}",
                    "supported_types": [
                        "ping", "subscribe", "unsubscribe", 
                        "set_preferences", "get_connection_info"
                    ]
                }
            }
            
            if client_id in enhanced_websocket_manager.client_connections:
                connection_info = enhanced_websocket_manager.client_connections[client_id]
                await enhanced_websocket_manager.send_to_connection(connection_info, error_response)
            
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")
        
        # Send error response
        error_response = {
            "type": "error",
            "data": {
                "error": "message_handling_error",
                "message": "An error occurred while processing your message"
            }
        }
        
        try:
            if client_id in enhanced_websocket_manager.client_connections:
                connection_info = enhanced_websocket_manager.client_connections[client_id]
                await enhanced_websocket_manager.send_to_connection(connection_info, error_response)
        except:
            pass  # Avoid cascading errors


async def broadcast_signal_acceptance(user_id: int, signal_id: str, acceptance_data: dict):
    """
    Broadcast signal acceptance notification to WebSocket clients.
    Uses enhanced filtering and routing.
    
    Args:
        user_id: User who accepted the signal
        signal_id: Signal identifier
        acceptance_data: Acceptance details
    """
    try:
        message = {
            "type": "signal_accepted",
            "data": {
                "signal_id": signal_id,
                "user_id": user_id,
                "acceptance_data": acceptance_data,
                "priority": 1  # High priority message
            }
        }
        
        # Use enhanced manager to broadcast with filtering
        await enhanced_websocket_manager.send_filtered_message(user_id, message)
        
        logger.info(f"Broadcasted signal acceptance: signal_id={signal_id}, user_id={user_id}")
        
    except Exception as e:
        logger.error(f"Error broadcasting signal acceptance: {e}")


async def broadcast_new_signal(signal_data: dict):
    """
    Broadcast new signal to all subscribed users.
    Uses enhanced subscription-based routing.
    
    Args:
        signal_data: Signal information
    """
    try:
        message = {
            "type": "new_signal",
            "data": signal_data,
            "priority": 2  # Medium priority
        }
        
        # Use enhanced manager for subscription-based broadcasting
        await enhanced_websocket_manager.broadcast_signal_update(message)
        
        logger.info(f"Broadcasted new signal: {signal_data.get('symbol', 'unknown')}")
        
    except Exception as e:
        logger.error(f"Error broadcasting new signal: {e}")


async def broadcast_risk_alert(alert_data: dict, target_users: Optional[list] = None):
    """
    Broadcast risk alert to specific users or all active users.
    
    Args:
        alert_data: Risk alert information
        target_users: Optional list of specific user IDs to target
    """
    try:
        message = {
            "type": "risk_alert", 
            "data": alert_data,
            "priority": 3,  # High priority
            "source_cluster": "risk_assessment"
        }
        
        if target_users:
            # Send to specific users
            for user_id in target_users:
                await enhanced_websocket_manager.send_filtered_message(user_id, message)
        else:
            # Broadcast to all active users
            await enhanced_websocket_manager.broadcast_to_active_users(message)
        
        logger.info(f"Broadcasted risk alert to {len(target_users) if target_users else 'all'} users")
        
    except Exception as e:
        logger.error(f"Error broadcasting risk alert: {e}")


async def send_execution_update(user_id: int, execution_data: dict):
    """
    Send execution update to specific user.
    
    Args:
        user_id: Target user ID
        execution_data: Execution information
    """
    try:
        message = {
            "type": "execution_update",
            "data": execution_data,
            "priority": 2,  # Medium priority
            "source_cluster": "execution"
        }
        
        await enhanced_websocket_manager.send_filtered_message(user_id, message)
        
        logger.info(f"Sent execution update to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error sending execution update: {e}")


# Enhanced WebSocket manager status endpoint
@router.get("/status")
async def websocket_manager_status():
    """Get enhanced WebSocket manager status and metrics."""
    try:
        return {
            "status": "operational",
            "total_connections": enhanced_websocket_manager.get_connection_count(),
            "connected_users": len(enhanced_websocket_manager.get_connected_users()),
            "monitoring_active": enhanced_websocket_manager.is_monitoring_active,
            "features": {
                "heartbeat_monitoring": True,
                "reconnection_logic": True,
                "message_queuing": True,
                "subscription_filtering": True,
                "preference_filtering": True,
                "rate_limiting": True,
                "cross_cluster_events": True
            },
            "configuration": {
                "heartbeat_interval": enhanced_websocket_manager.heartbeat_interval,
                "heartbeat_timeout": enhanced_websocket_manager.heartbeat_timeout_seconds,
                "max_connections_per_user": enhanced_websocket_manager.max_connections_per_user,
                "message_retention_hours": enhanced_websocket_manager.message_retention_hours
            }
        }
    except Exception as e:
        logger.error(f"Error getting WebSocket status: {e}")
        return {
            "status": "error",
            "error": str(e)
        } 