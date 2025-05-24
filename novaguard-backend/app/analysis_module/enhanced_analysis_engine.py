# novaguard-backend/app/analysis_module/enhanced_analysis_engine.py
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from .android_context_builder import AndroidContextBuilder, AndroidAnalysisContext
from .prompt_template_engine import PromptTemplateEngine

logger = logging.getLogger(__name__)

@dataclass
class AnalysisResult:
    """Represents the result of an enhanced analysis."""
    project_id: int
    project_name: str
    analysis_type: str
    context: AndroidAnalysisContext
    rendered_prompts: Dict[str, str]
    findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    execution_time: float

@dataclass
class AnalysisRequest:
    """Represents a request for enhanced analysis."""
    project_id: int
    project_name: str
    project_files: Dict[str, str]
    analysis_types: List[str]  # architecture, security, performance, code_review, lifecycle
    priority: str = "normal"  # low, normal, high, critical

class EnhancedAnalysisEngine:
    """
    Enhanced analysis engine that integrates all Android analysis components.
    Provides comprehensive project analysis with context-aware LLM prompts.
    """
    
    def __init__(self, max_workers: int = 4):
        self.context_builder = AndroidContextBuilder()
        self.prompt_engine = PromptTemplateEngine()
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Analysis type mappings
        self.analysis_type_templates = {
            "architecture": ["android_architecture_analyst"],
            "security": ["android_security_analyst"],
            "performance": ["android_performance_analyst"],
            "code_review": ["kotlin_code_reviewer", "java_code_reviewer"],
            "lifecycle": ["android_lifecycle_analyst"]
        }
        
        logger.info(f"Enhanced Analysis Engine initialized with {max_workers} workers")
    
    async def analyze_project(self, request: AnalysisRequest) -> AnalysisResult:
        """
        Perform comprehensive analysis of an Android project.
        
        Args:
            request: Analysis request with project details
            
        Returns:
            Complete analysis result with context, prompts, and findings
        """
        start_time = asyncio.get_event_loop().time()
        
        logger.info(f"Starting enhanced analysis for project: {request.project_name}")
        logger.info(f"Analysis types: {request.analysis_types}")
        logger.info(f"Files to analyze: {len(request.project_files)}")
        
        try:
            # Step 1: Build comprehensive Android context
            context = await self._build_project_context(request)
            
            # Step 2: Generate context-aware prompts
            rendered_prompts = await self._generate_analysis_prompts(context, request.analysis_types)
            
            # Step 3: Perform analysis (placeholder for LLM integration)
            findings = await self._perform_analysis(context, rendered_prompts, request)
            
            # Step 4: Generate recommendations
            recommendations = await self._generate_recommendations(context, findings)
            
            # Step 5: Calculate metrics
            metrics = await self._calculate_analysis_metrics(context, findings)
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            result = AnalysisResult(
                project_id=request.project_id,
                project_name=request.project_name,
                analysis_type=", ".join(request.analysis_types),
                context=context,
                rendered_prompts=rendered_prompts,
                findings=findings,
                recommendations=recommendations,
                metrics=metrics,
                execution_time=execution_time
            )
            
            logger.info(f"Analysis completed in {execution_time:.2f}s")
            logger.info(f"Generated {len(findings)} findings and {len(recommendations)} recommendations")
            
            return result
            
        except Exception as e:
            logger.error(f"Error during enhanced analysis: {e}")
            raise
    
    async def _build_project_context(self, request: AnalysisRequest) -> AndroidAnalysisContext:
        """Build comprehensive Android project context."""
        logger.info("Building Android project context...")
        
        # Create a simple project object
        project = type('Project', (), {
            'id': request.project_id,
            'name': request.project_name
        })()
        
        # Build context in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        context = await loop.run_in_executor(
            self.executor,
            self.context_builder.create_android_analysis_context,
            project,
            request.project_files
        )
        
        logger.info(f"Context built: {len(context.components)} components, "
                   f"{len(context.dependencies)} dependencies")
        
        return context
    
    async def _generate_analysis_prompts(self, context: AndroidAnalysisContext, 
                                       analysis_types: List[str]) -> Dict[str, str]:
        """Generate context-aware analysis prompts."""
        logger.info(f"Generating prompts for analysis types: {analysis_types}")
        
        rendered_prompts = {}
        
        for analysis_type in analysis_types:
            if analysis_type in self.analysis_type_templates:
                templates = self.analysis_type_templates[analysis_type]
                
                for template_name in templates:
                    logger.info(f"Rendering template: {template_name}")
                    
                    # Render template in thread pool
                    loop = asyncio.get_event_loop()
                    rendered = await loop.run_in_executor(
                        self.executor,
                        self.prompt_engine.render_template,
                        template_name,
                        context
                    )
                    
                    if rendered:
                        rendered_prompts[template_name] = rendered
                        logger.info(f"Successfully rendered {template_name} ({len(rendered)} chars)")
                    else:
                        logger.warning(f"Failed to render template: {template_name}")
            else:
                logger.warning(f"Unknown analysis type: {analysis_type}")
        
        logger.info(f"Generated {len(rendered_prompts)} analysis prompts")
        return rendered_prompts
    
    async def _perform_analysis(self, context: AndroidAnalysisContext, 
                              rendered_prompts: Dict[str, str],
                              request: AnalysisRequest) -> List[Dict[str, Any]]:
        """
        Perform actual analysis using rendered prompts.
        This is a placeholder for LLM integration.
        """
        logger.info("Performing analysis with rendered prompts...")
        
        findings = []
        
        # Simulate analysis based on context and prompts
        for prompt_name, prompt_content in rendered_prompts.items():
            category = self._get_prompt_category(prompt_name)
            
            # Generate mock findings based on context
            category_findings = await self._generate_category_findings(context, category, prompt_name)
            findings.extend(category_findings)
        
        logger.info(f"Analysis completed with {len(findings)} findings")
        return findings
    
    async def _generate_category_findings(self, context: AndroidAnalysisContext, 
                                        category: str, prompt_name: str) -> List[Dict[str, Any]]:
        """Generate findings for a specific analysis category."""
        findings = []
        
        if category == "architecture":
            findings.extend(await self._analyze_architecture(context))
        elif category == "security":
            findings.extend(await self._analyze_security(context))
        elif category == "performance":
            findings.extend(await self._analyze_performance(context))
        elif category == "code_review":
            findings.extend(await self._analyze_code_quality(context))
        elif category == "lifecycle":
            findings.extend(await self._analyze_lifecycle(context))
        
        # Add prompt metadata to findings
        for finding in findings:
            finding["analysis_prompt"] = prompt_name
            finding["category"] = category
        
        return findings
    
    async def _analyze_architecture(self, context: AndroidAnalysisContext) -> List[Dict[str, Any]]:
        """Analyze architecture patterns and structure."""
        findings = []
        
        # Check for architecture patterns
        if not context.architecture_patterns:
            findings.append({
                "type": "architecture_issue",
                "severity": "medium",
                "title": "No clear architecture pattern detected",
                "description": "The project doesn't follow a clear architecture pattern like MVVM, MVP, or Clean Architecture",
                "recommendation": "Consider implementing a well-defined architecture pattern for better maintainability"
            })
        
        # Check component distribution
        activity_count = len([c for c in context.components if c.type == "activity"])
        if activity_count > 10:
            findings.append({
                "type": "architecture_issue",
                "severity": "high",
                "title": "Too many activities",
                "description": f"Project has {activity_count} activities, which may indicate poor navigation structure",
                "recommendation": "Consider using single-activity architecture with fragments or Navigation Component"
            })
        
        # Check for modern components
        modern_components = ["androidx.lifecycle", "androidx.navigation", "androidx.room"]
        used_modern = [comp for comp in context.jetpack_components if any(mod in comp for mod in modern_components)]
        
        if len(used_modern) < 2:
            findings.append({
                "type": "architecture_recommendation",
                "severity": "low",
                "title": "Limited use of modern Android components",
                "description": f"Only using {len(used_modern)} modern Jetpack components",
                "recommendation": "Consider adopting more Jetpack components like ViewModel, LiveData, Room, or Navigation"
            })
        
        return findings
    
    async def _analyze_security(self, context: AndroidAnalysisContext) -> List[Dict[str, Any]]:
        """Analyze security configuration and permissions."""
        findings = []
        
        # Check dangerous permissions
        if context.dangerous_permissions:
            findings.append({
                "type": "security_issue",
                "severity": "high",
                "title": "Dangerous permissions detected",
                "description": f"App requests dangerous permissions: {', '.join(context.dangerous_permissions)}",
                "recommendation": "Ensure proper runtime permission handling and justify the need for each dangerous permission"
            })
        
        # Check exported components
        if context.exported_components:
            findings.append({
                "type": "security_warning",
                "severity": "medium",
                "title": "Exported components detected",
                "description": f"Components exported: {', '.join(context.exported_components)}",
                "recommendation": "Review exported components and ensure they have proper security measures"
            })
        
        # Check backup configuration
        if context.backup_allowed:
            findings.append({
                "type": "security_recommendation",
                "severity": "low",
                "title": "Backup allowed",
                "description": "App allows backup which may expose sensitive data",
                "recommendation": "Consider disabling backup for apps handling sensitive data"
            })
        
        # Check network security config
        if not context.network_security_config:
            findings.append({
                "type": "security_issue",
                "severity": "medium",
                "title": "No network security configuration",
                "description": "App doesn't have network security configuration",
                "recommendation": "Implement network security configuration to control network traffic"
            })
        
        return findings
    
    async def _analyze_performance(self, context: AndroidAnalysisContext) -> List[Dict[str, Any]]:
        """Analyze performance indicators."""
        findings = []
        
        # Check ProGuard usage
        if not context.proguard_enabled:
            findings.append({
                "type": "performance_issue",
                "severity": "medium",
                "title": "ProGuard not enabled",
                "description": "Code obfuscation and optimization not enabled",
                "recommendation": "Enable ProGuard or R8 for release builds to reduce APK size and improve performance"
            })
        
        # Check dependency count
        dependency_count = len(context.dependencies)
        if dependency_count > 50:
            findings.append({
                "type": "performance_warning",
                "severity": "medium",
                "title": "High dependency count",
                "description": f"Project has {dependency_count} dependencies",
                "recommendation": "Review dependencies and remove unused ones to reduce APK size"
            })
        
        # Check for performance-critical patterns
        if "coroutines" in context.architecture_patterns:
            findings.append({
                "type": "performance_positive",
                "severity": "info",
                "title": "Coroutines usage detected",
                "description": "Project uses Kotlin coroutines for asynchronous operations",
                "recommendation": "Continue using coroutines for efficient background processing"
            })
        
        return findings
    
    async def _analyze_code_quality(self, context: AndroidAnalysisContext) -> List[Dict[str, Any]]:
        """Analyze code quality indicators."""
        findings = []
        
        # Check language distribution
        if context.kotlin_percentage < 50 and context.java_percentage > 50:
            findings.append({
                "type": "code_quality_recommendation",
                "severity": "low",
                "title": "Consider migrating to Kotlin",
                "description": f"Project is {context.java_percentage:.1f}% Java, {context.kotlin_percentage:.1f}% Kotlin",
                "recommendation": "Consider migrating Java code to Kotlin for better language features and safety"
            })
        
        # Check testing frameworks
        if not context.testing_frameworks:
            findings.append({
                "type": "code_quality_issue",
                "severity": "high",
                "title": "No testing framework detected",
                "description": "Project doesn't appear to have testing dependencies",
                "recommendation": "Add testing frameworks like JUnit, Espresso, or Mockito for better code quality"
            })
        
        return findings
    
    async def _analyze_lifecycle(self, context: AndroidAnalysisContext) -> List[Dict[str, Any]]:
        """Analyze lifecycle management."""
        findings = []
        
        # Check for lifecycle-aware components
        lifecycle_components = [comp for comp in context.jetpack_components if "lifecycle" in comp]
        
        if not lifecycle_components:
            findings.append({
                "type": "lifecycle_issue",
                "severity": "medium",
                "title": "No lifecycle-aware components",
                "description": "Project doesn't use lifecycle-aware components",
                "recommendation": "Consider using ViewModel, LiveData, or other lifecycle-aware components"
            })
        
        # Check activity count for lifecycle complexity
        activity_count = len([c for c in context.components if c.type == "activity"])
        if activity_count > 5:
            findings.append({
                "type": "lifecycle_warning",
                "severity": "medium",
                "title": "Multiple activities may complicate lifecycle",
                "description": f"Project has {activity_count} activities",
                "recommendation": "Consider single-activity architecture to simplify lifecycle management"
            })
        
        return findings
    
    async def _generate_recommendations(self, context: AndroidAnalysisContext, 
                                      findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate high-level recommendations based on findings."""
        recommendations = []
        
        # Group findings by severity
        critical_findings = [f for f in findings if f.get("severity") == "critical"]
        high_findings = [f for f in findings if f.get("severity") == "high"]
        medium_findings = [f for f in findings if f.get("severity") == "medium"]
        
        # Generate priority recommendations
        if critical_findings:
            recommendations.append({
                "priority": "critical",
                "title": "Address Critical Issues",
                "description": f"Found {len(critical_findings)} critical issues that need immediate attention",
                "action_items": [f["title"] for f in critical_findings[:3]]
            })
        
        if high_findings:
            recommendations.append({
                "priority": "high",
                "title": "Security and Performance Improvements",
                "description": f"Found {len(high_findings)} high-priority issues",
                "action_items": [f["title"] for f in high_findings[:3]]
            })
        
        # Architecture recommendations
        if context.kotlin_percentage > 70:
            recommendations.append({
                "priority": "low",
                "title": "Modern Kotlin Development",
                "description": "Project shows good Kotlin adoption",
                "action_items": ["Continue leveraging Kotlin features", "Consider Kotlin Multiplatform"]
            })
        
        return recommendations
    
    async def _calculate_analysis_metrics(self, context: AndroidAnalysisContext, 
                                        findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate analysis metrics and scores."""
        
        # Calculate severity distribution
        severity_counts = {}
        for finding in findings:
            severity = finding.get("severity", "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        # Calculate overall health score (0-100)
        total_issues = len(findings)
        critical_weight = severity_counts.get("critical", 0) * 10
        high_weight = severity_counts.get("high", 0) * 5
        medium_weight = severity_counts.get("medium", 0) * 2
        low_weight = severity_counts.get("low", 0) * 1
        
        total_weight = critical_weight + high_weight + medium_weight + low_weight
        health_score = max(0, 100 - total_weight)
        
        # Calculate category scores
        architecture_score = self._calculate_architecture_score(context)
        security_score = self._calculate_security_score(context)
        performance_score = self._calculate_performance_score(context)
        
        return {
            "health_score": health_score,
            "total_findings": total_issues,
            "severity_distribution": severity_counts,
            "architecture_score": architecture_score,
            "security_score": security_score,
            "performance_score": performance_score,
            "kotlin_adoption": context.kotlin_percentage,
            "modern_components": len(context.jetpack_components),
            "dependency_count": len(context.dependencies)
        }
    
    def _calculate_architecture_score(self, context: AndroidAnalysisContext) -> int:
        """Calculate architecture score (0-100)."""
        score = 50  # Base score
        
        # Architecture patterns
        if context.architecture_patterns:
            score += 20
        
        # Modern components
        score += min(20, len(context.jetpack_components) * 5)
        
        # Component distribution
        activity_count = len([c for c in context.components if c.type == "activity"])
        if activity_count <= 5:
            score += 10
        
        return min(100, score)
    
    def _calculate_security_score(self, context: AndroidAnalysisContext) -> int:
        """Calculate security score (0-100)."""
        score = 80  # Base score
        
        # Dangerous permissions penalty
        score -= len(context.dangerous_permissions) * 10
        
        # Exported components penalty
        score -= len(context.exported_components) * 5
        
        # Network security config bonus
        if context.network_security_config:
            score += 10
        
        # Backup configuration
        if not context.backup_allowed:
            score += 5
        
        return max(0, min(100, score))
    
    def _calculate_performance_score(self, context: AndroidAnalysisContext) -> int:
        """Calculate performance score (0-100)."""
        score = 60  # Base score
        
        # ProGuard bonus
        if context.proguard_enabled:
            score += 15
        
        # Dependency count penalty
        if len(context.dependencies) > 30:
            score -= 10
        
        # Modern patterns bonus
        if "coroutines" in context.architecture_patterns:
            score += 15
        
        # Kotlin usage bonus
        if context.kotlin_percentage > 70:
            score += 10
        
        return max(0, min(100, score))
    
    def _get_prompt_category(self, prompt_name: str) -> str:
        """Get category for a prompt name."""
        for category, templates in self.analysis_type_templates.items():
            if prompt_name in templates:
                return category
        return "unknown"
    
    def get_analysis_summary(self, result: AnalysisResult) -> Dict[str, Any]:
        """Get a summary of analysis results."""
        return {
            "project_name": result.project_name,
            "analysis_type": result.analysis_type,
            "execution_time": result.execution_time,
            "health_score": result.metrics.get("health_score", 0),
            "total_findings": len(result.findings),
            "critical_issues": len([f for f in result.findings if f.get("severity") == "critical"]),
            "recommendations_count": len(result.recommendations),
            "kotlin_percentage": result.context.kotlin_percentage,
            "components_count": len(result.context.components),
            "dependencies_count": len(result.context.dependencies)
        } 