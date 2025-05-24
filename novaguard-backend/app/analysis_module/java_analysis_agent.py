# novaguard-backend/app/analysis_module/java_analysis_agent.py
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from pathlib import Path

from app.ckg_builder.models import ParsedData, ClassInfo, FunctionInfo

logger = logging.getLogger(__name__)

@dataclass
class JavaCodeSmell:
    """Represents a Java code smell finding."""
    smell_type: str
    severity: str  # "low", "medium", "high", "critical"
    file_path: str
    line_number: int
    entity_name: str
    description: str
    suggestion: str
    metrics: Dict[str, Any] = None

@dataclass
class JavaDesignPattern:
    """Represents a detected Java design pattern."""
    pattern_type: str
    confidence: float  # 0.0 to 1.0
    file_path: str
    class_name: str
    description: str
    components: List[str] = None

class JavaAnalysisAgent:
    """Analysis agent for Java-specific code quality and patterns."""

    def __init__(self):
        self.code_smells: List[JavaCodeSmell] = []
        self.design_patterns: List[JavaDesignPattern] = []
        
    def analyze_parsed_file(self, parsed_result: ParsedData) -> Dict[str, Any]:
        """Analyze a parsed Java file for code smells and patterns."""
        if parsed_result.language != "java":
            return {"error": "Not a Java file"}
            
        self.code_smells.clear()
        self.design_patterns.clear()
        
        # Analyze code smells
        self._detect_god_classes(parsed_result)
        self._detect_long_parameter_lists(parsed_result)
        self._detect_deep_inheritance(parsed_result)
        self._detect_unused_imports(parsed_result)
        self._detect_missing_documentation(parsed_result)
        self._analyze_cyclomatic_complexity(parsed_result)
        
        # Analyze design patterns
        self._detect_singleton_pattern(parsed_result)
        self._detect_factory_pattern(parsed_result)
        self._detect_observer_pattern(parsed_result)
        self._detect_builder_pattern(parsed_result)
        
        # Analyze performance issues
        self._detect_performance_issues(parsed_result)
        
        return {
            "file_path": parsed_result.file_path,
            "language": parsed_result.language,
            "code_smells": [self._smell_to_dict(smell) for smell in self.code_smells],
            "design_patterns": [self._pattern_to_dict(pattern) for pattern in self.design_patterns],
            "summary": {
                "total_code_smells": len(self.code_smells),
                "critical_issues": len([s for s in self.code_smells if s.severity == "critical"]),
                "high_issues": len([s for s in self.code_smells if s.severity == "high"]),
                "patterns_detected": len(self.design_patterns)
            }
        }
    
    def _detect_god_classes(self, parsed_result: ParsedData):
        """Detect God classes (classes with too many lines or methods)."""
        for cls in parsed_result.classes:
            line_count = cls.end_line - cls.start_line + 1
            method_count = len(cls.methods)
            
            if line_count > 500:
                self.code_smells.append(JavaCodeSmell(
                    smell_type="god_class",
                    severity="high" if line_count > 1000 else "medium",
                    file_path=parsed_result.file_path,
                    line_number=cls.start_line,
                    entity_name=cls.name,
                    description=f"Class '{cls.name}' has {line_count} lines, which is too many",
                    suggestion="Consider breaking this class into smaller, more focused classes",
                    metrics={"line_count": line_count, "method_count": method_count}
                ))
            
            if method_count > 20:
                self.code_smells.append(JavaCodeSmell(
                    smell_type="too_many_methods",
                    severity="medium",
                    file_path=parsed_result.file_path,
                    line_number=cls.start_line,
                    entity_name=cls.name,
                    description=f"Class '{cls.name}' has {method_count} methods",
                    suggestion="Consider using composition or extracting functionality to separate classes",
                    metrics={"method_count": method_count}
                ))
    
    def _detect_long_parameter_lists(self, parsed_result: ParsedData):
        """Detect methods with too many parameters."""
        for func in parsed_result.functions:
            param_count = len(func.parameters)
            
            if param_count > 7:
                self.code_smells.append(JavaCodeSmell(
                    smell_type="long_parameter_list",
                    severity="medium" if param_count <= 10 else "high",
                    file_path=parsed_result.file_path,
                    line_number=func.start_line,
                    entity_name=func.name,
                    description=f"Method '{func.name}' has {param_count} parameters",
                    suggestion="Consider using parameter objects or builder pattern",
                    metrics={"parameter_count": param_count}
                ))
    
    def _detect_deep_inheritance(self, parsed_result: ParsedData):
        """Detect deep inheritance hierarchies."""
        # This would require cross-file analysis in a real implementation
        # For now, we'll detect classes with many superclasses
        for cls in parsed_result.classes:
            if len(cls.superclasses) > 3:
                self.code_smells.append(JavaCodeSmell(
                    smell_type="deep_inheritance",
                    severity="medium",
                    file_path=parsed_result.file_path,
                    line_number=cls.start_line,
                    entity_name=cls.name,
                    description=f"Class '{cls.name}' has complex inheritance",
                    suggestion="Consider using composition over inheritance",
                    metrics={"superclass_count": len(cls.superclasses)}
                ))
    
    def _detect_unused_imports(self, parsed_result: ParsedData):
        """Detect potentially unused imports."""
        # Simple heuristic: check if import names appear in the file content
        # This would need more sophisticated analysis in practice
        for imp in parsed_result.imports:
            if imp.imported_names:
                for name, alias in imp.imported_names:
                    # This is a simplified check
                    if name and name not in ["*"]:
                        self.code_smells.append(JavaCodeSmell(
                            smell_type="potential_unused_import",
                            severity="low",
                            file_path=parsed_result.file_path,
                            line_number=imp.start_line,
                            entity_name=name,
                            description=f"Import '{name}' might be unused",
                            suggestion="Remove unused imports to improve code clarity"
                        ))
    
    def _detect_missing_documentation(self, parsed_result: ParsedData):
        """Detect classes and methods without documentation."""
        for cls in parsed_result.classes:
            # Check if class has JavaDoc (simplified check)
            if not any("@" in decorator for decorator in cls.decorators):
                self.code_smells.append(JavaCodeSmell(
                    smell_type="missing_documentation",
                    severity="low",
                    file_path=parsed_result.file_path,
                    line_number=cls.start_line,
                    entity_name=cls.name,
                    description=f"Class '{cls.name}' lacks documentation",
                    suggestion="Add JavaDoc comments to document the class purpose"
                ))
        
        for func in parsed_result.functions:
            if func.class_name and not any("@" in decorator for decorator in func.decorators):
                self.code_smells.append(JavaCodeSmell(
                    smell_type="missing_method_documentation",
                    severity="low",
                    file_path=parsed_result.file_path,
                    line_number=func.start_line,
                    entity_name=func.name,
                    description=f"Method '{func.name}' lacks documentation",
                    suggestion="Add JavaDoc comments to document method behavior"
                ))
    
    def _analyze_cyclomatic_complexity(self, parsed_result: ParsedData):
        """Analyze cyclomatic complexity of methods."""
        for func in parsed_result.functions:
            # Simplified complexity calculation based on control structures
            complexity = 1  # Base complexity
            
            if func.signature:
                # Count control flow keywords (simplified)
                control_keywords = ["if", "else", "for", "while", "switch", "case", "catch", "&&", "||"]
                for keyword in control_keywords:
                    complexity += func.signature.count(keyword)
            
            if complexity > 10:
                self.code_smells.append(JavaCodeSmell(
                    smell_type="high_cyclomatic_complexity",
                    severity="high" if complexity > 20 else "medium",
                    file_path=parsed_result.file_path,
                    line_number=func.start_line,
                    entity_name=func.name,
                    description=f"Method '{func.name}' has high complexity ({complexity})",
                    suggestion="Break down the method into smaller, simpler methods",
                    metrics={"cyclomatic_complexity": complexity}
                ))
    
    def _detect_singleton_pattern(self, parsed_result: ParsedData):
        """Detect Singleton pattern implementation."""
        for cls in parsed_result.classes:
            has_private_constructor = False
            has_static_instance = False
            has_get_instance = False
            
            for method in cls.methods:
                if method.name == cls.name and "private" in method.signature:
                    has_private_constructor = True
                elif "getInstance" in method.name and "static" in method.signature:
                    has_get_instance = True
            
            for attr in cls.attributes:
                if "static" in attr.var_type and cls.name.lower() in attr.name.lower():
                    has_static_instance = True
            
            if has_private_constructor and has_static_instance and has_get_instance:
                self.design_patterns.append(JavaDesignPattern(
                    pattern_type="singleton",
                    confidence=0.9,
                    file_path=parsed_result.file_path,
                    class_name=cls.name,
                    description=f"Class '{cls.name}' implements Singleton pattern",
                    components=["private constructor", "static instance", "getInstance method"]
                ))
    
    def _detect_factory_pattern(self, parsed_result: ParsedData):
        """Detect Factory pattern implementation."""
        for cls in parsed_result.classes:
            factory_methods = []
            
            for method in cls.methods:
                if ("create" in method.name.lower() or "make" in method.name.lower() or 
                    "build" in method.name.lower()) and "static" in method.signature:
                    factory_methods.append(method.name)
            
            if factory_methods:
                self.design_patterns.append(JavaDesignPattern(
                    pattern_type="factory",
                    confidence=0.7,
                    file_path=parsed_result.file_path,
                    class_name=cls.name,
                    description=f"Class '{cls.name}' implements Factory pattern",
                    components=factory_methods
                ))
    
    def _detect_observer_pattern(self, parsed_result: ParsedData):
        """Detect Observer pattern implementation."""
        for cls in parsed_result.classes:
            has_listeners = False
            has_notify_methods = False
            
            for method in cls.methods:
                if ("addListener" in method.name or "removeListener" in method.name or
                    "subscribe" in method.name or "unsubscribe" in method.name):
                    has_listeners = True
                elif ("notify" in method.name.lower() or "fire" in method.name.lower()):
                    has_notify_methods = True
            
            if has_listeners and has_notify_methods:
                self.design_patterns.append(JavaDesignPattern(
                    pattern_type="observer",
                    confidence=0.8,
                    file_path=parsed_result.file_path,
                    class_name=cls.name,
                    description=f"Class '{cls.name}' implements Observer pattern"
                ))
    
    def _detect_builder_pattern(self, parsed_result: ParsedData):
        """Detect Builder pattern implementation."""
        for cls in parsed_result.classes:
            if "builder" in cls.name.lower():
                has_build_method = False
                has_fluent_methods = 0
                
                for method in cls.methods:
                    if method.name == "build":
                        has_build_method = True
                    elif cls.name in method.signature:  # Returns builder type
                        has_fluent_methods += 1
                
                if has_build_method and has_fluent_methods > 2:
                    self.design_patterns.append(JavaDesignPattern(
                        pattern_type="builder",
                        confidence=0.9,
                        file_path=parsed_result.file_path,
                        class_name=cls.name,
                        description=f"Class '{cls.name}' implements Builder pattern"
                    ))
    
    def _detect_performance_issues(self, parsed_result: ParsedData):
        """Detect potential performance issues."""
        for func in parsed_result.functions:
            # Check for string concatenation in loops (simplified)
            if func.signature and "for" in func.signature and "+" in func.signature:
                self.code_smells.append(JavaCodeSmell(
                    smell_type="string_concatenation_in_loop",
                    severity="medium",
                    file_path=parsed_result.file_path,
                    line_number=func.start_line,
                    entity_name=func.name,
                    description=f"Method '{func.name}' may have inefficient string concatenation",
                    suggestion="Use StringBuilder for string concatenation in loops"
                ))
    
    def _smell_to_dict(self, smell: JavaCodeSmell) -> Dict[str, Any]:
        """Convert JavaCodeSmell to dictionary."""
        return {
            "type": smell.smell_type,
            "severity": smell.severity,
            "file_path": smell.file_path,
            "line_number": smell.line_number,
            "entity_name": smell.entity_name,
            "description": smell.description,
            "suggestion": smell.suggestion,
            "metrics": smell.metrics or {}
        }
    
    def _pattern_to_dict(self, pattern: JavaDesignPattern) -> Dict[str, Any]:
        """Convert JavaDesignPattern to dictionary."""
        return {
            "type": pattern.pattern_type,
            "confidence": pattern.confidence,
            "file_path": pattern.file_path,
            "class_name": pattern.class_name,
            "description": pattern.description,
            "components": pattern.components or []
        } 