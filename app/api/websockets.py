"""
WebSocket endpoints for real-time signal updates and notifications.
Implements authenticated WebSocket connections with JWT validation and message broadcasting.
"""

import logging
import uuid
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from fastapi.exceptions import WebSocketException

from app.services.websocket_manager import websocket_manager
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
            "is_2fa_enabled": payload.get("is_2fa_enabled", False)
        }
        
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
        return None


@router.websocket("/signals")
async def websocket_signals_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time signal updates.
    Requires JWT authentication via query parameter.
    
    Args:
        websocket: WebSocket connection
        token: JWT authentication token
    """
    client_id = str(uuid.uuid4())
    
    try:
        # Authenticate the connection
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
        
        # Connect to WebSocket manager
        success = await websocket_manager.connect(websocket, user_id, client_id)
        if not success:
            return
            
        logger.info(f"WebSocket client connected: user_id={user_id}, client_id={client_id}")
        
        # Connection established message is sent by websocket_manager.connect()
        # No need to send it again here
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                await handle_websocket_message(client_id, user_id, data)
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected: user_id={user_id}, client_id={client_id}")
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                # Continue listening for messages
                
    except WebSocketException as e:
        logger.warning(f"WebSocket authentication failed: {e.reason}")
        await websocket.close(code=e.code, reason=e.reason)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        # Clean up connection
        await websocket_manager.disconnect(client_id)


async def handle_websocket_message(client_id: str, user_id: int, message: dict):
    """
    Handle incoming WebSocket messages from clients.
    
    Args:
        client_id: Client identifier
        user_id: Authenticated user ID
        message: Received message
    """
    try:
        message_type = message.get("type")
        
        if message_type == "ping":
            # Handle heartbeat ping
            pong_response = await websocket_manager.handle_ping_pong(client_id, message)
            
            # Send pong back to client
            if client_id in websocket_manager.client_connections:
                connection_info = websocket_manager.client_connections[client_id]
                await websocket_manager.send_to_connection(connection_info, pong_response)
                
        elif message_type == "subscribe":
            # Handle subscription to signal types
            signal_types = message.get("data", {}).get("signal_types", [])
            logger.info(f"User {user_id} subscribed to signal types: {signal_types}")
            
            # In a real implementation, you would store subscription preferences
            # For now, acknowledge the subscription
            response = {
                "type": "subscription_confirmed",
                "data": {
                    "signal_types": signal_types,
                    "status": "subscribed"
                }
            }
            
            if client_id in websocket_manager.client_connections:
                connection_info = websocket_manager.client_connections[client_id]
                await websocket_manager.send_to_connection(connection_info, response)
                
        else:
            logger.warning(f"Unknown message type from user {user_id}: {message_type}")
            
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")


async def broadcast_signal_update(signal_data: dict):
    """
    Broadcast signal update to all connected WebSocket clients.
    
    Args:
        signal_data: Signal data to broadcast
    """
    try:
        message = {
            "type": "new_signal",
            "data": signal_data
        }
        
        await websocket_manager.broadcast(message)
        logger.info(f"Broadcasted signal update: {signal_data.get('id', 'unknown')}")
        
    except Exception as e:
        logger.error(f"Error broadcasting signal update: {e}")


async def broadcast_signal_acceptance(user_id: int, signal_id: str, acceptance_data: dict):
    """
    Broadcast signal acceptance notification to WebSocket clients.
    
    Args:
        user_id: User who accepted the signal
        signal_id: ID of accepted signal
        acceptance_data: Acceptance details
    """
    try:
        message = {
            "type": "signal_accepted",
            "data": {
                "signal_id": signal_id,
                "user_id": user_id,
                "acceptance_data": acceptance_data
            }
        }
        
        # Broadcast to all users except the one who accepted
        await websocket_manager.broadcast(message, exclude_user=user_id)
        logger.info(f"Broadcasted signal acceptance: user_id={user_id}, signal_id={signal_id}")
        
    except Exception as e:
        logger.error(f"Error broadcasting signal acceptance: {e}") 