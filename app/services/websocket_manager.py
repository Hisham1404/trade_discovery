"""
WebSocket Connection Manager for real-time signal broadcasting.
Implements connection tracking, authentication, and message broadcasting using FastAPI WebSocket patterns.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Set
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Information about a WebSocket connection."""
    websocket: WebSocket
    user_id: int
    client_id: str
    connected_at: datetime
    last_ping: datetime


class WebSocketManager:
    """
    Manages WebSocket connections for real-time signal broadcasting.
    Implements connection tracking, authentication, and message broadcasting.
    """
    
    def __init__(self):
        # Active connections: user_id -> list of ConnectionInfo
        # Using list instead of set because ConnectionInfo contains a WebSocket instance
        # which is not hashable. Lists avoid hashability issues that could lead to
        # runtime errors and hanging test runs.
        self.connections: Dict[int, List[ConnectionInfo]] = {}
        # Client ID to connection mapping for fast lookup
        self.client_connections: Dict[str, ConnectionInfo] = {}
        # Connection limits per user
        self.max_connections_per_user = 5
        
    async def connect(self, websocket: WebSocket, user_id: int, client_id: str) -> bool:
        """
        Accept and register a new WebSocket connection.
        
        Args:
            websocket: WebSocket instance
            user_id: Authenticated user ID
            client_id: Unique client identifier
            
        Returns:
            bool: True if connection successful, False if rejected
        """
        try:
            # Check connection limits
            if user_id in self.connections and len(self.connections[user_id]) >= self.max_connections_per_user:
                logger.warning(f"User {user_id} exceeded connection limit")
                await websocket.close(code=1008, reason="Connection limit exceeded")
                return False
            
            # Accept the connection
            await websocket.accept()
            
            # Create connection info
            now = datetime.now(timezone.utc)
            connection_info = ConnectionInfo(
                websocket=websocket,
                user_id=user_id,
                client_id=client_id,
                connected_at=now,
                last_ping=now
            )
            
            # Register connection
            if user_id not in self.connections:
                self.connections[user_id] = []
            
            self.connections[user_id].append(connection_info)
            self.client_connections[client_id] = connection_info
            
            logger.info(f"WebSocket connected: user_id={user_id}, client_id={client_id}")
            
            # Send connection established message
            await self.send_to_connection(connection_info, {
                "type": "connection_established",
                "data": {
                    "user_id": user_id,
                    "client_id": client_id,
                    "connected_at": now.isoformat()
                },
                "timestamp": now.isoformat()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket: {e}")
            return False
    
    async def disconnect(self, client_id: str):
        """
        Disconnect and unregister a WebSocket connection.
        
        Args:
            client_id: Client identifier to disconnect
        """
        try:
            if client_id not in self.client_connections:
                return
                
            connection_info = self.client_connections[client_id]
            user_id = connection_info.user_id
            
            # Remove from tracking
            if user_id in self.connections:
                # Remove the connection info if present
                try:
                    self.connections[user_id].remove(connection_info)
                except ValueError:
                    pass  # Already removed or never existed
            
            del self.client_connections[client_id]
            
            logger.info(f"WebSocket disconnected: user_id={user_id}, client_id={client_id}")
            
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")
    
    async def send_to_user(self, user_id: int, message: Dict[str, Any]):
        """
        Send message to all connections for a specific user.
        
        Args:
            user_id: Target user ID
            message: Message to send
        """
        if user_id not in self.connections:
            return
            
        # Send to all user's connections
        disconnected_connections = []
        for connection_info in self.connections[user_id][:]:
            try:
                await self.send_to_connection(connection_info, message)
            except WebSocketDisconnect:
                disconnected_connections.append(connection_info)
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                disconnected_connections.append(connection_info)
        
        # Clean up disconnected connections
        for connection_info in disconnected_connections:
            await self.disconnect(connection_info.client_id)
    
    async def send_to_connection(self, connection_info: ConnectionInfo, message: Dict[str, Any]):
        """
        Send message to a specific connection.
        
        Args:
            connection_info: Target connection
            message: Message to send
        """
        try:
            # Ensure timestamp is present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now(timezone.utc).isoformat()
                
            await connection_info.websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message to connection {connection_info.client_id}: {e}")
            raise
    
    async def broadcast(self, message: Dict[str, Any], exclude_user: int = None):
        """
        Broadcast message to all connected users.
        
        Args:
            message: Message to broadcast
            exclude_user: Optional user ID to exclude from broadcast
        """
        if not self.connections:
            return
            
        # Ensure timestamp is present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        # Send to all users
        for user_id in list(self.connections.keys()):
            if exclude_user and user_id == exclude_user:
                continue
                
            await self.send_to_user(user_id, message)
    
    async def handle_ping_pong(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle ping-pong heartbeat mechanism.
        
        Args:
            client_id: Client sending ping
            message: Ping message
            
        Returns:
            Pong response message
        """
        if client_id in self.client_connections:
            # Update last ping time
            self.client_connections[client_id].last_ping = datetime.now(timezone.utc)
        
        return {
            "type": "pong",
            "data": {"received_at": datetime.now(timezone.utc).isoformat()},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self.client_connections)
    
    def get_user_connection_count(self, user_id: int) -> int:
        """Get number of connections for a specific user."""
        return len(self.connections.get(user_id, []))
    
    def get_connected_users(self) -> List[int]:
        """Get list of all connected user IDs."""
        return list(self.connections.keys())


# Global WebSocket manager instance
websocket_manager = WebSocketManager() 