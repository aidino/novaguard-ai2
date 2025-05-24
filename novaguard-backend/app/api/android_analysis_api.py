from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, status
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import asyncio
import logging
from datetime import datetime

from app.analysis_module import (
    EnhancedAnalysisEngine,
    AnalysisRequest,
    AnalysisResult
)

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1/android", tags=["Android Analysis"])

# Initialize analysis engine
analysis_engine = EnhancedAnalysisEngine(max_workers=4)

# Pydantic models for API
class ProjectFileModel(BaseModel):
    """Model for project file data."""
    file_path: str = Field(..., description="Relative path of the file")
    content: str = Field(..., description="File content")

class AnalysisRequestModel(BaseModel):
    """Model for analysis request."""
    project_id: int = Field(..., description="Project ID")
    project_name: str = Field(..., description="Project name")
    files: List[ProjectFileModel] = Field(..., description="Project files to analyze")
    analysis_types: List[str] = Field(
        default=["architecture", "security", "performance"],
        description="Types of analysis to perform"
    )
    priority: str = Field(default="normal", description="Analysis priority")

class AnalysisStatusModel(BaseModel):
    """Model for analysis status."""
    analysis_id: str
    status: str  # pending, running, completed, failed
    progress: float  # 0.0 to 1.0
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

class FindingModel(BaseModel):
    """Model for analysis finding."""
    type: str
    severity: str
    title: str
    description: str
    recommendation: str
    category: str
    analysis_prompt: str

class RecommendationModel(BaseModel):
    """Model for analysis recommendation."""
    priority: str
    title: str
    description: str
    action_items: List[str]

class AnalysisResultModel(BaseModel):
    """Model for analysis result."""
    project_id: int
    project_name: str
    analysis_type: str
    execution_time: float
    health_score: int
    findings: List[FindingModel]
    recommendations: List[RecommendationModel]
    metrics: Dict[str, Any]
    context_summary: Dict[str, Any]

class AnalysisSummaryModel(BaseModel):
    """Model for analysis summary."""
    project_name: str
    analysis_type: str
    execution_time: float
    health_score: int
    total_findings: int
    critical_issues: int
    recommendations_count: int
    kotlin_percentage: float
    components_count: int
    dependencies_count: int

# In-memory storage for analysis results (in production, use database)
analysis_results: Dict[str, AnalysisResult] = {}
analysis_status: Dict[str, AnalysisStatusModel] = {}

@router.post("/analyze", response_model=Dict[str, str])
async def start_analysis(
    request: AnalysisRequestModel,
    background_tasks: BackgroundTasks
) -> Dict[str, str]:
    """
    Start a comprehensive Android project analysis.
    
    Args:
        request: Analysis request with project details
        background_tasks: FastAPI background tasks
        
    Returns:
        Analysis ID for tracking progress
    """
    # Validate analysis types first (before try block)
    valid_types = ["architecture", "security", "performance", "code_review", "lifecycle"]
    invalid_types = [t for t in request.analysis_types if t not in valid_types]
    if invalid_types:
        logger.error(f"Invalid analysis types: {invalid_types}. Valid types: {valid_types}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid analysis types: {invalid_types}. Valid types: {valid_types}"
        )
    
    try:
        # Generate analysis ID
        analysis_id = f"analysis_{request.project_id}_{int(datetime.now().timestamp())}"
        
        # Create analysis status
        analysis_status[analysis_id] = AnalysisStatusModel(
            analysis_id=analysis_id,
            status="pending",
            progress=0.0,
            started_at=datetime.now(),
            completed_at=None,
            error_message=None
        )
        
        # Convert request to internal format
        project_files = {file.file_path: file.content for file in request.files}
        
        internal_request = AnalysisRequest(
            project_id=request.project_id,
            project_name=request.project_name,
            project_files=project_files,
            analysis_types=request.analysis_types,
            priority=request.priority
        )
        
        # Start analysis in background
        background_tasks.add_task(
            perform_analysis_task,
            analysis_id,
            internal_request
        )
        
        logger.info(f"Started analysis {analysis_id} for project {request.project_name}")
        
        return {
            "analysis_id": analysis_id,
            "status": "pending",
            "message": f"Analysis started for project {request.project_name}"
        }
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error starting analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start analysis: {str(e)}"
        )

async def perform_analysis_task(analysis_id: str, request: AnalysisRequest):
    """Background task to perform the actual analysis."""
    try:
        # Update status to running
        analysis_status[analysis_id].status = "running"
        analysis_status[analysis_id].progress = 0.1
        
        logger.info(f"Starting analysis task {analysis_id}")
        
        # Perform analysis
        result = await analysis_engine.analyze_project(request)
        
        # Store result
        analysis_results[analysis_id] = result
        
        # Update status to completed
        analysis_status[analysis_id].status = "completed"
        analysis_status[analysis_id].progress = 1.0
        analysis_status[analysis_id].completed_at = datetime.now()
        
        logger.info(f"Completed analysis task {analysis_id}")
        
    except Exception as e:
        logger.error(f"Error in analysis task {analysis_id}: {e}")
        
        # Update status to failed
        analysis_status[analysis_id].status = "failed"
        analysis_status[analysis_id].error_message = str(e)

@router.get("/analysis/{analysis_id}/status", response_model=AnalysisStatusModel)
async def get_analysis_status(analysis_id: str) -> AnalysisStatusModel:
    """
    Get the status of an analysis.
    
    Args:
        analysis_id: Analysis ID
        
    Returns:
        Analysis status information
    """
    if analysis_id not in analysis_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found"
        )
    
    return analysis_status[analysis_id]

@router.get("/analysis/{analysis_id}/result", response_model=AnalysisResultModel)
async def get_analysis_result(analysis_id: str) -> AnalysisResultModel:
    """
    Get the result of a completed analysis.
    
    Args:
        analysis_id: Analysis ID
        
    Returns:
        Complete analysis result
    """
    if analysis_id not in analysis_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found"
        )
    
    status_info = analysis_status[analysis_id]
    
    if status_info.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Analysis {analysis_id} is not completed. Status: {status_info.status}"
        )
    
    if analysis_id not in analysis_results:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis result for {analysis_id} not found"
        )
    
    result = analysis_results[analysis_id]
    
    # Convert to API model
    return AnalysisResultModel(
        project_id=result.project_id,
        project_name=result.project_name,
        analysis_type=result.analysis_type,
        execution_time=result.execution_time,
        health_score=result.metrics.get("health_score", 0),
        findings=[
            FindingModel(
                type=f.get("type", "unknown"),
                severity=f.get("severity", "unknown"),
                title=f.get("title", "No title"),
                description=f.get("description", "No description"),
                recommendation=f.get("recommendation", "No recommendation"),
                category=f.get("category", "unknown"),
                analysis_prompt=f.get("analysis_prompt", "unknown")
            ) for f in result.findings
        ],
        recommendations=[
            RecommendationModel(
                priority=r.get("priority", "unknown"),
                title=r.get("title", "No title"),
                description=r.get("description", "No description"),
                action_items=r.get("action_items", [])
            ) for r in result.recommendations
        ],
        metrics=result.metrics,
        context_summary={
            "package_name": result.context.package_name,
            "target_sdk": result.context.target_sdk,
            "kotlin_percentage": result.context.kotlin_percentage,
            "components_count": len(result.context.components),
            "dependencies_count": len(result.context.dependencies),
            "architecture_patterns": result.context.architecture_patterns,
            "jetpack_components": result.context.jetpack_components
        }
    )

@router.get("/analysis/{analysis_id}/summary", response_model=AnalysisSummaryModel)
async def get_analysis_summary(analysis_id: str) -> AnalysisSummaryModel:
    """
    Get a summary of the analysis result.
    
    Args:
        analysis_id: Analysis ID
        
    Returns:
        Analysis summary
    """
    if analysis_id not in analysis_results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result for {analysis_id} not found"
        )
    
    result = analysis_results[analysis_id]
    summary = analysis_engine.get_analysis_summary(result)
    
    return AnalysisSummaryModel(**summary)

@router.get("/analysis/{analysis_id}/findings", response_model=List[FindingModel])
async def get_analysis_findings(
    analysis_id: str,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    limit: Optional[int] = None
) -> List[FindingModel]:
    """
    Get findings from an analysis with optional filtering.
    
    Args:
        analysis_id: Analysis ID
        severity: Filter by severity (critical, high, medium, low)
        category: Filter by category (architecture, security, performance, etc.)
        limit: Maximum number of findings to return
        
    Returns:
        List of findings
    """
    if analysis_id not in analysis_results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result for {analysis_id} not found"
        )
    
    result = analysis_results[analysis_id]
    findings = result.findings
    
    # Apply filters
    if severity:
        findings = [f for f in findings if f.get("severity") == severity]
    
    if category:
        findings = [f for f in findings if f.get("category") == category]
    
    # Apply limit
    if limit:
        findings = findings[:limit]
    
    return [
        FindingModel(
            type=f.get("type", "unknown"),
            severity=f.get("severity", "unknown"),
            title=f.get("title", "No title"),
            description=f.get("description", "No description"),
            recommendation=f.get("recommendation", "No recommendation"),
            category=f.get("category", "unknown"),
            analysis_prompt=f.get("analysis_prompt", "unknown")
        ) for f in findings
    ]

@router.get("/analysis/{analysis_id}/recommendations", response_model=List[RecommendationModel])
async def get_analysis_recommendations(analysis_id: str) -> List[RecommendationModel]:
    """
    Get recommendations from an analysis.
    
    Args:
        analysis_id: Analysis ID
        
    Returns:
        List of recommendations
    """
    if analysis_id not in analysis_results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result for {analysis_id} not found"
        )
    
    result = analysis_results[analysis_id]
    
    return [
        RecommendationModel(
            priority=r.get("priority", "unknown"),
            title=r.get("title", "No title"),
            description=r.get("description", "No description"),
            action_items=r.get("action_items", [])
        ) for r in result.recommendations
    ]

@router.get("/analysis/{analysis_id}/metrics", response_model=Dict[str, Any])
async def get_analysis_metrics(analysis_id: str) -> Dict[str, Any]:
    """
    Get detailed metrics from an analysis.
    
    Args:
        analysis_id: Analysis ID
        
    Returns:
        Analysis metrics
    """
    if analysis_id not in analysis_results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result for {analysis_id} not found"
        )
    
    result = analysis_results[analysis_id]
    return result.metrics

@router.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str) -> Dict[str, str]:
    """
    Delete an analysis and its results.
    
    Args:
        analysis_id: Analysis ID
        
    Returns:
        Deletion confirmation
    """
    deleted_items = []
    
    if analysis_id in analysis_status:
        del analysis_status[analysis_id]
        deleted_items.append("status")
    
    if analysis_id in analysis_results:
        del analysis_results[analysis_id]
        deleted_items.append("result")
    
    if not deleted_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found"
        )
    
    return {
        "message": f"Analysis {analysis_id} deleted",
        "deleted_items": ", ".join(deleted_items)  # Convert list to comma-separated string
    }

@router.get("/analyses", response_model=List[AnalysisStatusModel])
async def list_analyses(
    status_filter: Optional[str] = None,
    limit: Optional[int] = 50
) -> List[AnalysisStatusModel]:
    """
    List all analyses with optional filtering.
    
    Args:
        status_filter: Filter by status (pending, running, completed, failed)
        limit: Maximum number of analyses to return
        
    Returns:
        List of analysis status information
    """
    analyses = list(analysis_status.values())
    
    # Apply status filter
    if status_filter:
        analyses = [a for a in analyses if a.status == status_filter]
    
    # Sort by started_at (newest first)
    analyses.sort(key=lambda x: x.started_at or datetime.min, reverse=True)
    
    # Apply limit
    if limit:
        analyses = analyses[:limit]
    
    return analyses

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for the Android analysis service.
    
    Returns:
        Service health information
    """
    return {
        "status": "healthy",
        "service": "Android Analysis API",
        "version": "1.0.0",
        "analysis_engine": {
            "max_workers": analysis_engine.max_workers,
            "available_templates": len(analysis_engine.prompt_engine.get_available_templates())
        },
        "active_analyses": {
            "total": len(analysis_status),
            "pending": len([a for a in analysis_status.values() if a.status == "pending"]),
            "running": len([a for a in analysis_status.values() if a.status == "running"]),
            "completed": len([a for a in analysis_status.values() if a.status == "completed"]),
            "failed": len([a for a in analysis_status.values() if a.status == "failed"])
        },
        "timestamp": datetime.now().isoformat()
    } 