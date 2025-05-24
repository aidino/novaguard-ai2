import logging
from typing import Optional, List, Dict, Any
import xml.etree.ElementTree as ET

# Import shared base classes
from .base_classes import (
    ParsedFileResult,
    ExtractedFunction,
    ExtractedClass,
    ExtractedImport,
    ExtractedVariable
)

logger = logging.getLogger(__name__)

class AndroidManifestParser:
    """Parser for AndroidManifest.xml files."""
    
    def __init__(self):
        self.android_namespace = "{http://schemas.android.com/apk/res/android}"
    
    def parse(self, content: str, file_path: str) -> Optional[ParsedFileResult]:
        """Parse AndroidManifest.xml content."""
        try:
            result = ParsedFileResult(file_path=file_path, language="xml")
            
            # Parse XML
            root = ET.fromstring(content)
            
            # Parse package name
            self._parse_package_info(root, result)
            
            # Parse permissions
            self._parse_permissions(root, result)
            
            # Parse application components
            self._parse_application_components(root, result)
            
            # Parse SDK versions
            self._parse_sdk_versions(root, result)
            
            return result
        except Exception as e:
            logger.error(f"Error parsing AndroidManifest.xml {file_path}: {e}")
            return None
    
    def _parse_package_info(self, root: ET.Element, result: ParsedFileResult):
        """Parse package information from manifest."""
        package_name = root.get("package")
        if package_name:
            package_import = ExtractedImport(
                import_type="android_package",
                start_line=1,
                end_line=1,
                module_path=package_name
            )
            result.imports.append(package_import)
    
    def _parse_permissions(self, root: ET.Element, result: ParsedFileResult):
        """Parse permission declarations and uses."""
        line_number = 2  # Start after manifest tag
        
        # Parse uses-permission
        for permission_elem in root.findall("uses-permission"):
            permission_name = permission_elem.get(f"{self.android_namespace}name")
            if permission_name:
                permission_var = ExtractedVariable(
                    name=permission_name,
                    start_line=line_number,
                    end_line=line_number,
                    scope_name="manifest",
                    scope_type="uses_permission",
                    var_type="permission"
                )
                result.global_variables.append(permission_var)
                line_number += 1
        
        # Parse permission declarations
        for permission_elem in root.findall("permission"):
            permission_name = permission_elem.get(f"{self.android_namespace}name")
            permission_level = permission_elem.get(f"{self.android_namespace}protectionLevel")
            if permission_name:
                permission_var = ExtractedVariable(
                    name=permission_name,
                    start_line=line_number,
                    end_line=line_number,
                    scope_name="manifest",
                    scope_type="permission_declaration",
                    var_type=permission_level or "normal"
                )
                result.global_variables.append(permission_var)
                line_number += 1
    
    def _parse_application_components(self, root: ET.Element, result: ParsedFileResult):
        """Parse Android application components."""
        application = root.find("application")
        if not application:
            return
        
        line_number = 10  # Approximate line number
        
        # Parse activities
        for activity in application.findall("activity"):
            self._parse_component(activity, "Activity", result, line_number)
            line_number += 5
        
        # Parse services
        for service in application.findall("service"):
            self._parse_component(service, "Service", result, line_number)
            line_number += 5
        
        # Parse receivers
        for receiver in application.findall("receiver"):
            self._parse_component(receiver, "BroadcastReceiver", result, line_number)
            line_number += 5
        
        # Parse providers
        for provider in application.findall("provider"):
            self._parse_component(provider, "ContentProvider", result, line_number)
            line_number += 5
    
    def _parse_component(self, component_elem: ET.Element, component_type: str, result: ParsedFileResult, line_number: int):
        """Parse individual Android component."""
        component_name = component_elem.get(f"{self.android_namespace}name")
        if not component_name:
            return
        
        # Create class for the component
        component_class = ExtractedClass(
            name=f"{component_type}_{component_name.split('.')[-1]}",
            start_line=line_number,
            end_line=line_number + 3
        )
        
        # Add component type as decorator
        component_class.decorators.append(component_type)
        
        # Parse exported attribute
        exported = component_elem.get(f"{self.android_namespace}exported")
        if exported:
            component_class.decorators.append(f"exported={exported}")
        
        # Parse enabled attribute
        enabled = component_elem.get(f"{self.android_namespace}enabled")
        if enabled:
            component_class.decorators.append(f"enabled={enabled}")
        
        result.classes.append(component_class)
        
        # Parse intent filters
        self._parse_intent_filters(component_elem, component_class, result, line_number + 1)
    
    def _parse_intent_filters(self, component_elem: ET.Element, component_class: ExtractedClass, result: ParsedFileResult, line_number: int):
        """Parse intent filters for a component."""
        for intent_filter in component_elem.findall("intent-filter"):
            filter_line = line_number
            
            # Parse actions
            for action in intent_filter.findall("action"):
                action_name = action.get(f"{self.android_namespace}name")
                if action_name:
                    action_method = ExtractedFunction(
                        name=f"handle_{action_name.split('.')[-1]}",
                        start_line=filter_line,
                        end_line=filter_line,
                        class_name=component_class.name
                    )
                    action_method.decorators.append(f"action={action_name}")
                    result.functions.append(action_method)
                    filter_line += 1
            
            # Parse categories
            for category in intent_filter.findall("category"):
                category_name = category.get(f"{self.android_namespace}name")
                if category_name:
                    component_class.decorators.append(f"category={category_name}")
            
            # Parse data elements
            for data in intent_filter.findall("data"):
                scheme = data.get(f"{self.android_namespace}scheme")
                host = data.get(f"{self.android_namespace}host")
                mime_type = data.get(f"{self.android_namespace}mimeType")
                
                if scheme:
                    component_class.decorators.append(f"scheme={scheme}")
                if host:
                    component_class.decorators.append(f"host={host}")
                if mime_type:
                    component_class.decorators.append(f"mimeType={mime_type}")
    
    def _parse_sdk_versions(self, root: ET.Element, result: ParsedFileResult):
        """Parse SDK version information."""
        uses_sdk = root.find("uses-sdk")
        if not uses_sdk:
            return
        
        # Parse minSdkVersion
        min_sdk = uses_sdk.get(f"{self.android_namespace}minSdkVersion")
        if min_sdk:
            min_sdk_var = ExtractedVariable(
                name="minSdkVersion",
                start_line=5,  # Approximate
                end_line=5,
                scope_name="uses-sdk",
                scope_type="sdk_version",
                var_type=min_sdk
            )
            result.global_variables.append(min_sdk_var)
        
        # Parse targetSdkVersion
        target_sdk = uses_sdk.get(f"{self.android_namespace}targetSdkVersion")
        if target_sdk:
            target_sdk_var = ExtractedVariable(
                name="targetSdkVersion",
                start_line=6,  # Approximate
                end_line=6,
                scope_name="uses-sdk",
                scope_type="sdk_version",
                var_type=target_sdk
            )
            result.global_variables.append(target_sdk_var)
        
        # Parse maxSdkVersion (if present)
        max_sdk = uses_sdk.get(f"{self.android_namespace}maxSdkVersion")
        if max_sdk:
            max_sdk_var = ExtractedVariable(
                name="maxSdkVersion",
                start_line=7,  # Approximate
                end_line=7,
                scope_name="uses-sdk",
                scope_type="sdk_version",
                var_type=max_sdk
            )
            result.global_variables.append(max_sdk_var) 