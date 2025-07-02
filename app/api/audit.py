"""
Audit Logging and SEBI Compliance API - Task 8.6

This module provides API endpoints for:
1. Accessing and querying immutable audit logs
2. Generating and retrieving SEBI compliance reports
3. Verifying audit log integrity
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query, Path, Response
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field, validator

from app.core.config import get_settings
from app.api.dependencies import get_current_user, get_current_admin_user
from monitoring.services.immutable_audit_logger import (
    get_audit_logger, 
    ImmutableAuditLogger,
    AuditActionType,
    AuditLogEntry
)
from monitoring.services.compliance_report_generator import (
    get_compliance_report_generator,
    ComplianceReportGenerator,
    ComplianceReportType,
    ComplianceReportFormat
)

# Create router
router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    responses={404: {"description": "Not found"}},
)

# Models for request/response
class AuditLogFilterParams(BaseModel):
    """Parameters for filtering audit logs"""
    action_type: Optional[AuditActionType] = None
    user_id: Optional[str] = None
    service_id: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)

class AuditLogResponse(BaseModel):
    """Response model for audit logs"""
    logs: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int
    
class ComplianceReportRequest(BaseModel):
    """Request model for generating compliance reports"""
    report_type: ComplianceReportType
    start_date: datetime
    end_date: datetime
    report_format: ComplianceReportFormat = ComplianceReportFormat.PDF
    
    @validator('end_date')
    def end_date_after_start_date(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v

class ComplianceReportResponse(BaseModel):
    """Response model for compliance report generation"""
    report_id: str
    status: str = "processing"
    message: str

class ComplianceReportListResponse(BaseModel):
    """Response model for listing compliance reports"""
    reports: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int

class AuditLogIntegrityResponse(BaseModel):
    """Response model for audit log integrity verification"""
    verified: bool
    message: str
    entries_checked: int
    issues: List[Dict[str, Any]]

# Endpoints

@router.post("/logs", response_model=AuditLogResponse)
async def get_audit_logs(
    filter_params: AuditLogFilterParams,
    audit_logger: ImmutableAuditLogger = Depends(get_audit_logger),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Query audit logs with filtering
    
    Requires authentication. Admin users can see all logs, regular users only see their own logs.
    """
    # Regular users can only see their own logs
    if "admin" not in current_user.get("roles", []):
        filter_params.user_id = current_user["id"]
    
    logs, total = await audit_logger.get_audit_logs(
        action_type=filter_params.action_type,
        user_id=filter_params.user_id,
        service_id=filter_params.service_id,
        resource_id=filter_params.resource_id,
        resource_type=filter_params.resource_type,
        start_time=filter_params.start_time,
        end_time=filter_params.end_time,
        limit=filter_params.limit,
        offset=filter_params.offset
    )
    
    return {
        "logs": logs,
        "total": total,
        "limit": filter_params.limit,
        "offset": filter_params.offset
    }

@router.post("/logs/verify", response_model=AuditLogIntegrityResponse)
async def verify_audit_log_integrity(
    start_id: Optional[str] = None,
    end_id: Optional[str] = None,
    audit_logger: ImmutableAuditLogger = Depends(get_audit_logger),
    current_user: Dict[str, Any] = Depends(get_current_admin_user)  # Admin only
):
    """
    Verify the integrity of the audit log chain
    
    Admin only endpoint. Verifies the cryptographic integrity of the audit log chain.
    """
    result = await audit_logger.verify_log_integrity(start_id, end_id)
    return result

@router.post("/compliance/reports", response_model=ComplianceReportResponse)
async def generate_compliance_report(
    report_request: ComplianceReportRequest,
    background_tasks: BackgroundTasks,
    report_generator: ComplianceReportGenerator = Depends(get_compliance_report_generator),
    current_user: Dict[str, Any] = Depends(get_current_admin_user)  # Admin only
):
    """
    Generate a new SEBI compliance report
    
    Admin only endpoint. Report generation happens in the background.
    """
    report_id = await report_generator.generate_report(
        report_type=report_request.report_type,
        start_date=report_request.start_date,
        end_date=report_request.end_date,
        report_format=report_request.report_format,
        generated_by=current_user["id"],
        background_tasks=background_tasks
    )
    
    return {
        "report_id": report_id,
        "status": "processing",
        "message": "Report generation started. Use the report ID to check status and download when complete."
    }

@router.get("/compliance/reports", response_model=ComplianceReportListResponse)
async def list_compliance_reports(
    report_type: Optional[ComplianceReportType] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    report_generator: ComplianceReportGenerator = Depends(get_compliance_report_generator),
    current_user: Dict[str, Any] = Depends(get_current_admin_user)  # Admin only
):
    """
    List available compliance reports
    
    Admin only endpoint. Lists all available compliance reports with filtering options.
    """
    reports, total = await report_generator.list_reports(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    
    return {
        "reports": reports,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@router.get("/compliance/reports/{report_id}")
async def get_compliance_report(
    report_id: str = Path(..., description="ID of the compliance report to retrieve"),
    report_generator: ComplianceReportGenerator = Depends(get_compliance_report_generator),
    current_user: Dict[str, Any] = Depends(get_current_admin_user)  # Admin only
):
    """
    Download a compliance report
    
    Admin only endpoint. Downloads the specified compliance report in its original format.
    """
    try:
        content, content_type, filename = await report_generator.get_report(report_id)
        
        return StreamingResponse(
            iter([content]),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving report: {str(e)}"
        ) 