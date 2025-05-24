# novaguard-backend/app/ckg_builder/java_parser.py
import logging
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from tree_sitter import Language, Parser, Node, Query # type: ignore
from tree_sitter_languages import get_language

from .parsers import BaseCodeParser, ParsedFileResult, ExtractedFunction, ExtractedClass, ExtractedImport, ExtractedVariable

logger = logging.getLogger(__name__)

class JavaParser(BaseCodeParser):
    """Parser for Java files using tree-sitter."""

    QUERY_DEFINITIONS = {
        "imports_query": """
            [
              (import_declaration) @import_node
            ]
        """,
        "package_query": """
            (package_declaration) @package_node
        """,
        "definitions_query": """
            [
              (class_declaration) @definition_node
              (interface_declaration) @definition_node
              (enum_declaration) @definition_node
              (method_declaration) @definition_node
              (constructor_declaration) @definition_node
              (field_declaration) @definition_node
            ]
        """,
        "annotations_query": """
            (annotation) @annotation_node
        """,
        "body_calls_query": """
            (method_invocation
                name: (identifier) @call_method_name
            ) @call_expr
        """,
        "body_identifiers_query": """
            (identifier) @id_node
        """
    }

    def __init__(self):
        """Initialize Java parser."""
        super().__init__("java")
        self.queries: Dict[str, Query] = {}
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"JavaParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"JavaParser: Error compiling query '{query_name}': {type(e).__name__} - {e}")

    def _get_query(self, query_name: str) -> Optional[Query]:
        return self.queries.get(query_name)

    def _parse_modifiers(self, modifiers_node: Optional[Node]) -> List[str]:
        """Parse Java modifiers (public, private, static, final, etc.)."""
        modifiers = []
        if modifiers_node:
            for child in modifiers_node.named_children:
                if child.type == "modifiers":
                    for modifier in child.named_children:
                        modifier_text = self._get_node_text(modifier)
                        if modifier_text:
                            modifiers.append(modifier_text)
                else:
                    modifier_text = self._get_node_text(child)
                    if modifier_text:
                        modifiers.append(modifier_text)
        return modifiers

    def _parse_annotations(self, node: Node) -> List[str]:
        """Parse annotations from a node."""
        annotations = []
        annotations_query = self._get_query("annotations_query")
        if annotations_query:
            try:
                for pattern_idx, captures_dict in annotations_query.matches(node):
                    annotation_node = captures_dict.get("annotation_node")
                    if annotation_node:
                        annotation_text = self._get_node_text(annotation_node)
                        if annotation_text:
                            annotations.append(annotation_text)
            except Exception as e:
                logger.error(f"JavaParser: Error extracting annotations: {e}")
        return annotations

    def _parse_parameters_node(self, parameters_node: Optional[Node], owner_func_name: str) -> Tuple[List[ExtractedVariable], str]:
        """Parse method parameters from formal_parameters node."""
        parameters: List[ExtractedVariable] = []
        parameters_str = ""
        
        if not parameters_node:
            return parameters, parameters_str

        parameters_str = self._get_node_text(parameters_node) or ""
        
        for param_child in parameters_node.named_children:
            if param_child.type == "formal_parameter":
                # Java formal parameter: type name
                type_node = param_child.child_by_field_name("type")
                name_node = param_child.child_by_field_name("name")
                
                param_name = None
                param_type = None
                
                if name_node:
                    param_name = self._get_node_text(name_node)
                if type_node:
                    param_type = self._get_node_text(type_node)
                    
                if param_name:
                    parameters.append(ExtractedVariable(
                        name=param_name,
                        start_line=self._get_line_number(param_child),
                        end_line=self._get_end_line_number(param_child),
                        scope_name=owner_func_name,
                        scope_type="parameter",
                        var_type=param_type,
                        is_parameter=True
                    ))
                    
        return parameters, parameters_str

    def _extract_body_details(self, body_node: Optional[Node], owner_function: ExtractedFunction, result: ParsedFileResult):
        """Extract method calls and variable usage from method body."""
        if not body_node:
            return

        # Extract method calls
        calls_query = self._get_query("body_calls_query")
        if calls_query:
            try:
                for pattern_idx, captures_dict in calls_query.matches(body_node):
                    call_node = captures_dict.get("call_expr")
                    method_name_node = captures_dict.get("call_method_name")
                    
                    if call_node and method_name_node:
                        call_line = self._get_line_number(call_node)
                        method_name = self._get_node_text(method_name_node)
                        
                        if method_name:
                            owner_function.calls.add((method_name, None, None, call_line))
                            
            except Exception as e:
                logger.error(f"JavaParser: Error extracting calls from body: {e}")

        # Extract local variable declarations
        for child in body_node.named_children:
            if child.type == "local_variable_declaration":
                self._extract_local_variables_from_declaration(child, owner_function)
            # Recursively process nested blocks
            elif child.type in ["block", "if_statement", "for_statement", "while_statement", "try_statement"]:
                self._extract_body_details(child, owner_function, result)

    def _extract_local_variables_from_declaration(self, declaration_node: Node, owner_function: ExtractedFunction):
        """Extract local variable declarations."""
        type_node = declaration_node.child_by_field_name("type")
        var_type = None
        if type_node:
            var_type = self._get_node_text(type_node)
            
        for child in declaration_node.named_children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    var_name = self._get_node_text(name_node)
                    if var_name:
                        owner_function.local_variables.append(ExtractedVariable(
                            name=var_name,
                            start_line=self._get_line_number(child),
                            end_line=self._get_end_line_number(child),
                            scope_name=owner_function.name,
                            scope_type="local_variable",
                            var_type=var_type
                        ))

    def _parse_method_node(self, method_node: Node, result: ParsedFileResult, class_name: Optional[str] = None) -> Optional[ExtractedFunction]:
        """Parse Java method declaration."""
        name_node = method_node.child_by_field_name("name")
        if not name_node:
            return None
            
        method_name = self._get_node_text(name_node)
        if not method_name:
            return None

        # Get method signature
        signature = self._get_node_text(method_node)
        
        # Get parameters
        parameters_node = method_node.child_by_field_name("parameters")
        parameters, parameters_str = self._parse_parameters_node(parameters_node, method_name)
        
        # Get body
        body_node = method_node.child_by_field_name("body")
        
        extracted_function = ExtractedFunction(
            name=method_name,
            start_line=self._get_line_number(method_node),
            end_line=self._get_end_line_number(method_node),
            signature=signature,
            class_name=class_name,
            body_node=body_node,
            parameters_str=parameters_str
        )
        
        extracted_function.parameters = parameters
        
        # Parse annotations
        extracted_function.decorators = self._parse_annotations(method_node)
        
        # Extract body details
        self._extract_body_details(body_node, extracted_function, result)
        
        return extracted_function

    def _parse_constructor_node(self, constructor_node: Node, result: ParsedFileResult, class_name: Optional[str] = None) -> Optional[ExtractedFunction]:
        """Parse Java constructor declaration."""
        name_node = constructor_node.child_by_field_name("name")
        constructor_name = class_name or (self._get_node_text(name_node) if name_node else "constructor")
        
        # Get constructor signature
        signature = self._get_node_text(constructor_node)
        
        # Get parameters
        parameters_node = constructor_node.child_by_field_name("parameters")
        parameters, parameters_str = self._parse_parameters_node(parameters_node, constructor_name)
        
        # Get body
        body_node = constructor_node.child_by_field_name("body")
        
        extracted_function = ExtractedFunction(
            name=constructor_name,
            start_line=self._get_line_number(constructor_node),
            end_line=self._get_end_line_number(constructor_node),
            signature=signature,
            class_name=class_name,
            body_node=body_node,
            parameters_str=parameters_str
        )
        
        extracted_function.parameters = parameters
        
        # Parse annotations
        extracted_function.decorators = self._parse_annotations(constructor_node)
        
        # Extract body details
        self._extract_body_details(body_node, extracted_function, result)
        
        return extracted_function

    def _parse_class_node(self, class_node: Node, result: ParsedFileResult) -> Optional[ExtractedClass]:
        """Parse Java class declaration."""
        name_node = class_node.child_by_field_name("name")
        if not name_node:
            return None
            
        class_name = self._get_node_text(name_node)
        if not class_name:
            return None

        body_node = class_node.child_by_field_name("body")
        
        extracted_class = ExtractedClass(
            name=class_name,
            start_line=self._get_line_number(class_node),
            end_line=self._get_end_line_number(class_node),
            body_node=body_node
        )
        
        # Parse superclass
        superclass_node = class_node.child_by_field_name("superclass")
        if superclass_node:
            superclass_name = self._get_node_text(superclass_node)
            if superclass_name:
                extracted_class.superclasses.add(superclass_name)
        
        # Parse interfaces
        interfaces_node = class_node.child_by_field_name("interfaces")
        if interfaces_node:
            for interface_child in interfaces_node.named_children:
                interface_name = self._get_node_text(interface_child)
                if interface_name:
                    extracted_class.superclasses.add(interface_name)
        
        # Parse annotations
        extracted_class.decorators = self._parse_annotations(class_node)
        
        # Parse class body
        if body_node:
            for child in body_node.named_children:
                if child.type == "method_declaration":
                    method = self._parse_method_node(child, result, class_name)
                    if method:
                        extracted_class.methods.append(method)
                        result.functions.append(method)
                elif child.type == "constructor_declaration":
                    constructor = self._parse_constructor_node(child, result, class_name)
                    if constructor:
                        extracted_class.methods.append(constructor)
                        result.functions.append(constructor)
                elif child.type == "field_declaration":
                    self._parse_field_declaration(child, extracted_class)
                elif child.type in ["class_declaration", "interface_declaration", "enum_declaration"]:
                    # Nested classes
                    nested_class = self._parse_class_node(child, result)
                    if nested_class:
                        result.classes.append(nested_class)
        
        return extracted_class

    def _parse_field_declaration(self, field_node: Node, extracted_class: ExtractedClass):
        """Parse Java field declarations."""
        type_node = field_node.child_by_field_name("type")
        field_type = None
        if type_node:
            field_type = self._get_node_text(type_node)
            
        for child in field_node.named_children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    field_name = self._get_node_text(name_node)
                    if field_name:
                        extracted_class.attributes.append(ExtractedVariable(
                            name=field_name,
                            start_line=self._get_line_number(child),
                            end_line=self._get_end_line_number(child),
                            scope_name=extracted_class.name,
                            scope_type="class_attribute",
                            var_type=field_type
                        ))

    def _parse_import_declaration_node(self, import_node: Node, result: ParsedFileResult) -> Optional[ExtractedImport]:
        """Parse Java import declaration."""
        import_text = self._get_node_text(import_node)
        if not import_text:
            return None
            
        # Extract import path
        import_path = None
        for child in import_node.named_children:
            if child.type in ["scoped_identifier", "identifier"]:
                import_path = self._get_node_text(child)
                break
                
        if not import_path:
            return None
            
        # Check if it's a static import
        import_type = "static" if "static" in import_text else "regular"
        
        # Check if it's a wildcard import
        is_wildcard = import_text.endswith("*")
        
        imported_names = []
        if is_wildcard:
            imported_names = [("*", None)]
        else:
            # Extract the last part as the imported name
            parts = import_path.split(".")
            if parts:
                imported_names = [(parts[-1], None)]
        
        return ExtractedImport(
            import_type=import_type,
            start_line=self._get_line_number(import_node),
            end_line=self._get_end_line_number(import_node),
            module_path=import_path,
            imported_names=imported_names
        )

    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        """Extract all entities from Java source code."""
        
        # Extract package declaration
        package_query = self._get_query("package_query")
        if package_query:
            try:
                for pattern_idx, captures_dict in package_query.matches(root_node):
                    package_node = captures_dict.get("package_node")
                    if package_node:
                        # Store package info in file metadata if needed
                        pass
            except Exception as e:
                logger.error(f"JavaParser: Error extracting package: {e}")
        
        # Extract imports
        imports_query = self._get_query("imports_query")
        if imports_query:
            try:
                for pattern_idx, captures_dict in imports_query.matches(root_node):
                    import_node = captures_dict.get("import_node")
                    if import_node:
                        extracted_import = self._parse_import_declaration_node(import_node, result)
                        if extracted_import:
                            result.imports.append(extracted_import)
            except Exception as e:
                logger.error(f"JavaParser: Error extracting imports: {e}")
        
        # Extract definitions (classes, interfaces, methods, etc.)
        definitions_query = self._get_query("definitions_query")
        if definitions_query:
            try:
                for pattern_idx, captures_dict in definitions_query.matches(root_node):
                    definition_node = captures_dict.get("definition_node")
                    if definition_node:
                        if definition_node.type in ["class_declaration", "interface_declaration", "enum_declaration"]:
                            extracted_class = self._parse_class_node(definition_node, result)
                            if extracted_class:
                                result.classes.append(extracted_class)
                        elif definition_node.type == "method_declaration":
                            # Top-level methods (rare in Java, but possible in some contexts)
                            extracted_method = self._parse_method_node(definition_node, result)
                            if extracted_method:
                                result.functions.append(extracted_method)
            except Exception as e:
                logger.error(f"JavaParser: Error extracting definitions: {e}")

        logger.info(f"JavaParser: Extracted {len(result.classes)} classes, {len(result.functions)} functions, "
                   f"{len(result.imports)} imports from {result.file_path}") 