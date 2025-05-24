# novaguard-backend/app/ckg_builder/parsers/kotlin_parser.py
import logging
from typing import Optional, Set, List, Tuple, Dict, Any
from tree_sitter import Node, Query

# Import shared base classes
from .base_classes import (
    BaseCodeParser,
    ParsedFileResult,
    ExtractedFunction,
    ExtractedClass,
    ExtractedImport,
    ExtractedVariable
)

logger = logging.getLogger(__name__)

class KotlinParser(BaseCodeParser):
    """Tree-sitter based Kotlin parser."""
    
    QUERY_DEFINITIONS = {
        "imports_query": """
            [
              (import_header) @import_node
            ]
        """,
        "definitions_query": """
            (source_file
              [
                (class_declaration) @class_node
                (object_declaration) @object_node
                (function_declaration) @function_node
                (property_declaration) @property_node
              ]
            )
        """,
        "method_calls_query": """
            (call_expression) @method_call
        """,
        "annotations_query": """
            (annotation) @annotation_node
        """
    }
    
    def __init__(self):
        super().__init__("kotlin")
        self.queries: Dict[str, Query] = {}
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"KotlinParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"KotlinParser: Error compiling query '{query_name}': {e}")
                
    def _get_query(self, query_name: str) -> Optional[Query]:
        return self.queries.get(query_name)
    
    def _parse_annotations(self, node: Node) -> List[str]:
        """Parse annotations from a node."""
        annotations = []
        for child in node.children:
            if child.type == "modifiers":
                for modifier_child in child.children:
                    if modifier_child.type == "annotation":
                        annotation_text = self._get_node_text(modifier_child)
                        if annotation_text:
                            annotations.append(annotation_text)
        return annotations
    
    def _parse_package_declaration(self, root_node: Node, result: ParsedFileResult):
        """Parse package declaration from the root node."""
        for child in root_node.children:
            if child.type == "package_header":
                identifier_node = None
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        identifier_node = grandchild
                        break
                
                if identifier_node:
                    package_name = self._get_node_text(identifier_node)
                    if package_name:
                        package_import = ExtractedImport(
                            import_type="package",
                            start_line=self._get_line_number(child),
                            end_line=self._get_end_line_number(child),
                            module_path=package_name
                        )
                        result.imports.append(package_import)
    
    def _parse_import_node(self, import_node: Node, result: ParsedFileResult):
        """Parse Kotlin import declaration."""
        identifier_node = None
        import_alias_node = None
        
        for child in import_node.children:
            if child.type == "identifier":
                identifier_node = child
            elif child.type == "import_alias":
                import_alias_node = child
        
        if not identifier_node:
            return
            
        import_path = self._get_node_text(identifier_node)
        if not import_path:
            return
            
        # Get alias if present
        alias_name = None
        if import_alias_node:
            for alias_child in import_alias_node.children:
                if alias_child.type == "type_identifier":
                    alias_name = self._get_node_text(alias_child)
                    break
        
        # Check if it's a wildcard import
        is_wildcard = import_path.endswith(".*")
        import_type = "wildcard" if is_wildcard else "regular"
        
        imported_names = []
        if alias_name:
            imported_names.append((alias_name, import_path.split(".")[-1]))
        
        extracted_import = ExtractedImport(
            import_type=import_type,
            start_line=self._get_line_number(import_node),
            end_line=self._get_end_line_number(import_node),
            module_path=import_path,
            imported_names=imported_names
        )
        result.imports.append(extracted_import)
    
    def _parse_function_node(self, function_node: Node, result: ParsedFileResult, class_name: Optional[str] = None):
        """Parse Kotlin function declaration."""
        name_node = None
        for child in function_node.children:
            if child.type == "simple_identifier":
                name_node = child
                break
        
        if not name_node:
            return
            
        function_name = self._get_node_text(name_node)
        if not function_name:
            return
            
        # Get function body
        body_node = function_node.child_by_field_name("body")
        
        # Check if it's a suspend function
        is_suspend = False
        for child in function_node.children:
            if child.type == "modifiers":
                for modifier in child.children:
                    if self._get_node_text(modifier) == "suspend":
                        is_suspend = True
                        break
        
        # Create function object
        extracted_function = ExtractedFunction(
            name=function_name,
            start_line=self._get_line_number(function_node),
            end_line=self._get_end_line_number(function_node),
            class_name=class_name,
            body_node=body_node
        )
        
        # Mark suspend functions
        if is_suspend:
            extracted_function.decorators.append("suspend")
        
        # Parse annotations
        extracted_function.decorators.extend(self._parse_annotations(function_node))
        
        # Parse parameters
        parameters_node = function_node.child_by_field_name("parameters")
        
        if parameters_node:
            self._parse_function_parameters(parameters_node, extracted_function)
        
        # Parse function calls in body
        if body_node:
            self._parse_method_calls(body_node, extracted_function)
        
        result.functions.append(extracted_function)
    
    def _parse_function_parameters(self, parameters_node: Node, function: ExtractedFunction):
        """Parse Kotlin function parameters."""
        for child in parameters_node.children:
            if child.type == "function_value_parameter":
                param_name = None
                param_type = None
                
                for param_child in child.children:
                    if param_child.type == "simple_identifier":
                        param_name = self._get_node_text(param_child)
                    elif param_child.type == "user_type":
                        param_type = self._get_node_text(param_child)
                
                if param_name:
                    param = ExtractedVariable(
                        name=param_name,
                        start_line=self._get_line_number(child),
                        end_line=self._get_end_line_number(child),
                        scope_name=function.name,
                        scope_type="parameter",
                        var_type=param_type,
                        is_parameter=True
                    )
                    function.parameters.append(param)
    
    def _parse_method_calls(self, body_node: Node, function: ExtractedFunction):
        """Parse method calls within function body."""
        query = self._get_query("method_calls_query")
        if not query:
            return
            
        captures = query.captures(body_node)
        for node, capture_name in captures:
            if capture_name == "method_call":
                # Get method name from call expression
                callee_node = None
                for child in node.children:
                    if child.type in ["simple_identifier", "navigation_expression"]:
                        callee_node = child
                        break
                
                if callee_node:
                    if callee_node.type == "simple_identifier":
                        method_name = self._get_node_text(callee_node)
                        if method_name:
                            call_info = (
                                method_name,
                                None,  # no receiver for simple calls
                                None,  # receiver type
                                self._get_line_number(node)
                            )
                            function.calls.add(call_info)
                    elif callee_node.type == "navigation_expression":
                        # Parse receiver.method() calls
                        receiver_node = None
                        method_node = None
                        for nav_child in callee_node.children:
                            if nav_child.type == "simple_identifier" and not receiver_node:
                                receiver_node = nav_child
                            elif nav_child.type == "simple_identifier" and receiver_node:
                                method_node = nav_child
                        
                        if method_node:
                            method_name = self._get_node_text(method_node)
                            receiver_name = self._get_node_text(receiver_node) if receiver_node else None
                            
                            if method_name:
                                call_info = (
                                    method_name,
                                    receiver_name,
                                    None,  # receiver type
                                    self._get_line_number(node)
                                )
                                function.calls.add(call_info)
    
    def _parse_property_node(self, property_node: Node, result: ParsedFileResult, class_name: Optional[str] = None):
        """Parse Kotlin property declaration."""
        property_name = None
        property_type = None
        is_val = False
        is_var = False
        
        for child in property_node.children:
            if child.type == "simple_identifier":
                property_name = self._get_node_text(child)
            elif child.type == "user_type":
                property_type = self._get_node_text(child)
            elif child.type == "modifiers":
                for modifier in child.children:
                    modifier_text = self._get_node_text(modifier)
                    if modifier_text == "val":
                        is_val = True
                    elif modifier_text == "var":
                        is_var = True
        
        if property_name:
            scope_type = "class_attribute" if class_name else "global_variable"
            if is_val:
                scope_type += "_val"
            elif is_var:
                scope_type += "_var"
            
            property_var = ExtractedVariable(
                name=property_name,
                start_line=self._get_line_number(property_node),
                end_line=self._get_end_line_number(property_node),
                scope_name=class_name or "global",
                scope_type=scope_type,
                var_type=property_type
            )
            
            if class_name:
                # Find the class and add to its attributes
                for cls in result.classes:
                    if cls.name == class_name:
                        cls.attributes.append(property_var)
                        break
            else:
                result.global_variables.append(property_var)
    
    def _parse_class_node(self, class_node: Node, result: ParsedFileResult):
        """Parse Kotlin class/object/interface declaration."""
        name_node = None
        is_interface = False
        is_object = False
        
        for child in class_node.children:
            if child.type == "type_identifier":
                name_node = child
            elif child.type == "interface":
                is_interface = True
            elif child.type == "object":
                is_object = True

        if not name_node:
            return
            
        class_name = self._get_node_text(name_node)
        if not class_name:
            return
            
        # Get class body
        body_node = class_node.child_by_field_name("body")

        extracted_class = ExtractedClass(
            name=class_name,
            start_line=self._get_line_number(class_node),
            end_line=self._get_end_line_number(class_node),
            body_node=body_node
        )

        # Mark as interface or object
        if is_interface:
            extracted_class.decorators.append("interface")
        elif is_object:
            extracted_class.decorators.append("object")

        # Check if it's a data class, sealed class, etc.
        for child in class_node.children:
            if child.type == "modifiers":
                for modifier in child.children:
                    modifier_text = self._get_node_text(modifier)
                    if modifier_text in ["data", "sealed", "open", "abstract", "inner"]:
                        extracted_class.decorators.append(modifier_text)
        
        # Parse superclasses/interfaces
        delegation_specifiers_node = None
        for child in class_node.children:
            if child.type == "delegation_specifiers":
                delegation_specifiers_node = child
                break
        
        if delegation_specifiers_node:
            for child in delegation_specifiers_node.children:
                if child.type == "delegated_super_type":
                    for super_child in child.children:
                        if super_child.type == "user_type":
                            super_name = self._get_node_text(super_child)
                            if super_name:
                                extracted_class.superclasses.add(super_name)
        
        # Parse annotations
        extracted_class.decorators.extend(self._parse_annotations(class_node))
        
        result.classes.append(extracted_class)
        
        # Parse class body
        if body_node:
            self._parse_class_body(body_node, result, class_name)
    
    def _parse_class_body(self, body_node: Node, result: ParsedFileResult, class_name: str):
        """Parse the body of a class."""
        for child in body_node.children:
            if child.type == "function_declaration":
                self._parse_function_node(child, result, class_name)
            elif child.type == "property_declaration":
                self._parse_property_node(child, result, class_name)
            elif child.type in ["class_declaration", "object_declaration"]:
                # Nested class
                self._parse_class_node(child, result)
    
    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        """Extract all entities from Kotlin code."""
        # Parse package declaration first
        self._parse_package_declaration(root_node, result)
        
        # Parse imports
        imports_query = self._get_query("imports_query")
        if imports_query:
            captures = imports_query.captures(root_node)
            for node, capture_name in captures:
                if capture_name == "import_node":
                    self._parse_import_node(node, result)
        
        # Parse top-level definitions
        definitions_query = self._get_query("definitions_query")
        if definitions_query:
            captures = definitions_query.captures(root_node)
            for node, capture_name in captures:
                if capture_name in ["class_node", "object_node"]:
                    self._parse_class_node(node, result)
                elif capture_name == "function_node":
                    # Top-level function
                    self._parse_function_node(node, result)
                elif capture_name == "property_node":
                    # Top-level property
                    self._parse_property_node(node, result) 