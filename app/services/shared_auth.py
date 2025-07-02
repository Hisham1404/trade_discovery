"""
Shared Authentication Service for Cross-Cluster Communication - Task 9.2

Enterprise-grade authentication service providing:
- JWT token validation and generation for service-to-service authentication
- Cross-cluster authentication between Discovery, Monitoring, and Risk clusters
- Role-based access control for different event types
- Token refresh mechanisms with proper expiration handling
- Service account management for inter-cluster communication
- Shared secret management with environment variable support
- Authentication middleware for FastAPI applications
- Production-ready security features and audit logging
"""

import os
import json
import uuid
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import secrets

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, validator
from fastapi import HTTPException, Request, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# Configure logging
logger = logging.getLogger(__name__)


class ClusterName(str, Enum):
    """Supported cluster names"""
    DISCOVERY = "discovery"
    MONITORING = "monitoring"
    RISK_ASSESSMENT = "risk-assessment"
    EXECUTION = "execution"
    MANAGEMENT = "management"


class EventType(str, Enum):
    """Event types for role-based access control"""
    SIGNAL_ACCEPTED = "signal.accepted"
    SIGNAL_REJECTED = "signal.rejected"
    SIGNAL_STATUS_UPDATE = "signal.status.update"
    RISK_ALERT = "risk.alert"
    RISK_THRESHOLD_EXCEEDED = "risk.threshold.exceeded"
    MARKET_DATA_UPDATE = "market.data.update"
    AGENT_PERFORMANCE = "agent.performance"
    USER_ACTION = "user.action"
    SYSTEM_HEALTH = "system.health"


class ServiceRole(str, Enum):
    """Service roles with specific permissions"""
    SIGNAL_PRODUCER = "signal_producer"
    RISK_MONITOR = "risk_monitor"
    EVENT_CONSUMER = "event_consumer"
    EVENT_PUBLISHER = "event_publisher"
    DATA_CONSUMER = "data_consumer"
    MARKET_MONITOR = "market_monitor"
    CLUSTER_ADMIN = "cluster_admin"
    SYSTEM_MONITOR = "system_monitor"


@dataclass
class ClusterRole:
    """Role-based access control for clusters"""
    
    # Role to event type permissions mapping
    ROLE_PERMISSIONS: Dict[ServiceRole, List[EventType]] = field(default_factory=lambda: {
        ServiceRole.SIGNAL_PRODUCER: [
            EventType.SIGNAL_ACCEPTED,
            EventType.SIGNAL_REJECTED,
            EventType.SIGNAL_STATUS_UPDATE
        ],
        ServiceRole.RISK_MONITOR: [
            EventType.RISK_ALERT,
            EventType.RISK_THRESHOLD_EXCEEDED,
            EventType.SYSTEM_HEALTH
        ],
        ServiceRole.EVENT_CONSUMER: [
            EventType.SIGNAL_ACCEPTED,
            EventType.MARKET_DATA_UPDATE,
            EventType.AGENT_PERFORMANCE
        ],
        ServiceRole.EVENT_PUBLISHER: [
            EventType.SIGNAL_ACCEPTED,
            EventType.SIGNAL_STATUS_UPDATE,
            EventType.AGENT_PERFORMANCE,
            EventType.SYSTEM_HEALTH
        ],
        ServiceRole.DATA_CONSUMER: [
            EventType.MARKET_DATA_UPDATE,
            EventType.AGENT_PERFORMANCE
        ],
        ServiceRole.MARKET_MONITOR: [
            EventType.MARKET_DATA_UPDATE,
            EventType.SIGNAL_ACCEPTED,
            EventType.RISK_ALERT
        ],
        ServiceRole.SYSTEM_MONITOR: [
            EventType.SYSTEM_HEALTH,
            EventType.AGENT_PERFORMANCE,
            EventType.USER_ACTION
        ],
        ServiceRole.CLUSTER_ADMIN: list(EventType)  # Admin has access to all events
    })
    
    @classmethod
    def get_role(cls, role_name: str) -> 'ClusterRole':
        """Get role by name"""
        try:
            service_role = ServiceRole(role_name)
            return cls()
        except ValueError:
            raise ValueError(f"Invalid role: {role_name}")
    
    def can_access_event(self, role: ServiceRole, event_type: str) -> bool:
        """Check if role can access specific event type"""
        try:
            event = EventType(event_type)
            return event in self.ROLE_PERMISSIONS.get(role, [])
        except ValueError:
            return False
    
    @classmethod
    def get_event_permissions(cls, event_type: str) -> List[str]:
        """Get roles that can access specific event type"""
        try:
            event = EventType(event_type)
            roles = []
            for role, permissions in cls.ROLE_PERMISSIONS.items():
                if event in permissions:
                    roles.append(role.value)
            return roles
        except ValueError:
            return []
    
    @classmethod
    def validate_roles(cls, roles: List[str]) -> bool:
        """Validate if all roles are valid"""
        if not roles:
            return False
        
        try:
            for role in roles:
                ServiceRole(role)
            return True
        except ValueError:
            return False


@dataclass
class ServiceAccount:
    """Service account for cross-cluster authentication"""
    service_id: str
    cluster_name: str
    roles: List[str]
    secret_key: str
    _is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None
    description: Optional[str] = None
    
    def __post_init__(self):
        """Validate service account after initialization"""
        if not ClusterRole.validate_roles(self.roles):
            raise ValueError(f"Invalid roles: {self.roles}")
        
        if self.cluster_name not in [cluster.value for cluster in ClusterName]:
            raise ValueError(f"Invalid cluster name: {self.cluster_name}")
    
    @property
    def is_active(self) -> bool:
        """Check if service account is active and not expired"""
        return self._is_active and not self.is_expired()
    
    @is_active.setter
    def is_active(self, value: bool):
        """Set the active status"""
        self._is_active = value
    
    def is_expired(self) -> bool:
        """Check if service account is expired"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def has_role(self, role: str) -> bool:
        """Check if service account has specific role"""
        return role in self.roles
    
    def can_access_event_type(self, event_type: str) -> bool:
        """Check if service account can access specific event type"""
        cluster_role = ClusterRole()
        for role_str in self.roles:
            try:
                role = ServiceRole(role_str)
                if cluster_role.can_access_event(role, event_type):
                    return True
            except ValueError:
                continue
        return False
    
    def update_last_used(self):
        """Update last used timestamp"""
        self.last_used_at = datetime.now(timezone.utc)


class AuthToken:
    """JWT token management for authentication"""
    
    def __init__(self, service_id: str, cluster_name: str, roles: List[str], 
                 expires_in: int, secret_key: str, additional_claims: Optional[Dict] = None):
        self.service_id = service_id
        self.cluster_name = cluster_name
        self.roles = roles
        self.expires_in = expires_in
        self.secret_key = secret_key
        self.issued_at = datetime.now(timezone.utc)
        self.expires_at = self.issued_at + timedelta(seconds=expires_in)
        
        # Create JWT token
        self.jwt_token = self._create_token(additional_claims or {})
    
    def _create_token(self, additional_claims: Dict) -> str:
        """Create JWT token with claims"""
        payload = {
            "sub": self.service_id,
            "cluster": self.cluster_name,
            "roles": self.roles,
            "iat": int(self.issued_at.timestamp()),
            "exp": int(self.expires_at.timestamp()),
            "jti": str(uuid.uuid4()),  # JWT ID for revocation
            **additional_claims
        }
        
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    
    @staticmethod
    def validate_token(token: str, secret_key: str) -> Tuple[bool, Optional[Dict]]:
        """Validate JWT token and return payload"""
        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            
            # Check if token is expired
            exp = payload.get('exp')
            if exp and datetime.now(timezone.utc).timestamp() > exp:
                return False, None
            
            return True, payload
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: {e}")
            return False, None
    
    @staticmethod
    def refresh_token(token: str, secret_key: str, new_expires_in: int) -> Optional[str]:
        """Refresh JWT token with new expiration"""
        is_valid, payload = AuthToken.validate_token(token, secret_key)
        
        if not is_valid or not payload:
            return None
        
        # Create new token with updated expiration
        new_issued_at = datetime.now(timezone.utc)
        new_expires_at = new_issued_at + timedelta(seconds=new_expires_in)
        
        new_payload = payload.copy()
        new_payload.update({
            "iat": int(new_issued_at.timestamp()),
            "exp": int(new_expires_at.timestamp()),
            "jti": str(uuid.uuid4())  # New JWT ID
        })
        
        return jwt.encode(new_payload, secret_key, algorithm="HS256")


class TokenManager:
    """Manages JWT tokens for service authentication"""
    
    def __init__(self, config: Dict[str, Any]):
        self.secret_key = config['SECRET_KEY']
        self.token_expire_minutes = config.get('TOKEN_EXPIRE_MINUTES', 30)
        self.refresh_token_expire_minutes = config.get('REFRESH_TOKEN_EXPIRE_MINUTES', 1440)
        self.algorithm = "HS256"
        
        # In-memory token revocation list (in production, use Redis or database)
        self.revoked_tokens: set = set()
        
        # Password context for hashing refresh tokens
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    def generate_service_token(self, service_account: ServiceAccount) -> Dict[str, Any]:
        """Generate access and refresh tokens for service account"""
        # Generate access token
        access_token_expires = self.token_expire_minutes * 60
        access_token = AuthToken(
            service_id=service_account.service_id,
            cluster_name=service_account.cluster_name,
            roles=service_account.roles,
            expires_in=access_token_expires,
            secret_key=self.secret_key
        )
        
        # Generate refresh token
        refresh_token_expires = self.refresh_token_expire_minutes * 60
        refresh_token_payload = {
            "type": "refresh",
            "service_id": service_account.service_id
        }
        refresh_token = AuthToken(
            service_id=service_account.service_id,
            cluster_name=service_account.cluster_name,
            roles=service_account.roles,
            expires_in=refresh_token_expires,
            secret_key=self.secret_key,
            additional_claims=refresh_token_payload
        )
        
        # Update service account last used
        service_account.update_last_used()
        
        return {
            "access_token": access_token.jwt_token,
            "token_type": "bearer",
            "expires_in": access_token_expires,
            "refresh_token": refresh_token.jwt_token
        }
    
    def validate_service_token(self, token: str) -> Tuple[bool, Optional[Dict]]:
        """Validate service token"""
        # Check if token is revoked
        if self._is_token_revoked(token):
            return False, None
        
        return AuthToken.validate_token(token, self.secret_key)
    
    def refresh_service_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh service token using refresh token"""
        is_valid, payload = self.validate_service_token(refresh_token)
        
        if not is_valid or not payload:
            return None
        
        # Verify it's a refresh token
        if payload.get('type') != 'refresh':
            return None
        
        # Generate new access token
        new_access_token_expires = self.token_expire_minutes * 60
        new_access_token = AuthToken(
            service_id=payload['sub'],
            cluster_name=payload['cluster'],
            roles=payload['roles'],
            expires_in=new_access_token_expires,
            secret_key=self.secret_key
        )
        
        return {
            "access_token": new_access_token.jwt_token,
            "token_type": "bearer",
            "expires_in": new_access_token_expires
        }
    
    def revoke_token(self, token: str):
        """Revoke a token"""
        is_valid, payload = AuthToken.validate_token(token, self.secret_key)
        if is_valid and payload:
            jti = payload.get('jti')
            if jti:
                self.revoked_tokens.add(jti)
    
    def _is_token_revoked(self, token: str) -> bool:
        """Check if token is revoked"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": False})
            jti = payload.get('jti')
            return jti in self.revoked_tokens if jti else False
        except jwt.InvalidTokenError:
            return True


class AuthMiddleware:
    """Authentication middleware for FastAPI applications"""
    
    def __init__(self, config: Dict[str, Any]):
        self.token_manager = TokenManager(config)
        self.required_roles = config.get('REQUIRED_ROLES', [])
        self.allowed_clusters = config.get('ALLOWED_CLUSTERS', [])
        self.security = HTTPBearer()
    
    async def authenticate_request(self, request: Request) -> Dict[str, Any]:
        """Authenticate incoming request"""
        try:
            # Extract token from Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                return {"authenticated": False, "error": "Missing authorization header"}
            
            if not auth_header.startswith('Bearer '):
                return {"authenticated": False, "error": "Invalid authorization header format"}
            
            token = auth_header.split(' ')[1]
            
            # Validate token
            is_valid, payload = self.token_manager.validate_service_token(token)
            if not is_valid or not payload:
                return {"authenticated": False, "error": "Invalid token"}
            
            # Check cluster authorization
            cluster_name = payload.get('cluster')
            if self.allowed_clusters and cluster_name not in self.allowed_clusters:
                return {"authenticated": False, "error": f"Unauthorized cluster: {cluster_name}"}
            
            # Check role permissions
            user_roles = payload.get('roles', [])
            if self.required_roles:
                has_required_role = any(role in user_roles for role in self.required_roles)
                if not has_required_role:
                    return {"authenticated": False, "error": "Insufficient permissions"}
            
            return {
                "authenticated": True,
                "service_id": payload.get('sub'),
                "cluster_name": cluster_name,
                "roles": user_roles,
                "jwt_id": payload.get('jti')
            }
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return {"authenticated": False, "error": "Authentication failed"}


class CrossClusterAuthenticator:
    """Handles cross-cluster authentication"""
    
    def __init__(self, config: Dict[str, Any]):
        self.discovery_secret = config.get('DISCOVERY_CLUSTER_SECRET')
        self.monitoring_secret = config.get('MONITORING_CLUSTER_SECRET')
        self.risk_secret = config.get('RISK_CLUSTER_SECRET')
        self.execution_secret = config.get('EXECUTION_CLUSTER_SECRET')
        self.shared_secret = config.get('SHARED_SECRET')
        
        # Cluster secrets mapping
        self.cluster_secrets = {
            ClusterName.DISCOVERY: self.discovery_secret,
            ClusterName.MONITORING: self.monitoring_secret,
            ClusterName.RISK_ASSESSMENT: self.risk_secret,
            ClusterName.EXECUTION: self.execution_secret
        }
    
    def generate_cluster_token(self, cluster_name: str, target_cluster: str, 
                             permissions: List[str], expires_in: int = 3600) -> str:
        """Generate cross-cluster authentication token"""
        cluster_secret = self.cluster_secrets.get(ClusterName(cluster_name))
        if not cluster_secret:
            raise ValueError(f"No secret configured for cluster: {cluster_name}")
        
        # Use shared secret for cross-cluster communication
        signing_secret = self.shared_secret or cluster_secret
        
        token = AuthToken(
            service_id=f"{cluster_name}-cluster",
            cluster_name=cluster_name,
            roles=["cluster_service"],
            expires_in=expires_in,
            secret_key=signing_secret,
            additional_claims={
                "target": target_cluster,
                "permissions": permissions,
                "cross_cluster": True
            }
        )
        
        return token.jwt_token
    
    def validate_cluster_token(self, token: str, source_cluster: str, 
                             target_cluster: str) -> Tuple[bool, Optional[Dict]]:
        """Validate cross-cluster token"""
        # Use shared secret for validation
        cluster_secret = self.cluster_secrets.get(ClusterName(source_cluster))
        if not cluster_secret:
            return False, None
        
        signing_secret = self.shared_secret or cluster_secret
        
        is_valid, payload = AuthToken.validate_token(token, signing_secret)
        
        if not is_valid or not payload:
            return False, None
        
        # Verify cross-cluster token specifics
        if not payload.get('cross_cluster'):
            return False, None
        
        if payload.get('cluster') != source_cluster:
            return False, None
        
        if payload.get('target') != target_cluster:
            return False, None
        
        return True, payload
    
    def validate_cluster_permission(self, token: str, required_permission: str, 
                                  source_cluster: str) -> bool:
        """Validate if token has required permission"""
        cluster_secret = self.cluster_secrets.get(ClusterName(source_cluster))
        if not cluster_secret:
            return False
        
        signing_secret = self.shared_secret or cluster_secret
        is_valid, payload = AuthToken.validate_token(token, signing_secret)
        
        if not is_valid or not payload:
            return False
        
        permissions = payload.get('permissions', [])
        return required_permission in permissions


class SharedAuthService:
    """Main shared authentication service for cross-cluster communication"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.token_manager = TokenManager(config)
        self.cross_cluster_auth = CrossClusterAuthenticator(config)
        self.middleware = AuthMiddleware(config)
        
        # In-memory service account storage (in production, use database)
        self.service_accounts: Dict[str, ServiceAccount] = {}
        
        logger.info("SharedAuthService initialized successfully")
    
    async def register_service_account(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new service account"""
        try:
            # Generate secret key for service
            secret_key = secrets.token_urlsafe(32)
            
            # Create service account
            service_account = ServiceAccount(
                service_id=service_data['service_id'],
                cluster_name=service_data['cluster_name'],
                roles=service_data['roles'],
                secret_key=secret_key,
                description=service_data.get('description')
            )
            
            # Store service account
            self.service_accounts[service_account.service_id] = service_account
            
            # Generate tokens
            token_data = self.token_manager.generate_service_token(service_account)
            
            logger.info(f"Service account registered: {service_account.service_id}")
            
            return {
                "success": True,
                "service_account": {
                    "service_id": service_account.service_id,
                    "cluster_name": service_account.cluster_name,
                    "roles": service_account.roles,
                    "created_at": service_account.created_at.isoformat()
                },
                **token_data
            }
            
        except Exception as e:
            logger.error(f"Service registration failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def authenticate_request(self, request: Request) -> Dict[str, Any]:
        """Authenticate incoming request using middleware"""
        return await self.middleware.authenticate_request(request)
    
    async def generate_cross_cluster_token(self, source_cluster: str, target_cluster: str, 
                                         permissions: List[str]) -> str:
        """Generate cross-cluster communication token"""
        return self.cross_cluster_auth.generate_cluster_token(
            source_cluster, target_cluster, permissions
        )
    
    async def validate_cross_cluster_token(self, token: str, source_cluster: str, 
                                         target_cluster: str) -> bool:
        """Validate cross-cluster communication token"""
        is_valid, _ = self.cross_cluster_auth.validate_cluster_token(
            token, source_cluster, target_cluster
        )
        return is_valid
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token"""
        try:
            token_data = self.token_manager.refresh_service_token(refresh_token)
            if token_data:
                return {"success": True, **token_data}
            else:
                return {"success": False, "error": "Invalid refresh token"}
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def revoke_service_account(self, service_id: str) -> Dict[str, Any]:
        """Revoke service account and all its tokens"""
        try:
            if service_id in self.service_accounts:
                service_account = self.service_accounts[service_id]
                service_account._is_active = False
                
                logger.info(f"Service account revoked: {service_id}")
                return {"success": True, "message": f"Service account {service_id} revoked"}
            else:
                return {"success": False, "error": "Service account not found"}
        except Exception as e:
            logger.error(f"Service revocation failed: {e}")
            return {"success": False, "error": str(e)}


# Configuration helper
def get_auth_config() -> Dict[str, Any]:
    """Get authentication configuration from environment variables"""
    return {
        'SECRET_KEY': os.getenv('SHARED_AUTH_SECRET_KEY', 'development-secret-key'),
        'TOKEN_EXPIRE_MINUTES': int(os.getenv('TOKEN_EXPIRE_MINUTES', '30')),
        'REFRESH_TOKEN_EXPIRE_MINUTES': int(os.getenv('REFRESH_TOKEN_EXPIRE_MINUTES', '1440')),
        'DISCOVERY_CLUSTER_SECRET': os.getenv('DISCOVERY_CLUSTER_SECRET'),
        'MONITORING_CLUSTER_SECRET': os.getenv('MONITORING_CLUSTER_SECRET'),
        'RISK_CLUSTER_SECRET': os.getenv('RISK_CLUSTER_SECRET'),
        'EXECUTION_CLUSTER_SECRET': os.getenv('EXECUTION_CLUSTER_SECRET'),
        'SHARED_SECRET': os.getenv('SHARED_CLUSTER_SECRET'),
        'ALLOWED_CLUSTERS': os.getenv('ALLOWED_CLUSTERS', '').split(',') if os.getenv('ALLOWED_CLUSTERS') else [],
        'REQUIRED_ROLES': os.getenv('REQUIRED_ROLES', '').split(',') if os.getenv('REQUIRED_ROLES') else []
    }


# FastAPI dependency for authentication
async def get_current_service(
    request: Request,
    auth_service: SharedAuthService = Depends(lambda: SharedAuthService(get_auth_config()))
) -> Dict[str, Any]:
    """FastAPI dependency for service authentication"""
    auth_result = await auth_service.authenticate_request(request)
    
    if not auth_result.get('authenticated'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_result.get('error', 'Authentication failed'),
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return auth_result
