import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Set

from .parsers import ParsedFileResult, ExtractedClass, ExtractedVariable

logger = logging.getLogger(__name__)

class AndroidComponent:
    """Represents an Android component (Activity, Service, etc.)."""
    def __init__(self, component_type: str, name: str, exported: bool = False, 
                 intent_filters: Optional[List[Dict]] = None, permissions: Optional[List[str]] = None):
        self.component_type = component_type  # activity, service, receiver, provider
        self.name = name
        self.exported = exported
        self.intent_filters = intent_filters or []
        self.permissions = permissions or []
        self.metadata = {}

class AndroidPermission:
    """Represents an Android permission."""
    def __init__(self, name: str, permission_type: str = "uses", protection_level: Optional[str] = None):
        self.name = name
        self.permission_type = permission_type  # "uses" or "declares"
        self.protection_level = protection_level

class AndroidManifestParser:
    """Parser for AndroidManifest.xml files."""

    def __init__(self):
        self.namespace = "{http://schemas.android.com/apk/res/android}"

    def parse(self, content: str, file_path: str) -> Optional[ParsedFileResult]:
        """Parse AndroidManifest.xml content."""
        try:
            root = ET.fromstring(content)
            result = ParsedFileResult(file_path=file_path, language="android_manifest")
            
            self._extract_manifest_info(root, result)
            return result
            
        except ET.ParseError as e:
            logger.error(f"AndroidManifestParser: XML parsing error in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"AndroidManifestParser: Error parsing {file_path}: {e}")
            return None

    def _get_attribute(self, element: ET.Element, attr_name: str) -> Optional[str]:
        """Get Android namespace attribute value."""
        return element.get(f"{self.namespace}{attr_name}")

    def _extract_manifest_info(self, root: ET.Element, result: ParsedFileResult):
        """Extract information from manifest root."""
        # Extract package name
        package_name = root.get("package")
        if package_name:
            result.global_variables.append(ExtractedVariable(
                name="package",
                start_line=1,
                end_line=1,
                scope_name="manifest",
                scope_type="manifest_attribute",
                var_type=package_name
            ))

        # Extract application element
        application = root.find("application")
        if application:
            self._extract_application_info(application, result)

        # Extract permissions
        self._extract_permissions(root, result)

        # Extract SDK versions
        self._extract_sdk_info(root, result)

    def _extract_application_info(self, application: ET.Element, result: ParsedFileResult):
        """Extract application-level information."""
        app_name = self._get_attribute(application, "name")
        if app_name:
            result.global_variables.append(ExtractedVariable(
                name="application_name",
                start_line=1,
                end_line=1,
                scope_name="application",
                scope_type="application_attribute",
                var_type=app_name
            ))

        # Extract components
        self._extract_activities(application, result)
        self._extract_services(application, result)
        self._extract_receivers(application, result)
        self._extract_providers(application, result)

    def _extract_activities(self, application: ET.Element, result: ParsedFileResult):
        """Extract activity declarations."""
        activities = application.findall("activity")
        for activity in activities:
            component = self._parse_component(activity, "activity")
            if component:
                # Create a class-like representation for the activity
                activity_class = ExtractedClass(
                    name=component.name,
                    start_line=1,
                    end_line=1
                )
                activity_class.decorators.append("@AndroidActivity")
                if component.exported:
                    activity_class.decorators.append("@Exported")
                
                # Add intent filters as attributes
                for intent_filter in component.intent_filters:
                    actions = intent_filter.get("actions", [])
                    categories = intent_filter.get("categories", [])
                    if actions:
                        activity_class.attributes.append(ExtractedVariable(
                            name="intent_actions",
                            start_line=1,
                            end_line=1,
                            scope_name=component.name,
                            scope_type="intent_filter",
                            var_type=",".join(actions)
                        ))
                
                result.classes.append(activity_class)

    def _extract_services(self, application: ET.Element, result: ParsedFileResult):
        """Extract service declarations."""
        services = application.findall("service")
        for service in services:
            component = self._parse_component(service, "service")
            if component:
                service_class = ExtractedClass(
                    name=component.name,
                    start_line=1,
                    end_line=1
                )
                service_class.decorators.append("@AndroidService")
                if component.exported:
                    service_class.decorators.append("@Exported")
                
                result.classes.append(service_class)

    def _extract_receivers(self, application: ET.Element, result: ParsedFileResult):
        """Extract broadcast receiver declarations."""
        receivers = application.findall("receiver")
        for receiver in receivers:
            component = self._parse_component(receiver, "receiver")
            if component:
                receiver_class = ExtractedClass(
                    name=component.name,
                    start_line=1,
                    end_line=1
                )
                receiver_class.decorators.append("@AndroidReceiver")
                if component.exported:
                    receiver_class.decorators.append("@Exported")
                
                result.classes.append(receiver_class)

    def _extract_providers(self, application: ET.Element, result: ParsedFileResult):
        """Extract content provider declarations."""
        providers = application.findall("provider")
        for provider in providers:
            component = self._parse_component(provider, "provider")
            if component:
                provider_class = ExtractedClass(
                    name=component.name,
                    start_line=1,
                    end_line=1
                )
                provider_class.decorators.append("@AndroidProvider")
                if component.exported:
                    provider_class.decorators.append("@Exported")
                
                # Add authorities as attributes
                authorities = self._get_attribute(provider, "authorities")
                if authorities:
                    provider_class.attributes.append(ExtractedVariable(
                        name="authorities",
                        start_line=1,
                        end_line=1,
                        scope_name=component.name,
                        scope_type="provider_attribute",
                        var_type=authorities
                    ))
                
                result.classes.append(provider_class)

    def _parse_component(self, element: ET.Element, component_type: str) -> Optional[AndroidComponent]:
        """Parse a generic Android component."""
        name = self._get_attribute(element, "name")
        if not name:
            return None

        # Resolve relative names
        if name.startswith("."):
            # Relative to package - would need package name from manifest
            pass
        elif not "." in name:
            # Simple name - relative to package
            pass

        exported = self._get_attribute(element, "exported")
        is_exported = exported == "true" if exported else False

        # Extract intent filters
        intent_filters = []
        for intent_filter in element.findall("intent-filter"):
            filter_info = self._parse_intent_filter(intent_filter)
            if filter_info:
                intent_filters.append(filter_info)

        return AndroidComponent(
            component_type=component_type,
            name=name,
            exported=is_exported,
            intent_filters=intent_filters
        )

    def _parse_intent_filter(self, intent_filter: ET.Element) -> Dict:
        """Parse intent filter information."""
        actions = []
        categories = []
        data_schemes = []

        for action in intent_filter.findall("action"):
            action_name = self._get_attribute(action, "name")
            if action_name:
                actions.append(action_name)

        for category in intent_filter.findall("category"):
            category_name = self._get_attribute(category, "name")
            if category_name:
                categories.append(category_name)

        for data in intent_filter.findall("data"):
            scheme = self._get_attribute(data, "scheme")
            if scheme:
                data_schemes.append(scheme)

        return {
            "actions": actions,
            "categories": categories,
            "data_schemes": data_schemes
        }

    def _extract_permissions(self, root: ET.Element, result: ParsedFileResult):
        """Extract permission declarations and uses."""
        # Extract uses-permission
        for uses_permission in root.findall("uses-permission"):
            permission_name = self._get_attribute(uses_permission, "name")
            if permission_name:
                result.global_variables.append(ExtractedVariable(
                    name="uses_permission",
                    start_line=1,
                    end_line=1,
                    scope_name="manifest",
                    scope_type="permission",
                    var_type=permission_name
                ))

        # Extract permission declarations
        for permission in root.findall("permission"):
            permission_name = self._get_attribute(permission, "name")
            protection_level = self._get_attribute(permission, "protectionLevel")
            if permission_name:
                result.global_variables.append(ExtractedVariable(
                    name="declares_permission",
                    start_line=1,
                    end_line=1,
                    scope_name="manifest",
                    scope_type="permission_declaration",
                    var_type=f"{permission_name}:{protection_level or 'normal'}"
                ))

    def _extract_sdk_info(self, root: ET.Element, result: ParsedFileResult):
        """Extract SDK version information."""
        uses_sdk = root.find("uses-sdk")
        if uses_sdk:
            min_sdk = self._get_attribute(uses_sdk, "minSdkVersion")
            target_sdk = self._get_attribute(uses_sdk, "targetSdkVersion")
            max_sdk = self._get_attribute(uses_sdk, "maxSdkVersion")

            if min_sdk:
                result.global_variables.append(ExtractedVariable(
                    name="min_sdk_version",
                    start_line=1,
                    end_line=1,
                    scope_name="manifest",
                    scope_type="sdk_version",
                    var_type=min_sdk
                ))

            if target_sdk:
                result.global_variables.append(ExtractedVariable(
                    name="target_sdk_version",
                    start_line=1,
                    end_line=1,
                    scope_name="manifest",
                    scope_type="sdk_version",
                    var_type=target_sdk
                ))

            if max_sdk:
                result.global_variables.append(ExtractedVariable(
                    name="max_sdk_version",
                    start_line=1,
                    end_line=1,
                    scope_name="manifest",
                    scope_type="sdk_version",
                    var_type=max_sdk
                ))

        logger.info(f"AndroidManifestParser: Extracted {len(result.classes)} components, "
                   f"{len([v for v in result.global_variables if v.scope_type == 'permission'])} permissions from {result.file_path}") 