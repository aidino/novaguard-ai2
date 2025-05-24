import logging
import re
from typing import List, Dict, Any, Optional, Set, Tuple

from .parsers import ParsedFileResult, ExtractedVariable, ExtractedImport

logger = logging.getLogger(__name__)

class GradleDependency:
    """Represents a Gradle dependency."""
    def __init__(self, configuration: str, group: str, name: str, version: Optional[str] = None, 
                 classifier: Optional[str] = None, ext: Optional[str] = None):
        self.configuration = configuration  # implementation, api, testImplementation, etc.
        self.group = group
        self.name = name
        self.version = version
        self.classifier = classifier
        self.ext = ext

    def __str__(self):
        return f"{self.group}:{self.name}:{self.version or '?'}"

class GradlePlugin:
    """Represents a Gradle plugin."""
    def __init__(self, plugin_id: str, version: Optional[str] = None, apply: bool = True):
        self.plugin_id = plugin_id
        self.version = version
        self.apply = apply

class GradleParser:
    """Parser for Gradle build files (build.gradle and build.gradle.kts)."""

    # Common dependency configurations
    DEPENDENCY_CONFIGURATIONS = {
        'implementation', 'api', 'compileOnly', 'runtimeOnly',
        'testImplementation', 'testCompileOnly', 'testRuntimeOnly',
        'androidTestImplementation', 'androidTestCompileOnly', 'androidTestRuntimeOnly',
        'debugImplementation', 'releaseImplementation',
        'kapt', 'kaptTest', 'kaptAndroidTest',
        'annotationProcessor', 'testAnnotationProcessor'
    }

    def __init__(self, is_kotlin_dsl: bool = False):
        self.is_kotlin_dsl = is_kotlin_dsl

    def parse(self, content: str, file_path: str) -> Optional[ParsedFileResult]:
        """Parse Gradle build file content."""
        try:
            language = "gradle_kotlin" if self.is_kotlin_dsl else "gradle"
            result = ParsedFileResult(file_path=file_path, language=language)
            
            self._extract_plugins(content, result)
            self._extract_dependencies(content, result)
            self._extract_android_config(content, result)
            self._extract_build_config(content, result)
            
            return result
            
        except Exception as e:
            logger.error(f"GradleParser: Error parsing {file_path}: {e}")
            return None

    def _extract_plugins(self, content: str, result: ParsedFileResult):
        """Extract plugin declarations."""
        # Pattern for plugins block (new syntax)
        plugins_block_pattern = r'plugins\s*\{([^}]+)\}'
        plugins_matches = re.findall(plugins_block_pattern, content, re.DOTALL)
        
        for plugins_block in plugins_matches:
            # Extract individual plugin declarations
            if self.is_kotlin_dsl:
                # Kotlin DSL: id("plugin.id") version "version"
                plugin_patterns = [
                    r'id\s*\(\s*["\']([^"\']+)["\']\s*\)\s*version\s*["\']([^"\']+)["\']',
                    r'id\s*\(\s*["\']([^"\']+)["\']\s*\)',
                    r'kotlin\s*\(\s*["\']([^"\']+)["\']\s*\)'
                ]
            else:
                # Groovy DSL: id 'plugin.id' version 'version'
                plugin_patterns = [
                    r'id\s+["\']([^"\']+)["\']\s+version\s+["\']([^"\']+)["\']',
                    r'id\s+["\']([^"\']+)["\']'
                ]
            
            for pattern in plugin_patterns:
                matches = re.findall(pattern, plugins_block)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        plugin_id, version = match[0], match[1]
                    else:
                        plugin_id = match if isinstance(match, str) else match[0]
                        version = None
                    
                    result.imports.append(ExtractedImport(
                        import_type="plugin",
                        start_line=1,
                        end_line=1,
                        module_path=plugin_id,
                        imported_names=[(plugin_id, version)]
                    ))

        # Pattern for legacy apply plugin syntax
        legacy_plugin_pattern = r'apply\s+plugin:\s*["\']([^"\']+)["\']'
        legacy_matches = re.findall(legacy_plugin_pattern, content)
        for plugin_id in legacy_matches:
            result.imports.append(ExtractedImport(
                import_type="plugin",
                start_line=1,
                end_line=1,
                module_path=plugin_id,
                imported_names=[(plugin_id, None)]
            ))

    def _extract_dependencies(self, content: str, result: ParsedFileResult):
        """Extract dependency declarations."""
        # Pattern for dependencies block
        dependencies_pattern = r'dependencies\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        dependencies_matches = re.findall(dependencies_pattern, content, re.DOTALL)
        
        for deps_block in dependencies_matches:
            self._parse_dependencies_block(deps_block, result)

    def _parse_dependencies_block(self, deps_block: str, result: ParsedFileResult):
        """Parse individual dependencies from dependencies block."""
        if self.is_kotlin_dsl:
            # Kotlin DSL patterns
            patterns = [
                # implementation("group:name:version")
                r'(\w+)\s*\(\s*["\']([^:]+):([^:]+):([^"\']+)["\']\s*\)',
                # implementation("group:name:version:classifier@ext")
                r'(\w+)\s*\(\s*["\']([^:]+):([^:]+):([^:@]+)(?::([^@]+))?(?:@([^"\']+))?["\']\s*\)',
                # implementation(project(":module"))
                r'(\w+)\s*\(\s*project\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)',
                # implementation(files("path/to/jar"))
                r'(\w+)\s*\(\s*files\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)',
            ]
        else:
            # Groovy DSL patterns
            patterns = [
                # implementation 'group:name:version'
                r'(\w+)\s+["\']([^:]+):([^:]+):([^"\']+)["\']',
                # implementation 'group:name:version:classifier@ext'
                r'(\w+)\s+["\']([^:]+):([^:]+):([^:@]+)(?::([^@]+))?(?:@([^"\']+))?["\']',
                # implementation project(':module')
                r'(\w+)\s+project\s*\(\s*["\']([^"\']+)["\']\s*\)',
                # implementation files('path/to/jar')
                r'(\w+)\s+files\s*\(\s*["\']([^"\']+)["\']\s*\)',
            ]
        
        for pattern in patterns:
            matches = re.findall(pattern, deps_block)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    config = match[0]
                    if config in self.DEPENDENCY_CONFIGURATIONS:
                        self._add_dependency_from_match(match, result)

    def _add_dependency_from_match(self, match: Tuple, result: ParsedFileResult):
        """Add dependency from regex match."""
        config = match[0]
        
        if len(match) >= 4 and match[1] and match[2] and match[3]:
            # Standard dependency: group:name:version
            group, name, version = match[1], match[2], match[3]
            classifier = match[4] if len(match) > 4 else None
            ext = match[5] if len(match) > 5 else None
            
            dependency_str = f"{group}:{name}:{version}"
            if classifier:
                dependency_str += f":{classifier}"
            if ext:
                dependency_str += f"@{ext}"
                
            result.global_variables.append(ExtractedVariable(
                name=config,
                start_line=1,
                end_line=1,
                scope_name="dependencies",
                scope_type="gradle_dependency",
                var_type=dependency_str
            ))
        elif len(match) >= 2:
            # Project dependency or file dependency
            dependency_value = match[1]
            result.global_variables.append(ExtractedVariable(
                name=config,
                start_line=1,
                end_line=1,
                scope_name="dependencies",
                scope_type="gradle_dependency",
                var_type=dependency_value
            ))

    def _extract_android_config(self, content: str, result: ParsedFileResult):
        """Extract Android-specific configuration."""
        android_pattern = r'android\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        android_matches = re.findall(android_pattern, content, re.DOTALL)
        
        for android_block in android_matches:
            # Extract compileSdk
            compile_sdk_pattern = r'compileSdk\s*[=:]?\s*(\d+)'
            compile_sdk_match = re.search(compile_sdk_pattern, android_block)
            if compile_sdk_match:
                result.global_variables.append(ExtractedVariable(
                    name="compile_sdk_version",
                    start_line=1,
                    end_line=1,
                    scope_name="android",
                    scope_type="android_config",
                    var_type=compile_sdk_match.group(1)
                ))

            # Extract defaultConfig
            self._extract_default_config(android_block, result)
            
            # Extract buildTypes
            self._extract_build_types(android_block, result)
            
            # Extract productFlavors
            self._extract_product_flavors(android_block, result)

    def _extract_default_config(self, android_block: str, result: ParsedFileResult):
        """Extract defaultConfig from android block."""
        default_config_pattern = r'defaultConfig\s*\{([^}]+)\}'
        config_match = re.search(default_config_pattern, android_block, re.DOTALL)
        
        if config_match:
            config_block = config_match.group(1)
            
            # Extract various config values
            config_patterns = {
                'applicationId': r'applicationId\s*[=:]?\s*["\']([^"\']+)["\']',
                'minSdk': r'minSdk\s*[=:]?\s*(\d+)',
                'targetSdk': r'targetSdk\s*[=:]?\s*(\d+)',
                'versionCode': r'versionCode\s*[=:]?\s*(\d+)',
                'versionName': r'versionName\s*[=:]?\s*["\']([^"\']+)["\']',
                'testInstrumentationRunner': r'testInstrumentationRunner\s*[=:]?\s*["\']([^"\']+)["\']'
            }
            
            for config_name, pattern in config_patterns.items():
                match = re.search(pattern, config_block)
                if match:
                    result.global_variables.append(ExtractedVariable(
                        name=config_name,
                        start_line=1,
                        end_line=1,
                        scope_name="defaultConfig",
                        scope_type="android_config",
                        var_type=match.group(1)
                    ))

    def _extract_build_types(self, android_block: str, result: ParsedFileResult):
        """Extract buildTypes from android block."""
        build_types_pattern = r'buildTypes\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        build_types_match = re.search(build_types_pattern, android_block, re.DOTALL)
        
        if build_types_match:
            build_types_block = build_types_match.group(1)
            
            # Extract individual build types
            build_type_pattern = r'(\w+)\s*\{([^}]+)\}'
            for build_type_match in re.finditer(build_type_pattern, build_types_block):
                build_type_name = build_type_match.group(1)
                build_type_config = build_type_match.group(2)
                
                result.global_variables.append(ExtractedVariable(
                    name="build_type",
                    start_line=1,
                    end_line=1,
                    scope_name="buildTypes",
                    scope_type="android_config",
                    var_type=build_type_name
                ))

    def _extract_product_flavors(self, android_block: str, result: ParsedFileResult):
        """Extract productFlavors from android block."""
        flavors_pattern = r'productFlavors\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        flavors_match = re.search(flavors_pattern, android_block, re.DOTALL)
        
        if flavors_match:
            flavors_block = flavors_match.group(1)
            
            # Extract individual flavors
            flavor_pattern = r'(\w+)\s*\{([^}]+)\}'
            for flavor_match in re.finditer(flavor_pattern, flavors_block):
                flavor_name = flavor_match.group(1)
                
                result.global_variables.append(ExtractedVariable(
                    name="product_flavor",
                    start_line=1,
                    end_line=1,
                    scope_name="productFlavors",
                    scope_type="android_config",
                    var_type=flavor_name
                ))

    def _extract_build_config(self, content: str, result: ParsedFileResult):
        """Extract general build configuration."""
        # Extract Kotlin version
        kotlin_version_pattern = r'kotlin_version\s*[=:]\s*["\']([^"\']+)["\']'
        kotlin_match = re.search(kotlin_version_pattern, content)
        if kotlin_match:
            result.global_variables.append(ExtractedVariable(
                name="kotlin_version",
                start_line=1,
                end_line=1,
                scope_name="build",
                scope_type="build_config",
                var_type=kotlin_match.group(1)
            ))

        # Extract Gradle version from wrapper
        gradle_version_pattern = r'gradle-(\d+\.\d+(?:\.\d+)?)-'
        gradle_match = re.search(gradle_version_pattern, content)
        if gradle_match:
            result.global_variables.append(ExtractedVariable(
                name="gradle_version",
                start_line=1,
                end_line=1,
                scope_name="build",
                scope_type="build_config",
                var_type=gradle_match.group(1)
            ))

        logger.info(f"GradleParser: Extracted {len([v for v in result.global_variables if v.scope_type == 'gradle_dependency'])} dependencies, "
                   f"{len(result.imports)} plugins from {result.file_path}")

def create_gradle_parser(file_path: str) -> GradleParser:
    """Factory function to create appropriate Gradle parser based on file extension."""
    is_kotlin_dsl = file_path.endswith('.kts')
    return GradleParser(is_kotlin_dsl=is_kotlin_dsl) 