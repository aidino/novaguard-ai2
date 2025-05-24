# novaguard-backend/app/analysis_module/schemas_finding.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any # Đảm bảo List đã được import
from datetime import datetime

# Import các schema cần thiết từ các module khác
from app.webhook_service.schemas_pr_analysis import PRAnalysisRequestPublic 
from app.analysis_worker.llm_schemas import SeverityLevel

class AnalysisFindingBase(BaseModel):
    file_path: str = Field(..., max_length=1024)
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    severity: SeverityLevel
    message: str
    suggestion: Optional[str] = None
    agent_name: Optional[str] = Field(None, max_length=100)
    code_snippet: Optional[str] = None
    
    # Extended fields for enhanced analysis
    finding_type: Optional[str] = Field(None, max_length=100)
    finding_level: Optional[str] = Field("file", max_length=20) 
    module_name: Optional[str] = Field(None, max_length=255)
    meta_data: Optional[Dict[str, Any]] = None
    
    # Field for graceful degradation when LLM output cannot be parsed
    raw_llm_content: Optional[str] = Field(None, description="Raw LLM output when JSON parsing fails, for manual review")

class AnalysisFindingCreate(AnalysisFindingBase):
    pass

class AnalysisFindingPublic(AnalysisFindingBase):
    id: int
    pr_analysis_request_id: Optional[int] = None  # Made optional for full project scans
    full_project_analysis_request_id: Optional[int] = None  # Added for full project scans
    scan_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
        use_enum_values = True


class PRAnalysisReportDetail(BaseModel):
    pr_request_details: PRAnalysisRequestPublic  # Chi tiết của PRAnalysisRequest
    findings: List[AnalysisFindingPublic]       # Danh sách các phát hiện

    class Config:
        from_attributes = True
