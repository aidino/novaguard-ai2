# novaguard-backend/app/ckg_builder/parsers/gradle_parser.py
import logging
from typing import Optional, List, Dict, Any
import re

# Import shared base classes
from .base_classes import (
    ParsedFileResult,
    ExtractedFunction,
    ExtractedClass,
    ExtractedImport,
    ExtractedVariable
)

logger = logging.getLogger(__name__)

class BaseGradleParser:
    """Base class for Gradle parsers."""
    
    def __init__(self):
        self.dependencies_pattern = None
        self.plugins_pattern = None
        self.android_config_pattern = None
    
    def parse(self, content: str, file_path: str) -> Optional[ParsedFileResult]:
        """Parse Gradle build file content."""
        try:
            result = ParsedFileResult(file_path=file_path, language="gradle")
            
            # Parse dependencies
            self._parse_dependencies(content, result)
            
            # Parse plugins
            self._parse_plugins(content, result)
            
            # Parse Android configuration
            self._parse_android_config(content, result)
            
            return result
        except Exception as e:
            logger.error(f"Error parsing Gradle file {file_path}: {e}")
            return None
    
    def _parse_dependencies(self, content: str, result: ParsedFileResult):
        """Parse dependencies block."""
        raise NotImplementedError("Subclasses must implement _parse_dependencies")
    
    def _parse_plugins(self, content: str, result: ParsedFileResult):
        """Parse plugins block."""
        raise NotImplementedError("Subclasses must implement _parse_plugins")
    
    def _parse_android_config(self, content: str, result: ParsedFileResult):
        """Parse Android configuration."""
        raise NotImplementedError("Subclasses must implement _parse_android_config")

class GroovyGradleParser(BaseGradleParser):
    """Parser for Groovy-based build.gradle files."""
    
    def __init__(self):
        super().__init__()
        # Groovy patterns
        self.dependencies_pattern = re.compile(
            r'dependencies\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', 
            re.DOTALL
        )
        self.dependency_line_pattern = re.compile(
            r'\s*(\w+)\s+[\'"]([^\'"]+)[\'"]',
            re.MULTILINE
        )
        self.plugins_pattern = re.compile(
            r'plugins\s*\{([^}]*)\}', 
            re.DOTALL
        )
        self.plugin_line_pattern = re.compile(
            r'id\s+[\'"]([^\'"]+)[\'"](?:\s+version\s+[\'"]([^\'"]+)[\'"])?',
            re.MULTILINE
        )
        self.android_pattern = re.compile(
            r'android\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', 
            re.DOTALL
        )
    
    def _parse_dependencies(self, content: str, result: ParsedFileResult):
        """Parse Groovy dependencies block."""
        deps_match = self.dependencies_pattern.search(content)
        if not deps_match:
            return
        
        deps_content = deps_match.group(1)
        line_number = content[:deps_match.start()].count('\n') + 1
        
        for match in self.dependency_line_pattern.finditer(deps_content):
            config = match.group(1)  # implementation, api, testImplementation, etc.
            dependency = match.group(2)  # group:artifact:version
            
            dep_variable = ExtractedVariable(
                name=f"dependency_{config}_{dependency}",
                start_line=line_number + deps_content[:match.start()].count('\n'),
                end_line=line_number + deps_content[:match.end()].count('\n'),
                scope_name="dependencies",
                scope_type="gradle_dependency",
                var_type=config
            )
            result.global_variables.append(dep_variable)
    
    def _parse_plugins(self, content: str, result: ParsedFileResult):
        """Parse Groovy plugins block."""
        plugins_match = self.plugins_pattern.search(content)
        if not plugins_match:
            # Also check for apply plugin syntax
            apply_pattern = re.compile(r'apply\s+plugin:\s*[\'"]([^\'"]+)[\'"]')
            for match in apply_pattern.finditer(content):
                plugin_id = match.group(1)
                line_number = content[:match.start()].count('\n') + 1
                
                plugin_import = ExtractedImport(
                    import_type="gradle_plugin",
                    start_line=line_number,
                    end_line=line_number,
                    module_path=plugin_id
                )
                result.imports.append(plugin_import)
            return
        
        plugins_content = plugins_match.group(1)
        line_number = content[:plugins_match.start()].count('\n') + 1
        
        for match in self.plugin_line_pattern.finditer(plugins_content):
            plugin_id = match.group(1)
            plugin_version = match.group(2) if match.group(2) else None
            
            plugin_import = ExtractedImport(
                import_type="gradle_plugin",
                start_line=line_number + plugins_content[:match.start()].count('\n'),
                end_line=line_number + plugins_content[:match.end()].count('\n'),
                module_path=plugin_id,
                imported_names=[(plugin_id, plugin_version)] if plugin_version else []
            )
            result.imports.append(plugin_import)
    
    def _parse_android_config(self, content: str, result: ParsedFileResult):
        """Parse Groovy Android configuration."""
        android_match = self.android_pattern.search(content)
        if not android_match:
            return
        
        android_content = android_match.group(1)
        line_number = content[:android_match.start()].count('\n') + 1
        
        # Parse compileSdk, targetSdk, minSdk
        sdk_pattern = re.compile(r'(compileSdk|targetSdk|minSdk)\s+(\d+)')
        for match in sdk_pattern.finditer(android_content):
            config_name = match.group(1)
            config_value = match.group(2)
            
            sdk_variable = ExtractedVariable(
                name=config_name,
                start_line=line_number + android_content[:match.start()].count('\n'),
                end_line=line_number + android_content[:match.end()].count('\n'),
                scope_name="android",
                scope_type="android_config",
                var_type=config_value
            )
            result.global_variables.append(sdk_variable)
        
        # Parse buildTypes
        build_types_pattern = re.compile(r'buildTypes\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', re.DOTALL)
        build_types_match = build_types_pattern.search(android_content)
        if build_types_match:
            build_types_content = build_types_match.group(1)
            build_type_pattern = re.compile(r'(\w+)\s*\{')
            for match in build_type_pattern.finditer(build_types_content):
                build_type = match.group(1)
                
                build_type_class = ExtractedClass(
                    name=f"BuildType_{build_type}",
                    start_line=line_number + android_content[:build_types_match.start()].count('\n') + build_types_content[:match.start()].count('\n'),
                    end_line=line_number + android_content[:build_types_match.start()].count('\n') + build_types_content[:match.end()].count('\n')
                )
                result.classes.append(build_type_class)

class KotlinGradleParser(BaseGradleParser):
    """Parser for Kotlin DSL build.gradle.kts files."""
    
    def __init__(self):
        super().__init__()
        # Kotlin DSL patterns
        self.dependencies_pattern = re.compile(
            r'dependencies\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', 
            re.DOTALL
        )
        self.dependency_line_pattern = re.compile(
            r'\s*(\w+)\s*\(\s*"([^"]+)"\s*\)',
            re.MULTILINE
        )
        self.plugins_pattern = re.compile(
            r'plugins\s*\{([^}]*)\}', 
            re.DOTALL
        )
        self.plugin_line_pattern = re.compile(
            r'id\s*\(\s*"([^"]+)"\s*\)(?:\s*version\s*"([^"]+)")?',
            re.MULTILINE
        )
        self.android_pattern = re.compile(
            r'android\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', 
            re.DOTALL
        )
    
    def _parse_dependencies(self, content: str, result: ParsedFileResult):
        """Parse Kotlin DSL dependencies block."""
        deps_match = self.dependencies_pattern.search(content)
        if not deps_match:
            return
        
        deps_content = deps_match.group(1)
        line_number = content[:deps_match.start()].count('\n') + 1
        
        for match in self.dependency_line_pattern.finditer(deps_content):
            config = match.group(1)  # implementation, api, testImplementation, etc.
            dependency = match.group(2)  # group:artifact:version
            
            dep_variable = ExtractedVariable(
                name=f"dependency_{config}_{dependency}",
                start_line=line_number + deps_content[:match.start()].count('\n'),
                end_line=line_number + deps_content[:match.end()].count('\n'),
                scope_name="dependencies",
                scope_type="gradle_dependency",
                var_type=config
            )
            result.global_variables.append(dep_variable)
    
    def _parse_plugins(self, content: str, result: ParsedFileResult):
        """Parse Kotlin DSL plugins block."""
        plugins_match = self.plugins_pattern.search(content)
        if not plugins_match:
            return
        
        plugins_content = plugins_match.group(1)
        line_number = content[:plugins_match.start()].count('\n') + 1
        
        for match in self.plugin_line_pattern.finditer(plugins_content):
            plugin_id = match.group(1)
            plugin_version = match.group(2) if match.group(2) else None
            
            plugin_import = ExtractedImport(
                import_type="gradle_plugin",
                start_line=line_number + plugins_content[:match.start()].count('\n'),
                end_line=line_number + plugins_content[:match.end()].count('\n'),
                module_path=plugin_id,
                imported_names=[(plugin_id, plugin_version)] if plugin_version else []
            )
            result.imports.append(plugin_import)
    
    def _parse_android_config(self, content: str, result: ParsedFileResult):
        """Parse Kotlin DSL Android configuration."""
        android_match = self.android_pattern.search(content)
        if not android_match:
            return
        
        android_content = android_match.group(1)
        line_number = content[:android_match.start()].count('\n') + 1
        
        # Parse compileSdk, targetSdk, minSdk
        sdk_pattern = re.compile(r'(compileSdk|targetSdk|minSdk)\s*=\s*(\d+)')
        for match in sdk_pattern.finditer(android_content):
            config_name = match.group(1)
            config_value = match.group(2)
            
            sdk_variable = ExtractedVariable(
                name=config_name,
                start_line=line_number + android_content[:match.start()].count('\n'),
                end_line=line_number + android_content[:match.end()].count('\n'),
                scope_name="android",
                scope_type="android_config",
                var_type=config_value
            )
            result.global_variables.append(sdk_variable)
        
        # Parse buildTypes
        build_types_pattern = re.compile(r'buildTypes\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', re.DOTALL)
        build_types_match = build_types_pattern.search(android_content)
        if build_types_match:
            build_types_content = build_types_match.group(1)
            # In Kotlin DSL, build types are accessed by property name
            build_type_pattern = re.compile(r'getByName\s*\(\s*"(\w+)"\s*\)|create\s*\(\s*"(\w+)"\s*\)|(\w+)\s*\{')
            for match in build_type_pattern.finditer(build_types_content):
                build_type = match.group(1) or match.group(2) or match.group(3)
                
                if build_type:
                    build_type_class = ExtractedClass(
                        name=f"BuildType_{build_type}",
                        start_line=line_number + android_content[:build_types_match.start()].count('\n') + build_types_content[:match.start()].count('\n'),
                        end_line=line_number + android_content[:build_types_match.start()].count('\n') + build_types_content[:match.end()].count('\n')
                    )
                    result.classes.append(build_type_class)

def get_gradle_parser(file_path: str = "build.gradle") -> Optional[BaseGradleParser]:
    """Factory function to get appropriate Gradle parser based on file extension."""
    try:
        if file_path.endswith('.kts'):
            return KotlinGradleParser()
        else:
            return GroovyGradleParser()
    except Exception as e:
        logger.error(f"Error creating Gradle parser for {file_path}: {e}")
        return None

# For backward compatibility
class GradleParser(GroovyGradleParser):
    """Alias for GroovyGradleParser for backward compatibility."""
    pass 