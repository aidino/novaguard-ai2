# novaguard-backend/app/analysis_module/prompt_template_engine.py
import logging
import re
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass

from .android_context_builder import AndroidAnalysisContext, AndroidContextBuilder

logger = logging.getLogger(__name__)

@dataclass
class PromptTemplate:
    """Represents a prompt template with metadata."""
    name: str
    file_path: str
    content: str
    variables: List[str]
    category: str  # architecture, security, performance, code_review, lifecycle

class PromptTemplateEngine:
    """Engine for loading and rendering Android analysis prompt templates."""
    
    def __init__(self, templates_dir: str = "app/prompts"):
        self.templates_dir = Path(templates_dir)
        self.templates: Dict[str, PromptTemplate] = {}
        self.context_builder = AndroidContextBuilder()
        self._load_templates()
    
    def _load_templates(self):
        """Load all prompt templates from the templates directory."""
        try:
            if not self.templates_dir.exists():
                logger.error(f"Templates directory not found: {self.templates_dir}")
                return
            
            template_files = {
                "android_architecture_analyst": "architecture",
                "android_performance_analyst": "performance", 
                "android_security_analyst": "security",
                "kotlin_code_reviewer": "code_review",
                "java_code_reviewer": "code_review",
                "android_lifecycle_analyst": "lifecycle"
            }
            
            for template_name, category in template_files.items():
                template_path = self.templates_dir / f"{template_name}.md"
                if template_path.exists():
                    content = template_path.read_text(encoding="utf-8")
                    variables = self._extract_template_variables(content)
                    
                    self.templates[template_name] = PromptTemplate(
                        name=template_name,
                        file_path=str(template_path),
                        content=content,
                        variables=variables,
                        category=category
                    )
                    logger.info(f"Loaded template: {template_name} ({len(variables)} variables)")
                else:
                    logger.warning(f"Template file not found: {template_path}")
                    
        except Exception as e:
            logger.error(f"Error loading templates: {e}")
    
    def _extract_template_variables(self, content: str) -> List[str]:
        """Extract template variables from content (e.g., {{variable_name}})."""
        pattern = r'\{\{([^}]+)\}\}'
        variables = re.findall(pattern, content)
        return list(set(variables))  # Remove duplicates
    
    def render_template(self, template_name: str, context: AndroidAnalysisContext, 
                       additional_variables: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Render a specific template with Android analysis context.
        
        Args:
            template_name: Name of the template to render
            context: Android analysis context
            additional_variables: Additional variables to include
            
        Returns:
            Rendered prompt string or None if template not found
        """
        if template_name not in self.templates:
            logger.error(f"Template not found: {template_name}")
            return None
            
        template = self.templates[template_name]
        
        # Get base variables from context
        variables = self.context_builder.context_to_template_variables(context)
        
        # Add additional variables if provided
        if additional_variables:
            variables.update(additional_variables)
            
        # Add template-specific default values
        variables.update(self._get_default_variables(template_name))
        
        try:
            rendered_content = self._render_content(template.content, variables)
            logger.info(f"Successfully rendered template: {template_name}")
            return rendered_content
            
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            return None
    
    def _render_content(self, content: str, variables: Dict[str, Any]) -> str:
        """Render template content by replacing variables."""
        rendered = content
        
        for var_name, var_value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            
            # Convert value to string with appropriate formatting
            if isinstance(var_value, list):
                if not var_value:  # Empty list
                    str_value = "None"
                else:
                    str_value = ", ".join(str(item) for item in var_value)
            elif isinstance(var_value, bool):
                str_value = "Yes" if var_value else "No"
            elif var_value is None:
                str_value = "Not available"
            else:
                str_value = str(var_value)
                
            rendered = rendered.replace(placeholder, str_value)
        
        return rendered
    
    def _get_default_variables(self, template_name: str) -> Dict[str, Any]:
        """Get default variables for specific template types."""
        defaults = {
            # Common defaults
            "android_version": "Unknown",
            "kotlin_version": "Unknown", 
            "coroutines_version": "Unknown",
            "target_platform": "Android",
            "language_level": "Unknown",
            "jvm_target": "Unknown",
            "build_tool": "Gradle",
            "testing_framework": "JUnit",
            "di_framework": "Unknown",
            "reactive_framework": "Unknown",
            
            # Architecture specific
            "fragment_count": 0,
            "multi_activity_app": False,
            "fragment_usage_pattern": "Standard",
            "background_task_count": 0,
            "custom_observers": 0,
            "viewmodel_usage": False,
            "livedata_usage": False,
            "navigation_component": False,
            "workmanager_usage": False,
            "room_usage": False,
            
            # Performance specific
            "min_ram": 1024,
            "max_ram": 8192,
            "storage_type": "Flash",
            "network_types": "WiFi, Cellular",
            "apk_size": 0,
            "cold_start_time": 0,
            "warm_start_time": 0,
            "memory_usage": 0,
            "battery_drain": 0,
            "launch_components": "Unknown",
            "main_flows": "Unknown",
            "sync_operations": "Unknown",
            
            # Security specific
            "signing_scheme": "v2",
            "vulnerable_dependencies": [],
            "outdated_libraries": [],
            "high_risk_libraries": [],
            "deep_link_patterns": [],
            "signature_permissions": [],
            
            # Code review specific
            "interface_count": 0,
            "design_patterns": [],
            "test_coverage": 0,
            "cyclomatic_complexity": 0,
            
            # Lifecycle specific
            "lifecycle_score": 5,
            "memory_leak_risk": "Medium",
            "config_change_score": 5,
            "background_compliance": 5,
            "modern_component_score": 5
        }
        
        return defaults
    
    def get_available_templates(self) -> List[str]:
        """Get list of available template names."""
        return list(self.templates.keys())
    
    def get_template_info(self, template_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific template."""
        if template_name not in self.templates:
            return None
            
        template = self.templates[template_name]
        return {
            "name": template.name,
            "category": template.category,
            "variables": template.variables,
            "variable_count": len(template.variables),
            "file_path": template.file_path
        }
    
    def render_all_templates(self, context: AndroidAnalysisContext) -> Dict[str, str]:
        """
        Render all available templates with the given context.
        
        Args:
            context: Android analysis context
            
        Returns:
            Dictionary mapping template names to rendered content
        """
        rendered_templates = {}
        
        for template_name in self.templates.keys():
            rendered = self.render_template(template_name, context)
            if rendered:
                rendered_templates[template_name] = rendered
            else:
                logger.error(f"Failed to render template: {template_name}")
        
        return rendered_templates
    
    def render_templates_by_category(self, category: str, context: AndroidAnalysisContext) -> Dict[str, str]:
        """
        Render all templates of a specific category.
        
        Args:
            category: Template category (architecture, security, performance, etc.)
            context: Android analysis context
            
        Returns:
            Dictionary mapping template names to rendered content
        """
        rendered_templates = {}
        
        for template_name, template in self.templates.items():
            if template.category == category:
                rendered = self.render_template(template_name, context)
                if rendered:
                    rendered_templates[template_name] = rendered
                    
        return rendered_templates
    
    def validate_template_variables(self, template_name: str, context: AndroidAnalysisContext) -> Dict[str, Any]:
        """
        Validate that all template variables can be satisfied by the context.
        
        Args:
            template_name: Name of template to validate
            context: Android analysis context
            
        Returns:
            Dictionary with validation results
        """
        if template_name not in self.templates:
            return {"valid": False, "error": "Template not found"}
            
        template = self.templates[template_name]
        context_variables = self.context_builder.context_to_template_variables(context)
        default_variables = self._get_default_variables(template_name)
        available_variables = set(context_variables.keys()) | set(default_variables.keys())
        
        missing_variables = []
        for var in template.variables:
            if var not in available_variables:
                missing_variables.append(var)
        
        return {
            "valid": len(missing_variables) == 0,
            "template_variables": template.variables,
            "available_variables": list(available_variables),
            "missing_variables": missing_variables,
            "total_variables": len(template.variables),
            "satisfied_variables": len(template.variables) - len(missing_variables)
        } 