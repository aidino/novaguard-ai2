# novaguard-backend/app/ckg_builder/parsers/java_parser.py
import logging
from typing import Optional, Set, List, Tuple, Dict, Any
from tree_sitter import Node, Query
from tree_sitter_languages import get_language
from tree_sitter import Language, Parser

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

class JavaParser(BaseCodeParser):
    """Tree-sitter based Java parser."""
    
    QUERY_DEFINITIONS = {
        "imports_query": """
            [
              (import_declaration) @import_node
            ]
        """,
        "definitions_query": """
            [
              (class_declaration) @class_node
              (interface_declaration) @interface_node
              (enum_declaration) @enum_node
              (method_declaration) @method_node
              (constructor_declaration) @constructor_node
              (field_declaration) @field_node
            ]
        """,
        "method_calls_query": """
            (method_invocation) @method_call
        """,
        "annotations_query": """
            (annotation) @annotation_node
        """
    }
    
    def __init__(self):
        super().__init__("java")
        self.queries: Dict[str, Query] = {}
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"JavaParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"JavaParser: Error compiling query '{query_name}': {e}")
                
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
            if child.type == "package_declaration":
                package_name_node = child.child_by_field_name("name")
                if package_name_node:
                    package_name = self._get_node_text(package_name_node)
                    if package_name:
                        # Store as a special import
                        package_import = ExtractedImport(
                            import_type="package",
                            start_line=self._get_line_number(child),
                            end_line=self._get_end_line_number(child),
                            module_path=package_name
                        )
                        result.imports.append(package_import)
    
    def _parse_import_node(self, import_node: Node, result: ParsedFileResult):
        """Parse Java import declaration."""
        import_path_node = import_node.child_by_field_name("name")
        if not import_path_node:
            return
            
        import_path = self._get_node_text(import_path_node)
        if not import_path:
            return
            
        # Check if it's a static import
        is_static = False
        for child in import_node.children:
            if child.type == "static" or self._get_node_text(child) == "static":
                is_static = True
                break
        
        # Check if it's a wildcard import
        is_wildcard = import_path.endswith(".*")
        
        import_type = "static" if is_static else "regular"
        if is_wildcard:
            import_type += "_wildcard"
            
        extracted_import = ExtractedImport(
            import_type=import_type,
            start_line=self._get_line_number(import_node),
            end_line=self._get_end_line_number(import_node),
            module_path=import_path
        )
        result.imports.append(extracted_import)
    
    def _parse_method_node(self, method_node: Node, result: ParsedFileResult, class_name: Optional[str] = None):
        """Parse Java method declaration."""
        name_node = method_node.child_by_field_name("name")
        if not name_node:
            return
            
        method_name = self._get_node_text(name_node)
        if not method_name:
            return
            
        # Get method body
        body_node = method_node.child_by_field_name("body")
        
        # Create function object
        extracted_function = ExtractedFunction(
            name=method_name,
            start_line=self._get_line_number(method_node),
            end_line=self._get_end_line_number(method_node),
            class_name=class_name,
            body_node=body_node
        )
        
        # Parse annotations
        extracted_function.decorators = self._parse_annotations(method_node)
        
        # Parse parameters
        parameters_node = method_node.child_by_field_name("parameters")
        if parameters_node:
            self._parse_method_parameters(parameters_node, extracted_function)
        
        # Parse method calls in body
        if body_node:
            self._parse_method_calls(body_node, extracted_function)
        
        result.functions.append(extracted_function)
    
    def _parse_method_parameters(self, parameters_node: Node, function: ExtractedFunction):
        """Parse method parameters."""
        for child in parameters_node.children:
            if child.type == "formal_parameter":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                
                if name_node:
                    param_name = self._get_node_text(name_node)
                    param_type = self._get_node_text(type_node) if type_node else None
                    
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
        """Parse method calls within method body."""
        query = self._get_query("method_calls_query")
        if not query:
            return
            
        captures = query.captures(body_node)
        for node, capture_name in captures:
            if capture_name == "method_call":
                # Get method name
                object_node = node.child_by_field_name("object")
                name_node = node.child_by_field_name("name")
                
                if name_node:
                    method_name = self._get_node_text(name_node)
                    object_name = self._get_node_text(object_node) if object_node else None
                    
                    if method_name:
                        call_info = (
                            method_name,
                            object_name,
                            None,  # receiver type
                            self._get_line_number(node)
                        )
                        function.calls.add(call_info)
    
    def _parse_constructor_node(self, constructor_node: Node, result: ParsedFileResult, class_name: Optional[str] = None):
        """Parse Java constructor declaration."""
        name_node = constructor_node.child_by_field_name("name")
        if not name_node:
            return
            
        constructor_name = self._get_node_text(name_node)
        if not constructor_name:
            return
            
        body_node = constructor_node.child_by_field_name("body")
        
        extracted_function = ExtractedFunction(
            name=f"<init>:{constructor_name}",  # Mark as constructor
            start_line=self._get_line_number(constructor_node),
            end_line=self._get_end_line_number(constructor_node),
            class_name=class_name,
            body_node=body_node
        )
        
        # Parse parameters
        parameters_node = constructor_node.child_by_field_name("parameters")
        if parameters_node:
            self._parse_method_parameters(parameters_node, extracted_function)
        
        result.functions.append(extracted_function)
    
    def _parse_field_node(self, field_node: Node, result: ParsedFileResult, class_name: Optional[str] = None):
        """Parse Java field declaration."""
        declarator_node = None
        type_node = field_node.child_by_field_name("type")
        
        # Find variable declarator
        for child in field_node.children:
            if child.type == "variable_declarator":
                declarator_node = child
                break
        
        if not declarator_node:
            return
            
        name_node = declarator_node.child_by_field_name("name")
        if not name_node:
            return
            
        field_name = self._get_node_text(name_node)
        field_type = self._get_node_text(type_node) if type_node else None
        
        if field_name:
            scope_type = "class_attribute" if class_name else "global_variable"
            field_var = ExtractedVariable(
                name=field_name,
                start_line=self._get_line_number(field_node),
                end_line=self._get_end_line_number(field_node),
                scope_name=class_name or "global",
                scope_type=scope_type,
                var_type=field_type
            )
            
            if class_name:
                # Find the class and add to its attributes
                for cls in result.classes:
                    if cls.name == class_name:
                        cls.attributes.append(field_var)
                        break
            else:
                result.global_variables.append(field_var)
    
    def _parse_class_node(self, class_node: Node, result: ParsedFileResult):
        """Parse Java class/interface/enum declaration."""
        name_node = class_node.child_by_field_name("name")
        if not name_node:
            return
            
        class_name = self._get_node_text(name_node)
        if not class_name:
            return
            
        body_node = class_node.child_by_field_name("body")
        
        extracted_class = ExtractedClass(
            name=class_name,
            start_line=self._get_line_number(class_node),
            end_line=self._get_end_line_number(class_node),
            body_node=body_node
        )
        
        # Parse superclasses/interfaces
        superclass_node = class_node.child_by_field_name("superclass")
        if superclass_node:
            superclass_name = self._get_node_text(superclass_node)
            if superclass_name:
                extracted_class.superclasses.add(superclass_name)
        
        interfaces_node = class_node.child_by_field_name("interfaces")
        if interfaces_node:
            for child in interfaces_node.children:
                if child.type == "type_identifier":
                    interface_name = self._get_node_text(child)
                    if interface_name:
                        extracted_class.superclasses.add(interface_name)
        
        # Parse annotations
        extracted_class.decorators = self._parse_annotations(class_node)
        
        result.classes.append(extracted_class)
        
        # Parse class body
        if body_node:
            self._parse_class_body(body_node, result, class_name)
    
    def _parse_class_body(self, body_node: Node, result: ParsedFileResult, class_name: str):
        """Parse the body of a class."""
        for child in body_node.children:
            if child.type == "method_declaration":
                self._parse_method_node(child, result, class_name)
            elif child.type == "constructor_declaration":
                self._parse_constructor_node(child, result, class_name)
            elif child.type == "field_declaration":
                self._parse_field_node(child, result, class_name)
            elif child.type in ["class_declaration", "interface_declaration", "enum_declaration"]:
                # Nested class
                self._parse_class_node(child, result)
    
    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        """Extract all entities from Java code."""
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
                if capture_name in ["class_node", "interface_node", "enum_node"]:
                    self._parse_class_node(node, result)
                elif capture_name == "method_node":
                    # Top-level method (rare in Java)
                    self._parse_method_node(node, result)
                elif capture_name == "constructor_node":
                    # Top-level constructor (rare in Java)
                    self._parse_constructor_node(node, result)
                elif capture_name == "field_node":
                    # Top-level field (rare in Java)
                    self._parse_field_node(node, result) 