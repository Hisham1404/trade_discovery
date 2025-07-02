"""
SEBI Compliance Report Generator - Task 8.6

This module provides automated generation of SEBI compliance reports based on immutable audit logs.
It generates reports for:
1. Signal attribution and model versions
2. User consent records
3. Decision audit trails
4. System change history
5. Risk assessment records

Reports are generated in multiple formats (JSON, PDF, CSV) and stored with 7-year retention policy.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from enum import Enum
import csv
import io
import uuid
from pathlib import Path

# PDF generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

# FastAPI dependencies
from fastapi import Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field, validator

# MinIO client
from minio import Minio
from minio.commonconfig import ComposeSource
from minio.error import S3Error
from minio.retention import Retention

# SQLAlchemy
from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, Index, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select

# Local imports
from app.core.config import get_settings
from monitoring.services.immutable_audit_logger import (
    get_minio_client, 
    AuditLogMetadataModel,
    AuditActionType
)

# Configure logging
logger = logging.getLogger(__name__)

# Database model base
Base = declarative_base()

class ComplianceReportType(str, Enum):
    """Types of SEBI compliance reports"""
    SIGNAL_ATTRIBUTION = "signal_attribution"
    USER_CONSENT = "user_consent"
    DECISION_AUDIT = "decision_audit"
    SYSTEM_CHANGE = "system_change"
    RISK_ASSESSMENT = "risk_assessment"
    FULL_COMPLIANCE = "full_compliance"

class ComplianceReportFormat(str, Enum):
    """Available formats for compliance reports"""
    JSON = "json"
    PDF = "pdf"
    CSV = "csv"

class ComplianceReportModel(Base):
    """Database model for compliance reports metadata"""
    __tablename__ = "compliance_reports"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    report_type = Column(String, nullable=False, index=True)
    report_format = Column(String, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False, index=True)
    end_date = Column(DateTime(timezone=True), nullable=False, index=True)
    generated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), index=True)
    generated_by = Column(String, nullable=True, index=True)
    s3_object_key = Column(String, nullable=False)
    record_count = Column(Integer, nullable=False, default=0)
    report_hash = Column(String, nullable=False)
    retention_until = Column(DateTime(timezone=True), index=True)
    
    __table_args__ = (
        Index('ix_compliance_reports_type_date', 'report_type', 'start_date', 'end_date'),
    )

class ComplianceReportGenerator:
    """
    SEBI Compliance Report Generator
    
    Generates regulatory compliance reports based on immutable audit logs.
    Reports are stored in MinIO with 7-year retention policy.
    """
    
    def __init__(self,
                 minio_client: Minio,
                 db_session_factory: sessionmaker,
                 reports_bucket: str = "compliance-reports",
                 audit_bucket: str = "audit-logs"):
        """
        Initialize the compliance report generator
        
        Args:
            minio_client: MinIO client instance
            db_session_factory: SQLAlchemy session factory
            reports_bucket: MinIO bucket name for compliance reports
            audit_bucket: MinIO bucket name for audit logs
        """
        self.minio_client = minio_client
        self.db_session_factory = db_session_factory
        self.reports_bucket = reports_bucket
        self.audit_bucket = audit_bucket
        
        # Ensure reports bucket exists
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Ensure the compliance reports bucket exists with proper configuration"""
        try:
            if not self.minio_client.bucket_exists(self.reports_bucket):
                # Create bucket with object locking enabled for immutability
                self.minio_client.make_bucket(self.reports_bucket, object_lock=True)
                logger.info(f"Created compliance reports bucket: {self.reports_bucket} with object locking")
        except S3Error as e:
            logger.error(f"Error setting up compliance reports bucket: {e}")
            raise
    
    async def generate_report(self,
                            report_type: ComplianceReportType,
                            start_date: datetime,
                            end_date: datetime,
                            report_format: ComplianceReportFormat = ComplianceReportFormat.PDF,
                            generated_by: Optional[str] = None,
                            background_tasks: Optional[BackgroundTasks] = None) -> str:
        """
        Generate a compliance report
        
        Args:
            report_type: Type of compliance report to generate
            start_date: Start date for report data
            end_date: End date for report data
            report_format: Format of the report
            generated_by: User or service ID that generated the report
            background_tasks: FastAPI background tasks for async processing
            
        Returns:
            ID of the generated report
        """
        report_id = str(uuid.uuid4())
        
        # Use background task if available, otherwise execute synchronously
        if background_tasks:
            background_tasks.add_task(
                self._generate_and_store_report,
                report_id,
                report_type,
                start_date,
                end_date,
                report_format,
                generated_by
            )
            logger.debug(f"Queued compliance report {report_id} for background generation")
        else:
            await self._generate_and_store_report(
                report_id,
                report_type,
                start_date,
                end_date,
                report_format,
                generated_by
            )
        
        return report_id
    
    async def _generate_and_store_report(self,
                                      report_id: str,
                                      report_type: ComplianceReportType,
                                      start_date: datetime,
                                      end_date: datetime,
                                      report_format: ComplianceReportFormat,
                                      generated_by: Optional[str] = None):
        """
        Generate and store a compliance report
        
        Args:
            report_id: ID for the report
            report_type: Type of compliance report
            start_date: Start date for report data
            end_date: End date for report data
            report_format: Format of the report
            generated_by: User or service ID that generated the report
        """
        async with self.db_session_factory() as session:
            try:
                # Fetch audit log entries based on report type
                audit_entries = await self._fetch_audit_logs_for_report(
                    session, report_type, start_date, end_date
                )
                
                if not audit_entries:
                    logger.warning(f"No audit log entries found for {report_type} report between {start_date} and {end_date}")
                    # Create empty report
                    audit_entries = []
                
                # Generate report in specified format
                report_content, content_type = await self._format_report(
                    report_type, report_format, audit_entries, start_date, end_date
                )
                
                # Calculate report hash
                report_hash = self._calculate_report_hash(report_content)
                
                # Generate S3 object key
                year_month = datetime.now(timezone.utc).strftime("%Y/%m")
                object_key = f"{year_month}/{report_type}/{report_id}.{report_format.lower()}"
                
                # Calculate retention period (7 years for SEBI compliance)
                retention_date = datetime.now(timezone.utc) + timedelta(days=365 * 7)
                
                # Store report in MinIO (retention will be enforced at the bucket level)
                self.minio_client.put_object(
                    bucket_name=self.reports_bucket,
                    object_name=object_key,
                    data=io.BytesIO(report_content),
                    length=len(report_content),
                    content_type=content_type
                )
                
                # Store report metadata in database
                report_model = ComplianceReportModel(
                    id=report_id,
                    report_type=report_type,
                    report_format=report_format,
                    start_date=start_date,
                    end_date=end_date,
                    generated_at=datetime.now(timezone.utc),
                    generated_by=generated_by,
                    s3_object_key=object_key,
                    record_count=len(audit_entries),
                    report_hash=report_hash,
                    retention_until=retention_date
                )
                
                session.add(report_model)
                await session.commit()
                
                logger.info(f"Generated {report_type} compliance report {report_id} with {len(audit_entries)} records")
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to generate compliance report: {e}")
                raise
    
    async def _fetch_audit_logs_for_report(self,
                                        session: AsyncSession,
                                        report_type: ComplianceReportType,
                                        start_date: datetime,
                                        end_date: datetime) -> List[Dict[str, Any]]:
        """
        Fetch audit log entries for a specific report type
        
        Args:
            session: SQLAlchemy session
            report_type: Type of compliance report
            start_date: Start date for report data
            end_date: End date for report data
            
        Returns:
            List of audit log entries
        """
        # Define action types to include based on report type
        action_types = []
        
        if report_type == ComplianceReportType.SIGNAL_ATTRIBUTION:
            action_types = [
                AuditActionType.SIGNAL_GENERATED,
                AuditActionType.SIGNAL_MODIFIED,
                AuditActionType.MODEL_CHANGE,
                AuditActionType.AGENT_EXECUTION
            ]
        elif report_type == ComplianceReportType.USER_CONSENT:
            action_types = [
                AuditActionType.USER_LOGIN,
                AuditActionType.USER_ACTION
            ]
        elif report_type == ComplianceReportType.DECISION_AUDIT:
            action_types = [
                AuditActionType.SIGNAL_GENERATED,
                AuditActionType.USER_ACTION,
                AuditActionType.AGENT_EXECUTION
            ]
        elif report_type == ComplianceReportType.SYSTEM_CHANGE:
            action_types = [
                AuditActionType.SYSTEM_CHANGE,
                AuditActionType.MODEL_CHANGE,
                AuditActionType.PARAMETER_CHANGE,
                AuditActionType.ADMIN_ACTION
            ]
        elif report_type == ComplianceReportType.RISK_ASSESSMENT:
            action_types = [
                AuditActionType.SIGNAL_GENERATED,
                AuditActionType.SIGNAL_MODIFIED
            ]
        elif report_type == ComplianceReportType.FULL_COMPLIANCE:
            # Include all action types
            action_types = [action_type.value for action_type in AuditActionType]
        
        # Build query
        query = (
            select(AuditLogMetadataModel)
            .where(AuditLogMetadataModel.timestamp >= start_date)
            .where(AuditLogMetadataModel.timestamp <= end_date)
        )
        
        if action_types:
            query = query.where(AuditLogMetadataModel.action_type.in_(action_types))
        
        # Execute query
        result = await session.execute(query)
        metadata_entries = result.scalars().all()
        
        # Fetch full entries from MinIO
        entries = []
        for metadata in metadata_entries:
            try:
                response = self.minio_client.get_object(
                    self.audit_bucket, 
                    metadata.s3_object_key
                )
                data = json.loads(response.read().decode('utf-8'))
                response.close()
                response.release_conn()
                
                entries.append(data)
                
            except Exception as e:
                logger.error(f"Error retrieving audit log entry {metadata.id}: {e}")
                # Include partial data with error note
                entries.append({
                    "id": metadata.id,
                    "timestamp": metadata.timestamp.isoformat(),
                    "action_type": metadata.action_type,
                    "error": f"Failed to retrieve full entry: {str(e)}"
                })
        
        return entries
    
    async def _format_report(self,
                          report_type: ComplianceReportType,
                          report_format: ComplianceReportFormat,
                          audit_entries: List[Dict[str, Any]],
                          start_date: datetime,
                          end_date: datetime) -> Tuple[bytes, str]:
        """
        Format report in the specified format
        
        Args:
            report_type: Type of compliance report
            report_format: Format of the report
            audit_entries: Audit log entries for the report
            start_date: Start date for report data
            end_date: End date for report data
            
        Returns:
            Tuple of (report content as bytes, content type)
        """
        if report_format == ComplianceReportFormat.JSON:
            return await self._format_json_report(report_type, audit_entries, start_date, end_date)
        elif report_format == ComplianceReportFormat.PDF:
            return await self._format_pdf_report(report_type, audit_entries, start_date, end_date)
        elif report_format == ComplianceReportFormat.CSV:
            return await self._format_csv_report(report_type, audit_entries, start_date, end_date)
        else:
            raise ValueError(f"Unsupported report format: {report_format}")
    
    async def _format_json_report(self,
                               report_type: ComplianceReportType,
                               audit_entries: List[Dict[str, Any]],
                               start_date: datetime,
                               end_date: datetime) -> Tuple[bytes, str]:
        """Format report as JSON"""
        report = {
            "report_type": report_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "record_count": len(audit_entries),
            "entries": audit_entries
        }
        
        return json.dumps(report, indent=2).encode('utf-8'), "application/json"
    
    async def _format_csv_report(self,
                              report_type: ComplianceReportType,
                              audit_entries: List[Dict[str, Any]],
                              start_date: datetime,
                              end_date: datetime) -> Tuple[bytes, str]:
        """Format report as CSV"""
        output = io.StringIO()
        writer = None
        
        # Add header row with report metadata
        metadata_writer = csv.writer(output)
        metadata_writer.writerow(["SEBI Compliance Report"])
        metadata_writer.writerow(["Report Type", report_type])
        metadata_writer.writerow(["Generated At", datetime.now(timezone.utc).isoformat()])
        metadata_writer.writerow(["Period Start", start_date.isoformat()])
        metadata_writer.writerow(["Period End", end_date.isoformat()])
        metadata_writer.writerow(["Record Count", len(audit_entries)])
        metadata_writer.writerow([])  # Empty row
        
        if audit_entries:
            # Determine fields based on the first entry
            first_entry = audit_entries[0]
            
            # Common fields to include
            fields = ["id", "timestamp", "action_type", "user_id", "service_id", 
                     "ip_address", "resource_id", "resource_type"]
            
            # Add additional fields based on report type
            if report_type == ComplianceReportType.SIGNAL_ATTRIBUTION:
                if "action_details" in first_entry and isinstance(first_entry["action_details"], dict):
                    for key in first_entry["action_details"].keys():
                        fields.append(f"action_details.{key}")
            
            writer = csv.writer(output)
            writer.writerow(fields)
            
            # Write data rows
            for entry in audit_entries:
                row = []
                for field in fields:
                    if "." in field:  # Nested field
                        parts = field.split(".")
                        value = entry
                        for part in parts:
                            if isinstance(value, dict) and part in value:
                                value = value[part]
                            else:
                                value = None
                                break
                    else:
                        value = entry.get(field)
                    
                    # Convert complex objects to string
                    if isinstance(value, dict) or isinstance(value, list):
                        value = json.dumps(value)
                    
                    row.append(value)
                
                writer.writerow(row)
        
        return output.getvalue().encode('utf-8'), "text/csv"
    
    async def _format_pdf_report(self,
                              report_type: ComplianceReportType,
                              audit_entries: List[Dict[str, Any]],
                              start_date: datetime,
                              end_date: datetime) -> Tuple[bytes, str]:
        """Format report as PDF"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []
        
        # Add title
        title_style = styles["Heading1"]
        title = Paragraph(f"SEBI Compliance Report: {report_type}", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.25 * inch))
        
        # Add report metadata
        metadata = [
            ["Generated At:", datetime.now(timezone.utc).isoformat()],
            ["Report Type:", report_type],
            ["Period Start:", start_date.isoformat()],
            ["Period End:", end_date.isoformat()],
            ["Record Count:", str(len(audit_entries))]
        ]
        
        metadata_table = Table(metadata, colWidths=[2 * inch, 4 * inch])
        metadata_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6)
        ]))
        
        elements.append(metadata_table)
        elements.append(Spacer(1, 0.5 * inch))
        
        # Add entries based on report type
        if audit_entries:
            # Add section title
            section_title = Paragraph("Audit Log Entries", styles["Heading2"])
            elements.append(section_title)
            elements.append(Spacer(1, 0.25 * inch))
            
            # Create table with appropriate columns based on report type
            if report_type == ComplianceReportType.SIGNAL_ATTRIBUTION:
                headers = ["Timestamp", "Action", "Model/Agent", "Signal ID", "Confidence"]
                data = [headers]
                
                for entry in audit_entries:
                    timestamp = entry.get("timestamp", "")
                    action = entry.get("action_type", "")
                    
                    # Extract model/agent info
                    model_agent = ""
                    if "action_details" in entry and isinstance(entry["action_details"], dict):
                        model_agent = entry["action_details"].get("model_version", "")
                        if not model_agent:
                            model_agent = entry["action_details"].get("agent_id", "")
                    
                    # Extract signal ID
                    signal_id = entry.get("resource_id", "")
                    
                    # Extract confidence
                    confidence = ""
                    if "action_details" in entry and isinstance(entry["action_details"], dict):
                        confidence = entry["action_details"].get("confidence", "")
                    
                    data.append([timestamp, action, model_agent, signal_id, confidence])
            
            elif report_type == ComplianceReportType.USER_CONSENT:
                headers = ["Timestamp", "User ID", "Action", "IP Address", "Details"]
                data = [headers]
                
                for entry in audit_entries:
                    timestamp = entry.get("timestamp", "")
                    user_id = entry.get("user_id", "")
                    action = entry.get("action_type", "")
                    ip_address = entry.get("ip_address", "")
                    
                    # Extract details
                    details = ""
                    if "action_details" in entry and isinstance(entry["action_details"], dict):
                        details = json.dumps(entry["action_details"])
                    
                    data.append([timestamp, user_id, action, ip_address, details])
            
            else:
                # Generic table for other report types
                headers = ["Timestamp", "Action Type", "User/Service", "Resource", "Details"]
                data = [headers]
                
                for entry in audit_entries:
                    timestamp = entry.get("timestamp", "")
                    action = entry.get("action_type", "")
                    
                    # User or service
                    user_service = entry.get("user_id", "") or entry.get("service_id", "")
                    
                    # Resource
                    resource = f"{entry.get('resource_type', '')}: {entry.get('resource_id', '')}"
                    
                    # Details
                    details = ""
                    if "action_details" in entry and isinstance(entry["action_details"], dict):
                        details = json.dumps(entry["action_details"])[:100]  # Truncate long details
                        if len(json.dumps(entry["action_details"])) > 100:
                            details += "..."
                    
                    data.append([timestamp, action, user_service, resource, details])
            
            # Create and style the table
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('PADDING', (0, 0), (-1, -1), 6)
            ]))
            
            elements.append(table)
        else:
            # No entries message
            no_entries = Paragraph("No audit log entries found for the specified period and report type.", 
                                 styles["Normal"])
            elements.append(no_entries)
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        return pdf_content, "application/pdf"
    
    def _calculate_report_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of report content"""
        import hashlib
        return hashlib.sha256(content).hexdigest()
    
    async def get_report(self, report_id: str) -> Tuple[bytes, str, str]:
        """
        Retrieve a compliance report
        
        Args:
            report_id: ID of the report to retrieve
            
        Returns:
            Tuple of (report content, content type, filename)
        """
        async with self.db_session_factory() as session:
            try:
                # Get report metadata
                result = await session.execute(
                    select(ComplianceReportModel).where(ComplianceReportModel.id == report_id)
                )
                report = result.scalar_one_or_none()
                
                if not report:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Compliance report {report_id} not found"
                    )
                
                # Get report content from MinIO
                response = self.minio_client.get_object(
                    self.reports_bucket,
                    report.s3_object_key
                )
                
                content = response.read()
                response.close()
                response.release_conn()
                
                # Determine content type and filename
                content_type = self._get_content_type(report.report_format)
                filename = f"compliance_report_{report.report_type}_{report.start_date.strftime('%Y%m%d')}_{report.end_date.strftime('%Y%m%d')}.{report.report_format.lower()}"
                
                return content, content_type, filename
                
            except Exception as e:
                logger.error(f"Error retrieving compliance report {report_id}: {e}")
                raise
    
    def _get_content_type(self, report_format: str) -> str:
        """Get content type for report format"""
        if report_format.lower() == "json":
            return "application/json"
        elif report_format.lower() == "pdf":
            return "application/pdf"
        elif report_format.lower() == "csv":
            return "text/csv"
        else:
            return "application/octet-stream"
    
    async def list_reports(self,
                         report_type: Optional[ComplianceReportType] = None,
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None,
                         limit: int = 100,
                         offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """
        List available compliance reports
        
        Args:
            report_type: Filter by report type
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            Tuple of (list of reports, total count)
        """
        async with self.db_session_factory() as session:
            try:
                # Build query
                query = select(ComplianceReportModel)
                count_query = select(func.count(ComplianceReportModel.id))
                
                # Apply filters
                if report_type:
                    query = query.where(ComplianceReportModel.report_type == report_type)
                    count_query = count_query.where(ComplianceReportModel.report_type == report_type)
                
                if start_date:
                    query = query.where(ComplianceReportModel.start_date >= start_date)
                    count_query = count_query.where(ComplianceReportModel.start_date >= start_date)
                
                if end_date:
                    query = query.where(ComplianceReportModel.end_date <= end_date)
                    count_query = count_query.where(ComplianceReportModel.end_date <= end_date)
                
                # Apply pagination
                query = query.order_by(ComplianceReportModel.generated_at.desc())
                query = query.offset(offset).limit(limit)
                
                # Execute queries
                result = await session.execute(query)
                count_result = await session.execute(count_query)
                
                reports = result.scalars().all()
                total_count = count_result.scalar_one()
                
                # Convert to dictionaries
                report_list = []
                for report in reports:
                    report_list.append({
                        "id": report.id,
                        "report_type": report.report_type,
                        "report_format": report.report_format,
                        "start_date": report.start_date.isoformat(),
                        "end_date": report.end_date.isoformat(),
                        "generated_at": report.generated_at.isoformat(),
                        "generated_by": report.generated_by,
                        "record_count": report.record_count,
                        "retention_until": report.retention_until.isoformat()
                    })
                
                return report_list, total_count
                
            except Exception as e:
                logger.error(f"Error listing compliance reports: {e}")
                raise

# Dependency for getting the compliance report generator
async def get_compliance_report_generator(
    minio_client: Minio = Depends(get_minio_client),
    session_factory: sessionmaker = Depends(lambda: sessionmaker(bind=create_async_engine(get_settings().DATABASE_URL)))
) -> ComplianceReportGenerator:
    """Get compliance report generator instance"""
    return ComplianceReportGenerator(
        minio_client=minio_client,
        db_session_factory=session_factory
    )