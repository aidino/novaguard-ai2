# novaguard-backend/app/analysis_module/__init__.py
"""
Analysis module for language-specific code analysis agents.
"""

# Phase 4: Language-Specific Analysis Agents (temporarily disabled)
# from .java_analysis_agent import JavaAnalysisAgent
# from .kotlin_analysis_agent import KotlinAnalysisAgent

# Phase 5: Enhanced LLM Prompts
from .android_context_builder import (
    AndroidContextBuilder,
    AndroidAnalysisContext,
    AndroidComponent,
    AndroidPermission,
    GradleDependency
)
from .prompt_template_engine import (
    PromptTemplateEngine,
    PromptTemplate
)

# Phase 6: Enhanced Analysis Integration
from .enhanced_analysis_engine import (
    EnhancedAnalysisEngine,
    AnalysisResult,
    AnalysisRequest
)

__all__ = [
    # Phase 4 exports (temporarily disabled)
    # 'JavaAnalysisAgent',
    # 'KotlinAnalysisAgent',
    
    # Phase 5 exports
    'AndroidContextBuilder',
    'AndroidAnalysisContext', 
    'AndroidComponent',
    'AndroidPermission',
    'GradleDependency',
    'PromptTemplateEngine',
    'PromptTemplate',
    
    # Phase 6 exports
    'EnhancedAnalysisEngine',
    'AnalysisResult',
    'AnalysisRequest'
]