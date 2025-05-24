# novaguard-backend/app/analysis_module/kotlin_analysis_agent.py
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from pathlib import Path

from app.ckg_builder.models import ParsedData, ClassInfo, FunctionInfo

logger = logging.getLogger(__name__)

@dataclass
class KotlinIdiomIssue:
    """Represents a Kotlin idiom or best practice issue."""
    issue_type: str
    severity: str  # "low", "medium", "high", "critical"
    file_path: str
    line_number: int
    entity_name: str
    description: str
    suggestion: str
    kotlin_specific: bool = True

@dataclass
class KotlinCoroutineIssue:
    """Represents a Kotlin coroutine-related issue."""
    issue_type: str
    severity: str
    file_path: str
    line_number: int
    function_name: str
    description: str
    suggestion: str

class KotlinAnalysisAgent:
    """Analysis agent for Kotlin-specific code quality and idioms."""

    def __init__(self):
        self.idiom_issues: List[KotlinIdiomIssue] = []
        self.coroutine_issues: List[KotlinCoroutineIssue] = []
        
    def analyze_parsed_file(self, parsed_result: ParsedData) -> Dict[str, Any]:
        """Analyze a parsed Kotlin file for idioms and best practices."""
        if parsed_result.language != "kotlin":
            return {"error": "Not a Kotlin file"}
            
        self.idiom_issues.clear()
        self.coroutine_issues.clear()
        
        # Analyze Kotlin idioms
        self._analyze_data_class_usage(parsed_result)
        self._analyze_extension_functions(parsed_result)
        self._analyze_scope_functions(parsed_result)
        self._analyze_null_safety(parsed_result)
        self._analyze_immutability(parsed_result)
        
        # Analyze coroutines
        self._analyze_coroutine_scope_usage(parsed_result)
        self._analyze_main_thread_safety(parsed_result)
        self._analyze_resource_cleanup(parsed_result)
        self._analyze_structured_concurrency(parsed_result)
        
        # Performance analysis
        self._analyze_performance_patterns(parsed_result)
        
        return {
            "file_path": parsed_result.file_path,
            "language": parsed_result.language,
            "idiom_issues": [self._idiom_to_dict(issue) for issue in self.idiom_issues],
            "coroutine_issues": [self._coroutine_to_dict(issue) for issue in self.coroutine_issues],
            "summary": {
                "total_issues": len(self.idiom_issues) + len(self.coroutine_issues),
                "idiom_issues": len(self.idiom_issues),
                "coroutine_issues": len(self.coroutine_issues),
                "high_priority": len([i for i in self.idiom_issues if i.severity == "high"]) + 
                               len([i for i in self.coroutine_issues if i.severity == "high"])
            }
        }
    
    def _analyze_data_class_usage(self, parsed_result: ParsedData):
        """Analyze data class best practices."""
        for cls in parsed_result.classes:
            is_data_class = any("@DataClass" in decorator for decorator in cls.decorators)
            
            if is_data_class:
                # Check if data class has too many properties
                if len(cls.attributes) > 10:
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="data_class_too_many_properties",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=cls.start_line,
                        entity_name=cls.name,
                        description=f"Data class '{cls.name}' has {len(cls.attributes)} properties",
                        suggestion="Consider breaking large data classes into smaller ones"
                    ))
                
                # Check for mutable properties in data class
                for attr in cls.attributes:
                    if attr.var_type and "var " in attr.var_type:
                        self.idiom_issues.append(KotlinIdiomIssue(
                            issue_type="mutable_data_class_property",
                            severity="medium",
                            file_path=parsed_result.file_path,
                            line_number=attr.start_line,
                            entity_name=f"{cls.name}.{attr.name}",
                            description=f"Data class property '{attr.name}' is mutable",
                            suggestion="Prefer immutable properties (val) in data classes"
                        ))
            else:
                # Check if regular class could be a data class
                if (len(cls.methods) <= 3 and len(cls.attributes) >= 2 and 
                    all(attr.var_type and "val " in attr.var_type for attr in cls.attributes)):
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="could_be_data_class",
                        severity="low",
                        file_path=parsed_result.file_path,
                        line_number=cls.start_line,
                        entity_name=cls.name,
                        description=f"Class '{cls.name}' could be a data class",
                        suggestion="Consider using data class for simple data containers"
                    ))
    
    def _analyze_extension_functions(self, parsed_result: ParsedData):
        """Analyze extension function usage patterns."""
        for func in parsed_result.functions:
            is_extension = any("@Extension" in decorator for decorator in func.decorators)
            
            if is_extension:
                # Check if extension function is too complex
                line_count = func.end_line - func.start_line + 1
                if line_count > 20:
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="complex_extension_function",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        entity_name=func.name,
                        description=f"Extension function '{func.name}' is too complex ({line_count} lines)",
                        suggestion="Keep extension functions simple and focused"
                    ))
    
    def _analyze_scope_functions(self, parsed_result: ParsedData):
        """Analyze scope function usage (let, run, with, apply, also)."""
        scope_functions = ["let", "run", "with", "apply", "also"]
        
        for func in parsed_result.functions:
            if func.signature:
                # Count scope function usage
                scope_usage_count = sum(func.signature.count(sf) for sf in scope_functions)
                
                if scope_usage_count > 3:
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="excessive_scope_function_usage",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        entity_name=func.name,
                        description=f"Function '{func.name}' uses too many scope functions",
                        suggestion="Avoid excessive chaining of scope functions for readability"
                    ))
                
                # Check for nested scope functions
                for sf in scope_functions:
                    if func.signature.count(f"{sf}.{sf}") > 0:
                        self.idiom_issues.append(KotlinIdiomIssue(
                            issue_type="nested_scope_functions",
                            severity="low",
                            file_path=parsed_result.file_path,
                            line_number=func.start_line,
                            entity_name=func.name,
                            description=f"Function '{func.name}' has nested scope functions",
                            suggestion="Avoid nesting scope functions to maintain readability"
                        ))
    
    def _analyze_null_safety(self, parsed_result: ParsedData):
        """Analyze null safety violations."""
        for func in parsed_result.functions:
            if func.signature:
                # Check for force unwrapping (!!)
                force_unwrap_count = func.signature.count("!!")
                if force_unwrap_count > 0:
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="force_unwrapping",
                        severity="high",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        entity_name=func.name,
                        description=f"Function '{func.name}' uses force unwrapping ({force_unwrap_count} times)",
                        suggestion="Use safe calls (?.) or proper null checks instead of force unwrapping"
                    ))
                
                # Check for platform types usage
                if "java." in func.signature and "?" not in func.signature:
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="platform_type_without_null_check",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        entity_name=func.name,
                        description=f"Function '{func.name}' uses Java types without null safety",
                        suggestion="Add explicit nullability annotations when using Java interop"
                    ))
    
    def _analyze_immutability(self, parsed_result: ParsedData):
        """Analyze immutability recommendations."""
        for cls in parsed_result.classes:
            mutable_properties = 0
            total_properties = len(cls.attributes)
            
            for attr in cls.attributes:
                if attr.var_type and "var " in attr.var_type:
                    mutable_properties += 1
            
            if total_properties > 0:
                mutability_ratio = mutable_properties / total_properties
                
                if mutability_ratio > 0.7:
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="high_mutability",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=cls.start_line,
                        entity_name=cls.name,
                        description=f"Class '{cls.name}' has high mutability ({mutable_properties}/{total_properties} mutable)",
                        suggestion="Consider using immutable properties (val) where possible"
                    ))
    
    def _analyze_coroutine_scope_usage(self, parsed_result: ParsedData):
        """Analyze proper coroutine scope usage."""
        for func in parsed_result.functions:
            is_suspend = any("@Suspend" in decorator for decorator in func.decorators)
            
            if is_suspend:
                # Check if suspend function is called from wrong context
                if func.signature and "GlobalScope" in func.signature:
                    self.coroutine_issues.append(KotlinCoroutineIssue(
                        issue_type="global_scope_usage",
                        severity="high",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        function_name=func.name,
                        description=f"Suspend function '{func.name}' uses GlobalScope",
                        suggestion="Use structured concurrency with proper coroutine scopes"
                    ))
                
                # Check for missing coroutine scope
                if func.signature and "launch" in func.signature and "Scope" not in func.signature:
                    self.coroutine_issues.append(KotlinCoroutineIssue(
                        issue_type="missing_coroutine_scope",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        function_name=func.name,
                        description=f"Function '{func.name}' launches coroutines without explicit scope",
                        suggestion="Use explicit coroutine scope for better lifecycle management"
                    ))
    
    def _analyze_main_thread_safety(self, parsed_result: ParsedData):
        """Analyze main thread safety in coroutines."""
        for func in parsed_result.functions:
            if func.signature:
                # Check for blocking calls in suspend functions
                blocking_calls = ["Thread.sleep", "blocking", "runBlocking"]
                for blocking_call in blocking_calls:
                    if blocking_call in func.signature:
                        is_suspend = any("@Suspend" in decorator for decorator in func.decorators)
                        if is_suspend:
                            self.coroutine_issues.append(KotlinCoroutineIssue(
                                issue_type="blocking_call_in_suspend",
                                severity="high",
                                file_path=parsed_result.file_path,
                                line_number=func.start_line,
                                function_name=func.name,
                                description=f"Suspend function '{func.name}' contains blocking call",
                                suggestion="Use non-blocking alternatives or switch to IO dispatcher"
                            ))
                
                # Check for UI updates without main dispatcher
                ui_calls = ["setText", "setVisibility", "findViewById"]
                for ui_call in ui_calls:
                    if ui_call in func.signature and "Dispatchers.Main" not in func.signature:
                        self.coroutine_issues.append(KotlinCoroutineIssue(
                            issue_type="ui_update_wrong_dispatcher",
                            severity="medium",
                            file_path=parsed_result.file_path,
                            line_number=func.start_line,
                            function_name=func.name,
                            description=f"Function '{func.name}' updates UI without main dispatcher",
                            suggestion="Use Dispatchers.Main for UI updates"
                        ))
    
    def _analyze_resource_cleanup(self, parsed_result: ParsedData):
        """Analyze resource cleanup in coroutines."""
        for func in parsed_result.functions:
            if func.signature:
                # Check for resource usage without proper cleanup
                resource_patterns = ["FileInputStream", "Socket", "Database"]
                cleanup_patterns = ["close", "finally", "use"]
                
                has_resources = any(pattern in func.signature for pattern in resource_patterns)
                has_cleanup = any(pattern in func.signature for pattern in cleanup_patterns)
                
                if has_resources and not has_cleanup:
                    self.coroutine_issues.append(KotlinCoroutineIssue(
                        issue_type="missing_resource_cleanup",
                        severity="high",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        function_name=func.name,
                        description=f"Function '{func.name}' uses resources without proper cleanup",
                        suggestion="Use 'use' extension function or try-finally for resource cleanup"
                    ))
    
    def _analyze_structured_concurrency(self, parsed_result: ParsedData):
        """Analyze structured concurrency violations."""
        for func in parsed_result.functions:
            if func.signature:
                # Check for fire-and-forget coroutines
                if "launch" in func.signature and "join" not in func.signature:
                    self.coroutine_issues.append(KotlinCoroutineIssue(
                        issue_type="fire_and_forget_coroutine",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        function_name=func.name,
                        description=f"Function '{func.name}' launches coroutines without waiting",
                        suggestion="Consider using async/await or join for structured concurrency"
                    ))
                
                # Check for exception handling in coroutines
                has_coroutines = any(keyword in func.signature for keyword in ["launch", "async", "runBlocking"])
                has_exception_handling = any(keyword in func.signature for keyword in ["try", "catch", "CoroutineExceptionHandler"])
                
                if has_coroutines and not has_exception_handling:
                    self.coroutine_issues.append(KotlinCoroutineIssue(
                        issue_type="missing_exception_handling",
                        severity="medium",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        function_name=func.name,
                        description=f"Function '{func.name}' launches coroutines without exception handling",
                        suggestion="Add proper exception handling for coroutines"
                    ))
    
    def _analyze_performance_patterns(self, parsed_result: ParsedData):
        """Analyze Kotlin-specific performance patterns."""
        for func in parsed_result.functions:
            if func.signature:
                # Check for inefficient collection operations
                inefficient_patterns = [
                    ("filter.*map", "Use mapNotNull instead of filter + map"),
                    ("map.*filter", "Consider reordering: filter before map"),
                    ("forEach.*return", "Use for loop instead of forEach with early return")
                ]
                
                for pattern, suggestion in inefficient_patterns:
                    if pattern.replace(".*", "") in func.signature:
                        self.idiom_issues.append(KotlinIdiomIssue(
                            issue_type="inefficient_collection_operation",
                            severity="low",
                            file_path=parsed_result.file_path,
                            line_number=func.start_line,
                            entity_name=func.name,
                            description=f"Function '{func.name}' has inefficient collection operations",
                            suggestion=suggestion
                        ))
                
                # Check for string template performance
                if func.signature.count("$") > 5:
                    self.idiom_issues.append(KotlinIdiomIssue(
                        issue_type="complex_string_template",
                        severity="low",
                        file_path=parsed_result.file_path,
                        line_number=func.start_line,
                        entity_name=func.name,
                        description=f"Function '{func.name}' has complex string templates",
                        suggestion="Consider using StringBuilder for complex string building"
                    ))
    
    def _idiom_to_dict(self, issue: KotlinIdiomIssue) -> Dict[str, Any]:
        """Convert KotlinIdiomIssue to dictionary."""
        return {
            "type": issue.issue_type,
            "severity": issue.severity,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "entity_name": issue.entity_name,
            "description": issue.description,
            "suggestion": issue.suggestion,
            "kotlin_specific": issue.kotlin_specific
        }
    
    def _coroutine_to_dict(self, issue: KotlinCoroutineIssue) -> Dict[str, Any]:
        """Convert KotlinCoroutineIssue to dictionary."""
        return {
            "type": issue.issue_type,
            "severity": issue.severity,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "function_name": issue.function_name,
            "description": issue.description,
            "suggestion": issue.suggestion
        } 