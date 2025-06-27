"""
Redis-based session manager for secure user session handling.
Provides session creation, retrieval, invalidation, and TTL management.
"""

import json
import uuid
import redis
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from app.core.config import settings


# Redis connection configuration
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    db=0,  # Sessions in DB 0
    decode_responses=True
)

# Session key prefixes
SESSION_PREFIX = "session:"
USER_SESSIONS_PREFIX = "user_sessions:"


def create_session(session_data: Dict[str, Any], ttl_seconds: int = 3600) -> str:
    """
    Create a new Redis session.
    
    Args:
        session_data: Data to store in the session
        ttl_seconds: Session time-to-live in seconds (default: 1 hour)
        
    Returns:
        str: Generated session ID
    """
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    # Add metadata to session data
    session_data_with_meta = {
        **session_data,
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "last_accessed": datetime.utcnow().isoformat(),
        "ttl_seconds": ttl_seconds
    }
    
    # Store session in Redis
    session_key = f"{SESSION_PREFIX}{session_id}"
    redis_client.setex(
        session_key,
        ttl_seconds,
        json.dumps(session_data_with_meta)
    )
    
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve session data by session ID.
    
    Args:
        session_id: Session ID to retrieve
        
    Returns:
        Optional[Dict[str, Any]]: Session data if exists, None otherwise
    """
    try:
        session_key = f"{SESSION_PREFIX}{session_id}"
        session_data = redis_client.get(session_key)
        
        if session_data:
            data = json.loads(session_data)
            
            # Update last accessed time
            data["last_accessed"] = datetime.utcnow().isoformat()
            redis_client.setex(
                session_key,
                data.get("ttl_seconds", 3600),
                json.dumps(data)
            )
            
            return data
        
        return None
        
    except Exception:
        return None


def invalidate_session(session_id: str) -> bool:
    """
    Invalidate (delete) a session.
    
    Args:
        session_id: Session ID to invalidate
        
    Returns:
        bool: True if session was deleted, False otherwise
    """
    try:
        session_key = f"{SESSION_PREFIX}{session_id}"
        deleted = redis_client.delete(session_key)
        return deleted > 0
    except Exception:
        return False


def refresh_session(session_id: str, ttl_seconds: int = 3600) -> bool:
    """
    Refresh session TTL.
    
    Args:
        session_id: Session ID to refresh
        ttl_seconds: New TTL in seconds
        
    Returns:
        bool: True if session was refreshed, False otherwise
    """
    try:
        session_key = f"{SESSION_PREFIX}{session_id}"
        session_data = redis_client.get(session_key)
        
        if session_data:
            data = json.loads(session_data)
            data["ttl_seconds"] = ttl_seconds
            data["last_accessed"] = datetime.utcnow().isoformat()
            
            # Reset TTL
            redis_client.setex(session_key, ttl_seconds, json.dumps(data))
            return True
        
        return False
        
    except Exception:
        return False


def create_user_session(user_id: int, session_data: Dict[str, Any], ttl_seconds: int = 3600) -> str:
    """
    Create a session and track it for a specific user.
    
    Args:
        user_id: User ID
        session_data: Session data to store
        ttl_seconds: Session TTL
        
    Returns:
        str: Generated session ID
    """
    # Create regular session
    session_id = create_session(session_data, ttl_seconds)
    
    # Track this session for the user
    try:
        user_sessions_key = f"{USER_SESSIONS_PREFIX}{user_id}"
        
        # Add session to user's session list
        session_info = {
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "ip_address": session_data.get("ip_address"),
            "user_agent": session_data.get("user_agent")
        }
        
        redis_client.lpush(user_sessions_key, json.dumps(session_info))
        # Keep user session list for 7 days
        redis_client.expire(user_sessions_key, 7 * 24 * 3600)
        
    except Exception:
        # If tracking fails, session is still created
        pass
    
    return session_id


def get_user_sessions(user_id: int) -> List[Dict[str, Any]]:
    """
    Get all active sessions for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        List[Dict[str, Any]]: List of active session info
    """
    try:
        user_sessions_key = f"{USER_SESSIONS_PREFIX}{user_id}"
        session_strings = redis_client.lrange(user_sessions_key, 0, -1)
        
        active_sessions = []
        seen_ids = set()
        expired_sessions = []
        
        for session_string in session_strings:
            try:
                session_info = json.loads(session_string)
                session_id = session_info["session_id"]
                
                # Skip duplicates
                if session_id in seen_ids:
                    # Mark duplicate for removal
                    expired_sessions.append(session_string)
                    continue
                
                # Check if session still exists
                if get_session(session_id):
                    active_sessions.append(session_info)
                    seen_ids.add(session_id)
                else:
                    # Mark expired session for removal
                    expired_sessions.append(session_string)
            except Exception:
                # Mark invalid session for removal
                expired_sessions.append(session_string)
                continue
        
        # Clean up expired/duplicate sessions
        for expired_session in expired_sessions:
            redis_client.lrem(user_sessions_key, 1, expired_session)
        
        # Sort by created_at descending
        active_sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return active_sessions
        
    except Exception:
        return []


def cleanup_user_sessions(user_id: int, max_sessions: int = 5) -> int:
    """
    Clean up old sessions for a user, keeping only the most recent ones.
    
    Args:
        user_id: User ID
        max_sessions: Maximum number of sessions to keep
        
    Returns:
        int: Number of sessions cleaned up
    """
    try:
        user_sessions_key = f"{USER_SESSIONS_PREFIX}{user_id}"
        session_strings = redis_client.lrange(user_sessions_key, 0, -1)
        
        if len(session_strings) <= max_sessions:
            return 0
        
        # Get sessions to remove (oldest ones)
        sessions_to_remove = session_strings[max_sessions:]
        cleanup_count = 0
        
        for session_string in sessions_to_remove:
            try:
                session_info = json.loads(session_string)
                session_id = session_info["session_id"]
                
                # Invalidate the session
                if invalidate_session(session_id):
                    cleanup_count += 1
                
                # Remove from user's session list
                redis_client.lrem(user_sessions_key, 1, session_string)
                
            except Exception:
                continue
        
        return cleanup_count
        
    except Exception:
        return 0


def invalidate_all_user_sessions(user_id: int) -> int:
    """
    Invalidate all sessions for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        int: Number of sessions invalidated
    """
    try:
        user_sessions_key = f"{USER_SESSIONS_PREFIX}{user_id}"
        session_strings = redis_client.lrange(user_sessions_key, 0, -1)
        
        invalidated_count = 0
        for session_string in session_strings:
            try:
                session_info = json.loads(session_string)
                session_id = session_info["session_id"]
                
                if invalidate_session(session_id):
                    invalidated_count += 1
                    
            except Exception:
                continue
        
        # Clear user's session list
        redis_client.delete(user_sessions_key)
        
        return invalidated_count
        
    except Exception:
        return 0


def get_session_stats() -> Dict[str, Any]:
    """
    Get session statistics.
    
    Returns:
        Dict[str, Any]: Session statistics
    """
    try:
        # Count total sessions
        session_keys = redis_client.keys(f"{SESSION_PREFIX}*")
        total_sessions = len(session_keys)
        
        # Count user session lists
        user_session_keys = redis_client.keys(f"{USER_SESSIONS_PREFIX}*")
        active_users = len(user_session_keys)
        
        return {
            "total_sessions": total_sessions,
            "active_users": active_users,
            "redis_connected": True
        }
        
    except Exception:
        return {
            "total_sessions": 0,
            "active_users": 0,
            "redis_connected": False
        }


def count_user_sessions(user_id: int) -> int:
    """
    Count active sessions for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        int: Number of active sessions
    """
    try:
        # Use get_user_sessions which deduplicates and cleans up
        active_sessions = get_user_sessions(user_id)
        return len(active_sessions)
    except Exception:
        return 0


def health_check() -> bool:
    """
    Check if Redis connection is healthy.
    
    Returns:
        bool: True if Redis is accessible, False otherwise
    """
    try:
        redis_client.ping()
        return True
    except Exception:
        return False 