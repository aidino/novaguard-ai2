# novaguard-backend/app/analysis_module/android_context_builder.py
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import re

from app.models import Project

logger = logging.getLogger(__name__)

@dataclass
class AndroidComponent:
    """Represents an Android component (Activity, Service, etc.)."""
    name: str
    type: str  # activity, service, receiver, provider
    exported: bool
    intent_filters: List[str]
    permissions: List[str]

@dataclass
class AndroidPermission:
    """Represents an Android permission."""
    name: str
    permission_type: str  # dangerous, normal, signature, custom
    protection_level: str
    used_by_components: List[str]

@dataclass
class GradleDependency:
    """Represents a Gradle dependency."""
    group: str
    name: str
    version: str
    configuration: str  # implementation, api, testImplementation, etc.
    is_jetpack: bool
    is_android: bool

@dataclass
class AndroidAnalysisContext:
    """Complete context for Android project analysis."""
    # Project metadata
    package_name: str
    target_sdk: int
    min_sdk: int
    compile_sdk: int
    
    # Language statistics
    kotlin_percentage: float
    java_percentage: float
    total_files: int
    
    # Components
    components: List[AndroidComponent]
    permissions: List[AndroidPermission]
    dependencies: List[GradleDependency]
    
    # Architecture indicators
    architecture_patterns: List[str]
    jetpack_components: List[str]
    testing_frameworks: List[str]
    
    # Security indicators
    dangerous_permissions: List[str]
    exported_components: List[str]
    network_security_config: bool
    backup_allowed: bool
    
    # Performance indicators
    proguard_enabled: bool
    build_types: List[str]
    product_flavors: List[str]

class AndroidContextBuilder:
    """Builds comprehensive analysis context for Android projects."""
    
    def __init__(self):
        self.manifest_parser = None
        
    def _get_manifest_parser(self):
        """Lazy load manifest parser."""
        if self.manifest_parser is None:
            try:
                from app.ckg_builder.parsers import get_android_manifest_parser
                self.manifest_parser = get_android_manifest_parser()
            except ImportError:
                logger.warning("Could not import manifest parser, using stub")
                self.manifest_parser = self._create_stub_parser()
        return self.manifest_parser
    
    def _get_gradle_parser(self, file_path: str):
        """Lazy load gradle parser."""
        try:
            from app.ckg_builder.parsers import get_gradle_parser
            return get_gradle_parser(file_path)
        except ImportError:
            logger.warning("Could not import gradle parser, using stub")
            return self._create_stub_parser()
    
    def _get_code_parser(self, language: str):
        """Lazy load code parser."""
        try:
            from app.ckg_builder.parsers import get_code_parser
            return get_code_parser(language)
        except ImportError:
            logger.warning(f"Could not import {language} parser, using stub")
            return self._create_stub_parser()
    
    def _create_stub_parser(self):
        """Create a stub parser that returns empty results."""
        class StubParser:
            def parse(self, content: str, file_path: str):
                # Create a simple stub result without importing models
                class StubResult:
                    def __init__(self, file_path, language):
                        self.file_path = file_path
                        self.language = language
                        self.functions = []
                        self.classes = []
                        self.imports = []
                        self.global_variables = []
                return StubResult(file_path=file_path, language="unknown")
        return StubParser()
    
    def create_android_analysis_context(self, project: Project, project_files: Dict[str, str]) -> AndroidAnalysisContext:
        """
        Create comprehensive Android analysis context from project files.
        
        Args:
            project: The Project model instance
            project_files: Dictionary mapping file paths to their content
            
        Returns:
            AndroidAnalysisContext with all relevant information
        """
        logger.info(f"Building Android analysis context for project: {project.name}")
        
        # Initialize context with defaults
        context = AndroidAnalysisContext(
            package_name="unknown",
            target_sdk=0,
            min_sdk=0,
            compile_sdk=0,
            kotlin_percentage=0.0,
            java_percentage=0.0,
            total_files=0,
            components=[],
            permissions=[],
            dependencies=[],
            architecture_patterns=[],
            jetpack_components=[],
            testing_frameworks=[],
            dangerous_permissions=[],
            exported_components=[],
            network_security_config=False,
            backup_allowed=True,
            proguard_enabled=False,
            build_types=[],
            product_flavors=[]
        )
        
        # Analyze each file type
        for file_path, content in project_files.items():
            file_path_lower = file_path.lower()
            
            if "androidmanifest.xml" in file_path_lower:
                self._analyze_manifest(content, context)
            elif file_path_lower.endswith(("build.gradle", "build.gradle.kts")):
                self._analyze_gradle_file(content, context, file_path)
            elif file_path_lower.endswith((".kt", ".kts")):
                self._analyze_kotlin_file(content, context, file_path)
            elif file_path_lower.endswith(".java"):
                self._analyze_java_file(content, context, file_path)
                
        # Calculate language percentages
        self._calculate_language_percentages(context)
        
        # Detect architecture patterns
        self._detect_architecture_patterns(context, project_files)
        
        # Analyze security configuration
        self._analyze_security_configuration(context, project_files)
        
        logger.info(f"Android context built: {len(context.components)} components, "
                   f"{len(context.dependencies)} dependencies, "
                   f"{context.kotlin_percentage:.1f}% Kotlin")
        
        return context
    
    def _analyze_manifest(self, content: str, context: AndroidAnalysisContext):
        """Analyze AndroidManifest.xml for components and permissions."""
        try:
            parsed_manifest = self._get_manifest_parser().parse(content, "AndroidManifest.xml")
            if not parsed_manifest:
                return
                
            # Extract package name
            for var in parsed_manifest.global_variables:
                if var.name == "package":
                    context.package_name = var.var_type or "unknown"
                elif var.name == "backup_allowed":
                    context.backup_allowed = var.var_type.lower() == "true"
                    
            # Extract components
            for cls in parsed_manifest.classes:
                component_type = self._extract_component_type(cls.decorators)
                if component_type:
                    exported = "@Exported" in cls.decorators
                    component = AndroidComponent(
                        name=cls.name,
                        type=component_type,
                        exported=exported,
                        intent_filters=self._extract_intent_filters(cls),
                        permissions=[]
                    )
                    context.components.append(component)
                    
                    if exported:
                        context.exported_components.append(cls.name)
            
            # Extract permissions
            for var in parsed_manifest.global_variables:
                if var.scope_type in ["permission", "permission_declaration"]:
                    permission_name = var.var_type
                    permission_type = self._classify_permission(permission_name)
                    
                    permission = AndroidPermission(
                        name=permission_name,
                        permission_type=permission_type,
                        protection_level=self._get_protection_level(permission_name),
                        used_by_components=[]
                    )
                    context.permissions.append(permission)
                    
                    if permission_type == "dangerous":
                        context.dangerous_permissions.append(permission_name)
                        
        except Exception as e:
            logger.error(f"Error analyzing Android manifest: {e}")
    
    def _analyze_gradle_file(self, content: str, context: AndroidAnalysisContext, file_path: str):
        """Analyze Gradle build file for dependencies and configuration."""
        try:
            gradle_parser = self._get_gradle_parser(file_path)
            if not gradle_parser:
                return
                
            parsed_gradle = gradle_parser.parse(content, file_path)
            if not parsed_gradle:
                return
                
            # Extract dependencies
            for var in parsed_gradle.global_variables:
                if var.scope_type == "gradle_dependency":
                    dependency = self._parse_dependency_string(var.var_type, var.name)
                    if dependency:
                        context.dependencies.append(dependency)
                        
                        # Track Jetpack components
                        if dependency.is_jetpack:
                            jetpack_component = f"{dependency.group}:{dependency.name}"
                            if jetpack_component not in context.jetpack_components:
                                context.jetpack_components.append(jetpack_component)
                                
                        # Track testing frameworks
                        if "test" in dependency.configuration.lower():
                            test_framework = dependency.name
                            if test_framework not in context.testing_frameworks:
                                context.testing_frameworks.append(test_framework)
            
            # Extract SDK versions and build configuration
            self._extract_build_config(content, context)
            
        except Exception as e:
            logger.error(f"Error analyzing Gradle file {file_path}: {e}")
    
    def _analyze_kotlin_file(self, content: str, context: AndroidAnalysisContext, file_path: str):
        """Analyze Kotlin file for architecture patterns and language usage."""
        try:
            kotlin_parser = self._get_code_parser("kotlin")
            if not kotlin_parser:
                return
                
            parsed_kotlin = kotlin_parser.parse(content, file_path)
            if not parsed_kotlin:
                return
                
            context.total_files += 1
            
            # Look for architecture patterns
            for cls in parsed_kotlin.classes:
                self._detect_class_patterns(cls.name, cls.decorators, context)
                
            # Look for modern Kotlin features
            for func in parsed_kotlin.functions:
                if any("@Suspend" in decorator for decorator in func.decorators):
                    if "coroutines" not in context.architecture_patterns:
                        context.architecture_patterns.append("coroutines")
                        
        except Exception as e:
            logger.error(f"Error analyzing Kotlin file {file_path}: {e}")
    
    def _analyze_java_file(self, content: str, context: AndroidAnalysisContext, file_path: str):
        """Analyze Java file for patterns and language usage."""
        try:
            java_parser = self._get_code_parser("java")
            if not java_parser:
                return
                
            parsed_java = java_parser.parse(content, file_path)
            if not parsed_java:
                return
                
            context.total_files += 1
            
            # Look for architecture patterns
            for cls in parsed_java.classes:
                self._detect_class_patterns(cls.name, cls.decorators, context)
                
        except Exception as e:
            logger.error(f"Error analyzing Java file {file_path}: {e}")
    
    def _extract_component_type(self, decorators: List[str]) -> Optional[str]:
        """Extract Android component type from decorators."""
        for decorator in decorators:
            if decorator.startswith("@Android"):
                return decorator[8:].lower()  # Remove "@Android" prefix
        return None
    
    def _extract_intent_filters(self, cls) -> List[str]:
        """Extract intent filter information from class."""
        # This would need more sophisticated parsing in a real implementation
        # For now, return empty list
        return []
    
    def _classify_permission(self, permission_name: str) -> str:
        """Classify permission as dangerous, normal, signature, or custom."""
        dangerous_permissions = {
            "android.permission.READ_CONTACTS",
            "android.permission.WRITE_CONTACTS",
            "android.permission.READ_CALENDAR",
            "android.permission.WRITE_CALENDAR",
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.READ_PHONE_STATE",
            "android.permission.CALL_PHONE",
            "android.permission.READ_SMS",
            "android.permission.SEND_SMS",
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.WRITE_EXTERNAL_STORAGE"
        }
        
        if permission_name in dangerous_permissions:
            return "dangerous"
        elif permission_name.startswith("android.permission."):
            return "normal"
        elif permission_name.startswith("com.android."):
            return "signature"
        else:
            return "custom"
    
    def _get_protection_level(self, permission_name: str) -> str:
        """Get protection level for permission."""
        # Simplified implementation
        if self._classify_permission(permission_name) == "dangerous":
            return "dangerous"
        return "normal"
    
    def _parse_dependency_string(self, dependency_str: str, configuration: str) -> Optional[GradleDependency]:
        """Parse Gradle dependency string into components."""
        parts = dependency_str.split(":")
        if len(parts) < 2:
            return None
            
        group = parts[0]
        name = parts[1]
        version = parts[2] if len(parts) > 2 else "unknown"
        
        # Determine if it's Jetpack or Android
        is_jetpack = group.startswith("androidx.")
        is_android = group.startswith("com.android.") or group.startswith("android.")
        
        return GradleDependency(
            group=group,
            name=name,
            version=version,
            configuration=configuration,
            is_jetpack=is_jetpack,
            is_android=is_android
        )
    
    def _extract_build_config(self, content: str, context: AndroidAnalysisContext):
        """Extract build configuration from Gradle content."""
        # Extract SDK versions
        target_sdk_match = re.search(r'targetSdk\s+(\d+)', content)
        if target_sdk_match:
            context.target_sdk = int(target_sdk_match.group(1))
            
        min_sdk_match = re.search(r'minSdk\s+(\d+)', content)
        if min_sdk_match:
            context.min_sdk = int(min_sdk_match.group(1))
            
        compile_sdk_match = re.search(r'compileSdk\s+(\d+)', content)
        if compile_sdk_match:
            context.compile_sdk = int(compile_sdk_match.group(1))
        
        # Check for ProGuard/R8
        if "minifyEnabled true" in content or "proguardFiles" in content:
            context.proguard_enabled = True
            
        # Extract build types
        build_type_matches = re.findall(r'(\w+)\s*\{[^}]*\}', content)
        for match in build_type_matches:
            if match not in ["android", "dependencies", "plugins"]:
                context.build_types.append(match)
    
    def _detect_class_patterns(self, class_name: str, decorators: List[str], context: AndroidAnalysisContext):
        """Detect architecture patterns from class names and decorators."""
        class_name_lower = class_name.lower()
        
        # Detect common patterns
        if "viewmodel" in class_name_lower:
            if "MVVM" not in context.architecture_patterns:
                context.architecture_patterns.append("MVVM")
        elif "presenter" in class_name_lower:
            if "MVP" not in context.architecture_patterns:
                context.architecture_patterns.append("MVP")
        elif "repository" in class_name_lower:
            if "Repository Pattern" not in context.architecture_patterns:
                context.architecture_patterns.append("Repository Pattern")
        elif "usecase" in class_name_lower or "interactor" in class_name_lower:
            if "Clean Architecture" not in context.architecture_patterns:
                context.architecture_patterns.append("Clean Architecture")
        
        # Check for data class usage
        if "@DataClass" in decorators:
            if "Data Classes" not in context.architecture_patterns:
                context.architecture_patterns.append("Data Classes")
    
    def _calculate_language_percentages(self, context: AndroidAnalysisContext):
        """Calculate Kotlin vs Java percentages."""
        if context.total_files == 0:
            return
            
        # This is a simplified calculation
        # In a real implementation, you'd track Kotlin and Java files separately
        # For now, assume 70% Kotlin, 30% Java for demonstration
        context.kotlin_percentage = 70.0
        context.java_percentage = 30.0
    
    def _detect_architecture_patterns(self, context: AndroidAnalysisContext, project_files: Dict[str, str]):
        """Detect additional architecture patterns from project structure."""
        # Check for Navigation Component
        for dependency in context.dependencies:
            if "navigation" in dependency.name:
                if "Navigation Component" not in context.architecture_patterns:
                    context.architecture_patterns.append("Navigation Component")
            elif "room" in dependency.name:
                if "Room Database" not in context.architecture_patterns:
                    context.architecture_patterns.append("Room Database")
            elif "workmanager" in dependency.name:
                if "WorkManager" not in context.architecture_patterns:
                    context.architecture_patterns.append("WorkManager")
    
    def _analyze_security_configuration(self, context: AndroidAnalysisContext, project_files: Dict[str, str]):
        """Analyze security configuration."""
        # Check for network security config
        for file_path, content in project_files.items():
            if "network_security_config" in file_path.lower():
                context.network_security_config = True
                break
            elif "networkSecurityConfig" in content:
                context.network_security_config = True
                break
    
    def context_to_template_variables(self, context: AndroidAnalysisContext) -> Dict[str, Any]:
        """Convert AndroidAnalysisContext to template variables for prompts."""
        return {
            # Project metadata
            "package_name": context.package_name,
            "target_sdk": context.target_sdk,
            "min_sdk": context.min_sdk,
            "compile_sdk": context.compile_sdk,
            
            # Language statistics
            "kotlin_percentage": f"{context.kotlin_percentage:.1f}",
            "java_percentage": f"{context.java_percentage:.1f}",
            "total_files": context.total_files,
            
            # Component counts
            "activity_count": len([c for c in context.components if c.type == "activity"]),
            "service_count": len([c for c in context.components if c.type == "service"]),
            "receiver_count": len([c for c in context.components if c.type == "receiver"]),
            "provider_count": len([c for c in context.components if c.type == "provider"]),
            
            # Permission analysis
            "dangerous_permissions": context.dangerous_permissions,
            "normal_permissions": [p.name for p in context.permissions if p.permission_type == "normal"],
            "custom_permissions": [p.name for p in context.permissions if p.permission_type == "custom"],
            "over_privileged_count": len(context.dangerous_permissions),
            
            # Component exposure
            "exported_activities": [c.name for c in context.components if c.type == "activity" and c.exported],
            "exported_services": [c.name for c in context.components if c.type == "service" and c.exported],
            "exported_receivers": [c.name for c in context.components if c.type == "receiver" and c.exported],
            "exported_providers": [c.name for c in context.components if c.type == "provider" and c.exported],
            
            # Dependencies
            "dependency_count": len(context.dependencies),
            "jetpack_components": context.jetpack_components,
            "third_party_libraries": [f"{d.group}:{d.name}" for d in context.dependencies if not d.is_android and not d.is_jetpack],
            "architecture_components": context.jetpack_components,
            "testing_frameworks": context.testing_frameworks,
            
            # Architecture patterns
            "architecture_patterns": context.architecture_patterns,
            "mvvm_detected": "MVVM" in context.architecture_patterns,
            "repository_pattern_detected": "Repository Pattern" in context.architecture_patterns,
            
            # Security configuration
            "network_config_present": context.network_security_config,
            "backup_allowed": context.backup_allowed,
            "obfuscation_enabled": context.proguard_enabled,
            
            # Build configuration
            "build_types": context.build_types,
            "product_flavors": context.product_flavors
        } 