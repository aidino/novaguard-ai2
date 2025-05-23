# novaguard-backend/app/analysis_worker/llm_schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union # Đảm bảo Union được import nếu bạn dùng nó ở đâu đó
import enum

import logging
logger = logging.getLogger(__name__)

class SeverityLevel(str, enum.Enum): # Kế thừa từ str và enum.Enum
    ERROR = "Error"
    WARNING = "Warning"
    NOTE = "Note"
    INFO = "Info"
    
class LLMSingleFinding(BaseModel):
    """
    Represents a single issue/finding identified by the LLM, typically file-specific.
    
    CRITICAL: All fields marked with ... are REQUIRED and must be provided by the LLM.
    """
    file_path: Optional[str] = Field(
        None, 
        description="REQUIRED: The exact file path from the changed files provided. Must match paths exactly as shown in the 'Changed Files' section. Use None only for project-level findings.",
        examples=["app/models/user.py", "src/components/Login.tsx", "backend/api/auth.py"]
    )
    line_start: Optional[int] = Field(
        None, 
        description="REQUIRED for code-specific findings: The starting line number (1-based index) where the issue begins. Must be a positive integer.",
        ge=1
    )
    line_end: Optional[int] = Field(
        None, 
        description="REQUIRED for code-specific findings: The ending line number (1-based index) where the issue ends. Must be >= line_start.",
        ge=1
    )
    severity: SeverityLevel = Field(
        ..., 
        description="REQUIRED: Severity level. Must be one of: 'Error' (critical issues causing crashes/security), 'Warning' (potential problems), 'Note' (suggestions), 'Info' (informational)."
    )
    message: str = Field(
        ..., 
        description="REQUIRED: Clear, specific description of the issue found. Must reference actual code elements and explain the technical risk.",
        min_length=10,
        examples=["Function 'get_user()' can return None but is accessed without null check on line 45, causing potential runtime exception."]
    )
    suggestion: Optional[str] = Field(
        None, 
        description="RECOMMENDED: Specific, actionable suggestion to fix the issue. Should include code snippets or specific steps.",
        examples=["Add null check: 'if not user: raise ValueError(\"User not found\")' before accessing user properties."]
    )
    finding_type: Optional[str] = Field(
        "code_smell", 
        description="Type of finding. Must be one of: 'logic_error', 'security_vulnerability', 'performance_bottleneck', 'concurrency_issue', 'business_logic_flaw', 'code_smell'."
    )
    meta_data: Optional[dict] = Field(
        None, 
        description="Additional structured context about the finding. Use for technical details, impact assessment, or categorization.",
        examples=[{"function_name": "process_payment", "vulnerability_type": "null_pointer", "impact": "system_crash"}]
    )
    agent_name: Optional[str] = Field(None, description="Name of the agent that generated this finding.") # <--- THÊM DÒNG NÀY

    @field_validator('line_end')
    @classmethod
    def validate_line_end(cls, v, info):
        if v is not None and info.data.get('line_start') is not None:
            if v < info.data['line_start']:
                raise ValueError('line_end must be >= line_start')
        return v

    @field_validator('severity', mode='before')
    @classmethod
    def _validate_severity(cls, value: str) -> SeverityLevel:
        try:
            return SeverityLevel(value.capitalize() if isinstance(value, str) else value)
        except ValueError:
            logger.warning(f"Invalid severity value '{value}' from LLM. Defaulting to Note.")
            return SeverityLevel.NOTE

    @field_validator('finding_type')
    @classmethod
    def validate_finding_type(cls, v):
        valid_types = ['logic_error', 'security_vulnerability', 'performance_bottleneck', 
                      'concurrency_issue', 'business_logic_flaw', 'code_smell']
        if v and v not in valid_types:
            logger.warning(f"Invalid finding_type '{v}'. Using 'code_smell'.")
            return 'code_smell'
        return v

class LLMProjectLevelFinding(BaseModel):
    """
    Represents a single issue/finding identified at the project or module level.
    
    CRITICAL: All fields marked with ... are REQUIRED and must be provided by the LLM.
    """
    finding_category: str = Field(
        ..., 
        description="REQUIRED: Category of the project-level finding. Must be one of: 'Architectural Concern', 'Technical Debt', 'Security Hotspot', 'Module Design', 'Code Quality', 'Performance Issue'.",
        min_length=3
    )
    description: str = Field(
        ..., 
        description="REQUIRED: Detailed description of the project-level issue. Must reference actual data from CKG summary with specific metrics and real entity names.",
        min_length=20
    )
    severity: SeverityLevel = Field(
        ..., 
        description="REQUIRED: Severity level based on actual impact assessment. 'Error' for critical architectural flaws, 'Warning' for significant concerns."
    )
    implication: Optional[str] = Field(
        None, 
        description="RECOMMENDED: Specific potential impact on maintainability, scalability, security, or performance. Based on actual project characteristics."
    )
    recommendation: Optional[str] = Field(
        None, 
        description="RECOMMENDED: High-level, actionable recommendation with specific steps to address the issue."
    )
    relevant_components: Optional[List[str]] = Field(
        None, 
        description="RECOMMENDED: List of actual file paths, class names, or module names from the CKG data that are related to this finding."
    )
    meta_data: Optional[dict] = Field(
        None, 
        description="Additional structured data with actual metrics, entity names, and technical details from the real project analysis."
    )

    @field_validator('finding_category')
    @classmethod
    def validate_finding_category(cls, v):
        valid_categories = ['Architectural Concern', 'Technical Debt', 'Security Hotspot', 
                           'Module Design', 'Code Quality', 'Performance Issue']
        if v not in valid_categories:
            logger.warning(f"Invalid finding_category '{v}'. Using 'Architectural Concern'.")
            return 'Architectural Concern'
        return v

    @field_validator('severity', mode='before')
    @classmethod
    def _validate_severity(cls, value: str) -> SeverityLevel:
        try:
            return SeverityLevel(value.capitalize() if isinstance(value, str) else value)
        except ValueError:
            logger.warning(f"Invalid severity value '{value}' from LLM. Defaulting to Note.")
            return SeverityLevel.NOTE

class LLMStructuredOutput(BaseModel):
    """
    The overall JSON structure expected from the LLM for PR analysis or file-specific analysis.
    
    FORMAT REQUIREMENT: Must return a JSON object with exactly this structure.
    """
    findings: List[LLMSingleFinding] = Field(
        ..., 
        description="REQUIRED: Array of all distinct issues identified. Use empty array [] if no issues found. Each finding must be a complete LLMSingleFinding object."
    )

class LLMProjectAnalysisOutput(BaseModel):
    """
    The overall JSON structure expected from the LLM for full project analysis.
    May contain a mix of project-level and more granular findings.
    
    FORMAT REQUIREMENT: Must return a JSON object with exactly these three keys.
    """
    project_summary: Optional[str] = Field(
        None, 
        description="RECOMMENDED: Brief overall assessment based on actual CKG metrics. Reference specific numbers like file count, class count, complexity metrics."
    )
    project_level_findings: List[LLMProjectLevelFinding] = Field(
        default_factory=list, 
        description="REQUIRED: Array of architectural/project-level issues based on actual CKG analysis. Use empty array [] if no significant issues found."
    )
    granular_findings: List[LLMSingleFinding] = Field(
        default_factory=list, 
        description="OPTIONAL: Array of specific code-level findings if identified during project analysis. Typically empty for project-level analysis."
    )

    @field_validator('project_summary', mode='before')
    @classmethod
    def _validate_project_summary(cls, value):
        """Ensure project_summary is a string, not a dict"""
        if isinstance(value, dict):
            logger.warning(f"LLM returned dict for project_summary, converting to string.")
            # Try to extract meaningful string from dict
            if 'summary' in value:
                return str(value['summary'])
            elif 'description' in value:
                return str(value['description'])
            else:
                # Convert dict to readable string
                return f"Project contains {value.get('total_files', 'unknown')} files and {value.get('total_classes', 'unknown')} classes."
        return value