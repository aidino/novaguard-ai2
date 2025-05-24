# novaguard-backend/app/project_service/android_detector.py
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class AndroidModuleInfo:
    """Information about an Android module."""
    def __init__(self, name: str, path: str, module_type: str = "app"):
        self.name = name
        self.path = path
        self.module_type = module_type  # app, library, feature, etc.
        self.has_kotlin = False
        self.kotlin_percentage = 0.0
        self.source_sets = []
        self.build_variants = []
        self.dependencies = []
        self.target_sdk = None
        self.min_sdk = None
        self.compile_sdk = None

class AndroidProjectStructure:
    """Represents the structure of an Android project."""
    def __init__(self, root_path: str):
        self.root_path = root_path
        self.project_name = os.path.basename(root_path)
        self.is_android_project = False
        self.is_multi_module = False
        self.modules = {}
        self.gradle_version = None
        self.kotlin_version = None
        self.android_gradle_plugin_version = None
        self.overall_kotlin_percentage = 0.0
        self.package_name = None
        self.min_sdk_version = None
        self.target_sdk_version = None
        self.compile_sdk_version = None

def detect_android_project(project_path: str) -> Tuple[bool, Optional[AndroidProjectStructure]]:
    """
    Detect if a project is an Android project and analyze its structure.
    
    Args:
        project_path: Path to the project root
        
    Returns:
        Tuple of (is_android_project, project_structure)
    """
    project_path = Path(project_path)
    
    if not project_path.exists() or not project_path.is_dir():
        logger.warning(f"Project path does not exist or is not a directory: {project_path}")
        return False, None
    
    structure = AndroidProjectStructure(str(project_path))
    
    # Check for Android project indicators
    android_indicators = _check_android_indicators(project_path)
    
    if not android_indicators['has_gradle'] and not android_indicators['has_manifest']:
        return False, None
    
    structure.is_android_project = True
    
    # Analyze project structure
    _analyze_gradle_structure(project_path, structure)
    _analyze_modules(project_path, structure)
    _analyze_kotlin_usage(project_path, structure)
    _extract_project_metadata(project_path, structure)
    
    logger.info(f"Detected Android project: {structure.project_name}")
    logger.info(f"  - Multi-module: {structure.is_multi_module}")
    logger.info(f"  - Modules: {len(structure.modules)}")
    logger.info(f"  - Kotlin usage: {structure.overall_kotlin_percentage:.1f}%")
    logger.info(f"  - Target SDK: {structure.target_sdk_version}")
    
    return True, structure

def _check_android_indicators(project_path: Path) -> Dict[str, bool]:
    """Check for Android project indicators."""
    indicators = {
        'has_gradle': False,
        'has_manifest': False,
        'has_android_gradle_plugin': False,
        'has_app_module': False
    }
    
    # Check for Gradle files
    gradle_files = [
        'build.gradle',
        'build.gradle.kts',
        'settings.gradle',
        'settings.gradle.kts',
        'gradlew',
        'gradlew.bat'
    ]
    
    for gradle_file in gradle_files:
        if (project_path / gradle_file).exists():
            indicators['has_gradle'] = True
            break
    
    # Check for AndroidManifest.xml
    manifest_locations = [
        'app/src/main/AndroidManifest.xml',
        'src/main/AndroidManifest.xml',
        'AndroidManifest.xml'
    ]
    
    for manifest_path in manifest_locations:
        if (project_path / manifest_path).exists():
            indicators['has_manifest'] = True
            break
    
    # Check for Android Gradle Plugin in build files
    build_files = ['build.gradle', 'build.gradle.kts', 'app/build.gradle', 'app/build.gradle.kts']
    for build_file in build_files:
        build_path = project_path / build_file
        if build_path.exists():
            try:
                content = build_path.read_text(encoding='utf-8')
                if any(plugin in content for plugin in [
                    'com.android.application',
                    'com.android.library',
                    'android-library',
                    'android'
                ]):
                    indicators['has_android_gradle_plugin'] = True
                    break
            except Exception as e:
                logger.warning(f"Could not read build file {build_path}: {e}")
    
    # Check for app module
    if (project_path / 'app').exists() and (project_path / 'app').is_dir():
        indicators['has_app_module'] = True
    
    return indicators

def _analyze_gradle_structure(project_path: Path, structure: AndroidProjectStructure):
    """Analyze Gradle structure and extract version information."""
    # Check settings.gradle for multi-module setup
    settings_files = ['settings.gradle', 'settings.gradle.kts']
    for settings_file in settings_files:
        settings_path = project_path / settings_file
        if settings_path.exists():
            try:
                content = settings_path.read_text(encoding='utf-8')
                # Count include statements to determine if multi-module
                include_count = content.count('include')
                if include_count > 1:  # More than just app module
                    structure.is_multi_module = True
                
                # Extract module names
                import re
                include_pattern = r'include\s*["\']([^"\']+)["\']'
                modules = re.findall(include_pattern, content)
                for module in modules:
                    module_name = module.replace(':', '').strip()
                    module_path = str(project_path / module_name)
                    if os.path.exists(module_path):
                        structure.modules[module_name] = AndroidModuleInfo(module_name, module_path)
                        
            except Exception as e:
                logger.warning(f"Could not parse settings file {settings_path}: {e}")
            break
    
    # Extract Gradle wrapper version
    gradle_wrapper_props = project_path / 'gradle' / 'wrapper' / 'gradle-wrapper.properties'
    if gradle_wrapper_props.exists():
        try:
            content = gradle_wrapper_props.read_text(encoding='utf-8')
            import re
            version_match = re.search(r'gradle-(\d+\.\d+(?:\.\d+)?)-', content)
            if version_match:
                structure.gradle_version = version_match.group(1)
        except Exception as e:
            logger.warning(f"Could not parse gradle wrapper properties: {e}")

def _analyze_modules(project_path: Path, structure: AndroidProjectStructure):
    """Analyze individual modules in the project."""
    if not structure.modules:
        # Single module project - check app directory
        app_path = project_path / 'app'
        if app_path.exists():
            structure.modules['app'] = AndroidModuleInfo('app', str(app_path), 'app')
        else:
            # Might be a library project in root
            structure.modules['root'] = AndroidModuleInfo('root', str(project_path), 'library')
    
    for module_name, module_info in structure.modules.items():
        _analyze_module_details(Path(module_info.path), module_info, structure)

def _analyze_module_details(module_path: Path, module_info: AndroidModuleInfo, structure: AndroidProjectStructure):
    """Analyze details of a specific module."""
    # Analyze build.gradle file
    build_files = ['build.gradle', 'build.gradle.kts']
    for build_file in build_files:
        build_path = module_path / build_file
        if build_path.exists():
            _analyze_build_gradle(build_path, module_info, structure)
            break
    
    # Analyze source structure
    _analyze_source_structure(module_path, module_info)
    
    # Analyze AndroidManifest.xml
    manifest_path = module_path / 'src' / 'main' / 'AndroidManifest.xml'
    if manifest_path.exists():
        _analyze_manifest(manifest_path, module_info, structure)

def _analyze_build_gradle(build_path: Path, module_info: AndroidModuleInfo, structure: AndroidProjectStructure):
    """Analyze build.gradle file for module information."""
    try:
        content = build_path.read_text(encoding='utf-8')
        
        # Determine module type
        if 'com.android.application' in content:
            module_info.module_type = 'app'
        elif 'com.android.library' in content:
            module_info.module_type = 'library'
        elif 'com.android.feature' in content:
            module_info.module_type = 'feature'
        
        # Extract SDK versions
        import re
        compile_sdk_match = re.search(r'compileSdk\s*[=:]?\s*(\d+)', content)
        if compile_sdk_match:
            module_info.compile_sdk = int(compile_sdk_match.group(1))
            structure.compile_sdk_version = module_info.compile_sdk
        
        # Extract from defaultConfig
        min_sdk_match = re.search(r'minSdk\s*[=:]?\s*(\d+)', content)
        if min_sdk_match:
            module_info.min_sdk = int(min_sdk_match.group(1))
            structure.min_sdk_version = module_info.min_sdk
            
        target_sdk_match = re.search(r'targetSdk\s*[=:]?\s*(\d+)', content)
        if target_sdk_match:
            module_info.target_sdk = int(target_sdk_match.group(1))
            structure.target_sdk_version = module_info.target_sdk
        
        # Extract Kotlin version
        kotlin_version_match = re.search(r'kotlin_version\s*[=:]\s*["\']([^"\']+)["\']', content)
        if kotlin_version_match:
            structure.kotlin_version = kotlin_version_match.group(1)
        
        # Check for Kotlin plugin
        if any(kotlin_indicator in content for kotlin_indicator in [
            'kotlin-android',
            'org.jetbrains.kotlin.android',
            'kotlin("android")'
        ]):
            module_info.has_kotlin = True
        
        # Extract Android Gradle Plugin version (from project level build.gradle)
        agp_match = re.search(r'com\.android\.tools\.build:gradle:([^"\']+)', content)
        if agp_match:
            structure.android_gradle_plugin_version = agp_match.group(1)
            
    except Exception as e:
        logger.warning(f"Could not analyze build.gradle at {build_path}: {e}")

def _analyze_source_structure(module_path: Path, module_info: AndroidModuleInfo):
    """Analyze source code structure and language distribution."""
    src_main_path = module_path / 'src' / 'main'
    if not src_main_path.exists():
        return
    
    # Standard source sets
    source_sets = ['main', 'test', 'androidTest', 'debug', 'release']
    for source_set in source_sets:
        source_set_path = module_path / 'src' / source_set
        if source_set_path.exists():
            module_info.source_sets.append(source_set)
    
    # Count Java and Kotlin files
    java_files = 0
    kotlin_files = 0
    
    java_dir = src_main_path / 'java'
    if java_dir.exists():
        java_files = len(list(java_dir.glob('**/*.java')))
        kotlin_files = len(list(java_dir.glob('**/*.kt')))
    
    kotlin_dir = src_main_path / 'kotlin'
    if kotlin_dir.exists():
        kotlin_files += len(list(kotlin_dir.glob('**/*.kt')))
    
    total_files = java_files + kotlin_files
    if total_files > 0:
        module_info.kotlin_percentage = (kotlin_files / total_files) * 100
        if kotlin_files > 0:
            module_info.has_kotlin = True

def _analyze_manifest(manifest_path: Path, module_info: AndroidModuleInfo, structure: AndroidProjectStructure):
    """Analyze AndroidManifest.xml for project information."""
    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        
        # Extract package name
        package_name = root.get('package')
        if package_name and not structure.package_name:
            structure.package_name = package_name
        
        # Extract uses-sdk information if not already found
        uses_sdk = root.find('uses-sdk')
        if uses_sdk is not None:
            namespace = "{http://schemas.android.com/apk/res/android}"
            
            min_sdk = uses_sdk.get(f"{namespace}minSdkVersion")
            if min_sdk and not structure.min_sdk_version:
                try:
                    structure.min_sdk_version = int(min_sdk)
                    module_info.min_sdk = int(min_sdk)
                except ValueError:
                    pass
            
            target_sdk = uses_sdk.get(f"{namespace}targetSdkVersion")
            if target_sdk and not structure.target_sdk_version:
                try:
                    structure.target_sdk_version = int(target_sdk)
                    module_info.target_sdk = int(target_sdk)
                except ValueError:
                    pass
                    
    except Exception as e:
        logger.warning(f"Could not analyze AndroidManifest.xml at {manifest_path}: {e}")

def _analyze_kotlin_usage(project_path: Path, structure: AndroidProjectStructure):
    """Analyze overall Kotlin usage across the project."""
    total_java = 0
    total_kotlin = 0
    
    for module_info in structure.modules.values():
        module_path = Path(module_info.path)
        src_dirs = [
            module_path / 'src' / 'main' / 'java',
            module_path / 'src' / 'main' / 'kotlin'
        ]
        
        for src_dir in src_dirs:
            if src_dir.exists():
                total_java += len(list(src_dir.glob('**/*.java')))
                total_kotlin += len(list(src_dir.glob('**/*.kt')))
    
    total_files = total_java + total_kotlin
    if total_files > 0:
        structure.overall_kotlin_percentage = (total_kotlin / total_files) * 100

def _extract_project_metadata(project_path: Path, structure: AndroidProjectStructure):
    """Extract additional project metadata."""
    # Try to extract project name from settings.gradle
    settings_files = ['settings.gradle', 'settings.gradle.kts']
    for settings_file in settings_files:
        settings_path = project_path / settings_file
        if settings_path.exists():
            try:
                content = settings_path.read_text(encoding='utf-8')
                import re
                
                # Look for rootProject.name
                name_match = re.search(r'rootProject\.name\s*[=:]\s*["\']([^"\']+)["\']', content)
                if name_match:
                    structure.project_name = name_match.group(1)
                    break
            except Exception as e:
                logger.warning(f"Could not parse settings file for project name: {e}")

def is_android_project_path(project_path: str) -> bool:
    """Quick check if a path contains an Android project."""
    is_android, _ = detect_android_project(project_path)
    return is_android 