# novaguard-backend/app/ckg_builder/kotlin_parser.py
import logging
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from tree_sitter import Language, Parser, Node, Query # type: ignore
from tree_sitter_languages import get_language

from .parsers import BaseCodeParser, ParsedFileResult, ExtractedFunction, ExtractedClass, ExtractedImport, ExtractedVariable

logger = logging.getLogger(__name__)

class KotlinParser(BaseCodeParser):
    """Parser for Kotlin files using tree-sitter."""

    QUERY_DEFINITIONS = {
        "imports_query": """
            [
              (import_header) @import_node
            ]
        """,
        "package_query": """
            (package_header) @package_node
        """,
        "definitions_query": """
            (source_file
              [
                (class_declaration) @definition_node
                (object_declaration) @definition_node
                (function_declaration) @definition_node
                (property_declaration) @definition_node
              ]
            )
        """,
        "annotations_query": """
            (annotation) @annotation_node
        """,
        "body_calls_query": """
            [
              (call_expression
                  (simple_identifier) @call_function_name
              ) @call_expr
              (navigation_expression
                  (simple_identifier) @call_method_name
              ) @method_call_expr
            ]
        """,
        "body_identifiers_query": """
            (simple_identifier) @id_node
        """,
        "coroutine_query": """
            [
              (function_declaration
                modifiers: (modifiers) @suspend_modifier
              ) @suspend_function
              (call_expression
                (simple_identifier) @coroutine_call
              ) @coroutine_expr
            ]
        """
    }

    def __init__(self):
        """Initialize Kotlin parser."""
        super().__init__("kotlin")
        self.queries: Dict[str, Query] = {}
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"KotlinParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"KotlinParser: Error compiling query '{query_name}': {type(e).__name__} - {e}")

    def _get_query(self, query_name: str) -> Optional[Query]:
        return self.queries.get(query_name)

    def _parse_modifiers(self, modifiers_node: Optional[Node]) -> List[str]:
        """Parse Kotlin modifiers (public, private, suspend, data, etc.)."""
        modifiers = []
        if modifiers_node:
            for modifier in modifiers_node.named_children:
                modifier_text = self._get_node_text(modifier)
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
                logger.error(f"KotlinParser: Error extracting annotations: {e}")
        return annotations

    def _parse_parameters_node(self, parameters_node: Optional[Node], owner_func_name: str) -> Tuple[List[ExtractedVariable], str]:
        """Parse Kotlin function parameters."""
        parameters: List[ExtractedVariable] = []
        parameters_str = ""
        
        if not parameters_node:
            return parameters, parameters_str

        parameters_str = self._get_node_text(parameters_node) or ""
        
        for param_child in parameters_node.named_children:
            if param_child.type == "parameter":
                # Kotlin parameter: name: type
                name_node = param_child.child_by_field_name("name")
                type_node = param_child.child_by_field_name("type")
                
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
        """Extract function calls and variable usage from function body."""
        if not body_node:
            return

        # Extract function calls
        calls_query = self._get_query("body_calls_query")
        if calls_query:
            try:
                for pattern_idx, captures_dict in calls_query.matches(body_node):
                    call_node = captures_dict.get("call_expr") or captures_dict.get("method_call_expr")
                    function_name_node = captures_dict.get("call_function_name") or captures_dict.get("call_method_name")
                    
                    if call_node and function_name_node:
                        call_line = self._get_line_number(call_node)
                        function_name = self._get_node_text(function_name_node)
                        
                        if function_name:
                            owner_function.calls.add((function_name, None, None, call_line))
                            
            except Exception as e:
                logger.error(f"KotlinParser: Error extracting calls from body: {e}")

        # Check for coroutine usage
        self._extract_coroutine_usage(body_node, owner_function)

        # Extract local variable/property declarations
        for child in body_node.named_children:
            if child.type == "property_declaration":
                self._extract_local_variables_from_property(child, owner_function)
            # Recursively process nested blocks
            elif child.type in ["block", "if_expression", "for_statement", "while_statement", "try_expression"]:
                self._extract_body_details(child, owner_function, result)

    def _extract_coroutine_usage(self, body_node: Node, owner_function: ExtractedFunction):
        """Extract coroutine-related calls and patterns."""
        coroutine_query = self._get_query("coroutine_query")
        if coroutine_query:
            try:
                for pattern_idx, captures_dict in coroutine_query.matches(body_node):
                    coroutine_call_node = captures_dict.get("coroutine_call")
                    if coroutine_call_node:
                        call_name = self._get_node_text(coroutine_call_node)
                        if call_name in ["launch", "async", "runBlocking", "withContext", "delay", "suspendCoroutine"]:
                            call_line = self._get_line_number(coroutine_call_node)
                            owner_function.calls.add((call_name, "coroutine", None, call_line))
            except Exception as e:
                logger.error(f"KotlinParser: Error extracting coroutine usage: {e}")

    def _extract_local_variables_from_property(self, property_node: Node, owner_function: ExtractedFunction):
        """Extract local property declarations (val/var)."""
        # Check if it's val or var
        modifiers_node = property_node.child_by_field_name("modifiers")
        is_mutable = False
        if modifiers_node:
            modifiers_text = self._get_node_text(modifiers_node)
            is_mutable = "var" in modifiers_text if modifiers_text else False

        name_node = property_node.child_by_field_name("name") 
        type_node = property_node.child_by_field_name("type")
        
        if name_node:
            var_name = self._get_node_text(name_node)
            var_type = None
            if type_node:
                var_type = self._get_node_text(type_node)
                
            if var_name:
                owner_function.local_variables.append(ExtractedVariable(
                    name=var_name,
                    start_line=self._get_line_number(property_node),
                    end_line=self._get_end_line_number(property_node),
                    scope_name=owner_function.name,
                    scope_type="local_variable",
                    var_type=var_type
                ))

    def _is_suspend_function(self, function_node: Node) -> bool:
        """Check if a function is a suspend function."""
        modifiers_node = function_node.child_by_field_name("modifiers")
        if modifiers_node:
            modifiers_text = self._get_node_text(modifiers_node)
            return "suspend" in modifiers_text if modifiers_text else False
        return False

    def _is_extension_function(self, function_node: Node) -> bool:
        """Check if a function is an extension function."""
        receiver_node = function_node.child_by_field_name("receiver_type")
        return receiver_node is not None

    def _parse_function_node(self, function_node: Node, result: ParsedFileResult, class_name: Optional[str] = None) -> Optional[ExtractedFunction]:
        """Parse Kotlin function declaration."""
        name_node = function_node.child_by_field_name("name")
        if not name_node:
            return None
            
        function_name = self._get_node_text(name_node)
        if not function_name:
            return None

        # Get function signature
        signature = self._get_node_text(function_node)
        
        # Get parameters
        parameters_node = function_node.child_by_field_name("parameters")
        parameters, parameters_str = self._parse_parameters_node(parameters_node, function_name)
        
        # Get body
        body_node = function_node.child_by_field_name("body")
        
        extracted_function = ExtractedFunction(
            name=function_name,
            start_line=self._get_line_number(function_node),
            end_line=self._get_end_line_number(function_node),
            signature=signature,
            class_name=class_name,
            body_node=body_node,
            parameters_str=parameters_str
        )
        
        extracted_function.parameters = parameters
        
        # Parse annotations
        extracted_function.decorators = self._parse_annotations(function_node)
        
        # Add Kotlin-specific metadata
        if self._is_suspend_function(function_node):
            extracted_function.decorators.append("@Suspend")
        if self._is_extension_function(function_node):
            extracted_function.decorators.append("@Extension")
        
        # Extract body details
        self._extract_body_details(body_node, extracted_function, result)
        
        return extracted_function

    def _is_interface(self, class_node: Node) -> bool:
        """Check if a class declaration is actually an interface."""
        for child in class_node.children:
            if child.type == "interface":
                return True
        return False

    def _is_data_class(self, class_node: Node) -> bool:
        """Check if a class is a data class."""
        modifiers_node = class_node.child_by_field_name("modifiers")
        if modifiers_node:
            modifiers_text = self._get_node_text(modifiers_node)
            return "data" in modifiers_text if modifiers_text else False
        return False

    def _is_sealed_class(self, class_node: Node) -> bool:
        """Check if a class is a sealed class."""
        modifiers_node = class_node.child_by_field_name("modifiers")
        if modifiers_node:
            modifiers_text = self._get_node_text(modifiers_node)
            return "sealed" in modifiers_text if modifiers_text else False
        return False

    def _parse_class_node(self, class_node: Node, result: ParsedFileResult) -> Optional[ExtractedClass]:
        """Parse Kotlin class declaration."""
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
        
        # Parse superclass and interfaces
        delegation_specifiers = class_node.child_by_field_name("delegation_specifiers")
        if delegation_specifiers:
            for specifier in delegation_specifiers.named_children:
                if specifier.type == "constructor_invocation":
                    # Superclass constructor call
                    user_type = specifier.child_by_field_name("user_type")
                    if user_type:
                        superclass_name = self._get_node_text(user_type)
                        if superclass_name:
                            extracted_class.superclasses.add(superclass_name)
                elif specifier.type == "user_type":
                    # Interface implementation
                    interface_name = self._get_node_text(specifier)
                    if interface_name:
                        extracted_class.superclasses.add(interface_name)
        
        # Parse annotations
        extracted_class.decorators = self._parse_annotations(class_node)
        
        # Add Kotlin-specific metadata
        if self._is_interface(class_node):
            extracted_class.decorators.append("interface")
        if self._is_data_class(class_node):
            extracted_class.decorators.append("@DataClass")
        if self._is_sealed_class(class_node):
            extracted_class.decorators.append("@SealedClass")
        
        # Parse class body
        if body_node:
            for child in body_node.named_children:
                if child.type == "function_declaration":
                    method = self._parse_function_node(child, result, class_name)
                    if method:
                        extracted_class.methods.append(method)
                        result.functions.append(method)
                elif child.type == "property_declaration":
                    self._parse_property_declaration(child, extracted_class)
                elif child.type in ["class_declaration", "object_declaration", "interface_declaration"]:
                    # Nested classes
                    nested_class = self._parse_class_node(child, result)
                    if nested_class:
                        result.classes.append(nested_class)
        
        return extracted_class

    def _parse_object_declaration(self, object_node: Node, result: ParsedFileResult) -> Optional[ExtractedClass]:
        """Parse Kotlin object declaration (singleton)."""
        name_node = object_node.child_by_field_name("name")
        if not name_node:
            return None
            
        object_name = self._get_node_text(name_node)
        if not object_name:
            return None

        body_node = object_node.child_by_field_name("object_body")
        
        extracted_object = ExtractedClass(
            name=object_name,
            start_line=self._get_line_number(object_node),
            end_line=self._get_end_line_number(object_node),
            body_node=body_node
        )
        
        # Mark as object/singleton
        extracted_object.decorators.append("@Object")
        
        # Parse object body similar to class
        if body_node:
            for child in body_node.named_children:
                if child.type == "function_declaration":
                    method = self._parse_function_node(child, result, object_name)
                    if method:
                        extracted_object.methods.append(method)
                        result.functions.append(method)
                elif child.type == "property_declaration":
                    self._parse_property_declaration(child, extracted_object)
        
        return extracted_object

    def _parse_property_declaration(self, property_node: Node, extracted_class: ExtractedClass):
        """Parse Kotlin property declarations."""
        name_node = property_node.child_by_field_name("name")
        type_node = property_node.child_by_field_name("type")
        
        if name_node:
            property_name = self._get_node_text(name_node)
            property_type = None
            if type_node:
                property_type = self._get_node_text(type_node)
                
            if property_name:
                # Check if it's mutable (var) or immutable (val)
                modifiers_node = property_node.child_by_field_name("modifiers")
                is_mutable = False
                if modifiers_node:
                    modifiers_text = self._get_node_text(modifiers_node)
                    is_mutable = "var" in modifiers_text if modifiers_text else False
                
                var_type_annotation = f"{'var' if is_mutable else 'val'} {property_type}" if property_type else ('var' if is_mutable else 'val')
                
                extracted_class.attributes.append(ExtractedVariable(
                    name=property_name,
                    start_line=self._get_line_number(property_node),
                    end_line=self._get_end_line_number(property_node),
                    scope_name=extracted_class.name,
                    scope_type="class_attribute",
                    var_type=var_type_annotation
                ))

    def _parse_import_header_node(self, import_node: Node, result: ParsedFileResult) -> Optional[ExtractedImport]:
        """Parse Kotlin import header."""
        import_text = self._get_node_text(import_node)
        if not import_text:
            return None
            
        # Extract import path
        import_path = None
        for child in import_node.named_children:
            if child.type == "identifier":
                import_path = self._get_node_text(child)
                break
                
        if not import_path:
            return None
            
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
            import_type="regular",
            start_line=self._get_line_number(import_node),
            end_line=self._get_end_line_number(import_node),
            module_path=import_path,
            imported_names=imported_names
        )

    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        """Extract all entities from Kotlin source code with graceful error handling."""
        
        entities_extracted = False
        
        # Extract package declaration
        package_query = self._get_query("package_query")
        if package_query:
            try:
                for pattern_idx, captures_dict in package_query.matches(root_node):
                    package_node = captures_dict.get("package_node")
                    if package_node:
                        # Store package info in file metadata if needed
                        entities_extracted = True
            except Exception as e:
                logger.debug(f"KotlinParser: Error extracting package from {result.file_path}: {e}")
        
        # Extract imports
        imports_query = self._get_query("imports_query")
        if imports_query:
            try:
                for pattern_idx, captures_dict in imports_query.matches(root_node):
                    import_node = captures_dict.get("import_node")
                    if import_node:
                        extracted_import = self._parse_import_header_node(import_node, result)
                        if extracted_import:
                            result.imports.append(extracted_import)
                            entities_extracted = True
            except Exception as e:
                logger.debug(f"KotlinParser: Error extracting imports from {result.file_path}: {e}")
        
        # Extract definitions (classes, objects, functions, etc.)
        definitions_query = self._get_query("definitions_query")
        if definitions_query:
            try:
                for pattern_idx, captures_dict in definitions_query.matches(root_node):
                    definition_node = captures_dict.get("definition_node")
                    if definition_node:
                        try:
                            if definition_node.type in ["class_declaration", "interface_declaration"]:
                                extracted_class = self._parse_class_node(definition_node, result)
                                if extracted_class:
                                    result.classes.append(extracted_class)
                                    entities_extracted = True
                            elif definition_node.type == "object_declaration":
                                extracted_object = self._parse_object_declaration(definition_node, result)
                                if extracted_object:
                                    result.classes.append(extracted_object)
                                    entities_extracted = True
                            elif definition_node.type == "function_declaration":
                                # Top-level functions
                                extracted_function = self._parse_function_node(definition_node, result)
                                if extracted_function:
                                    result.functions.append(extracted_function)
                                    entities_extracted = True
                            elif definition_node.type == "property_declaration":
                                # Top-level properties
                                self._parse_top_level_property(definition_node, result)
                                entities_extracted = True
                        except Exception as e:
                            logger.debug(f"KotlinParser: Error parsing {definition_node.type} in {result.file_path}: {e}")
                            continue
            except Exception as e:
                logger.debug(f"KotlinParser: Error extracting definitions from {result.file_path}: {e}")

        # Fallback: try to extract at least some basic information if main extraction failed
        if not entities_extracted and root_node.has_error:
            logger.debug(f"KotlinParser: Attempting fallback extraction for {result.file_path}")
            self._fallback_extraction(root_node, result)
        
        # Only log warning if extraction completely failed
        if not entities_extracted and not (result.classes or result.functions or result.imports):
            logger.debug(f"KotlinParser: Unable to extract any meaningful data from {result.file_path}. "
                        f"File may use very advanced Kotlin syntax not yet supported.")

        logger.debug(f"KotlinParser: Extracted {len(result.classes)} classes/objects, {len(result.functions)} functions, "
                   f"{len(result.imports)} imports from {result.file_path}")

    def _fallback_extraction(self, root_node: Node, result: ParsedFileResult):
        """Fallback extraction for files with syntax errors."""
        try:
            # Try to find any recognizable patterns even with syntax errors
            def traverse_for_identifiers(node: Node, depth: int = 0):
                if depth > 10:  # Limit recursion depth
                    return
                    
                # Look for class-like patterns
                if node.type == "simple_identifier":
                    identifier_text = self._get_node_text(node)
                    if identifier_text and identifier_text[0].isupper():
                        # Likely a class name
                        parent = node.parent
                        if parent and any(keyword in parent.text.decode('utf8', errors='ignore').lower() 
                                        for keyword in ['class', 'interface', 'object']):
                            extracted_class = ExtractedClass(
                                name=identifier_text,
                                start_line=self._get_line_number(node),
                                end_line=self._get_end_line_number(node)
                            )
                            extracted_class.decorators.append("fallback_extraction")
                            result.classes.append(extracted_class)
                            
                # Look for function-like patterns
                elif node.type == "fun" and node.parent:
                    sibling = node.next_sibling
                    if sibling and sibling.type == "simple_identifier":
                        function_name = self._get_node_text(sibling)
                        if function_name:
                            extracted_function = ExtractedFunction(
                                name=function_name,
                                start_line=self._get_line_number(node),
                                end_line=self._get_end_line_number(sibling)
                            )
                            extracted_function.decorators.append("fallback_extraction")
                            result.functions.append(extracted_function)
                
                for child in node.children:
                    traverse_for_identifiers(child, depth + 1)
            
            traverse_for_identifiers(root_node)
            
        except Exception as e:
            logger.debug(f"KotlinParser: Fallback extraction failed for {result.file_path}: {e}")

    def _parse_top_level_property(self, property_node: Node, result: ParsedFileResult):
        """Parse top-level property declarations."""
        name_node = property_node.child_by_field_name("name")
        type_node = property_node.child_by_field_name("type")
        
        if name_node:
            property_name = self._get_node_text(name_node)
            property_type = None
            if type_node:
                property_type = self._get_node_text(type_node)
                
            if property_name:
                # Check if it's mutable (var) or immutable (val)
                modifiers_node = property_node.child_by_field_name("modifiers")
                is_mutable = False
                if modifiers_node:
                    modifiers_text = self._get_node_text(modifiers_node)
                    is_mutable = "var" in modifiers_text if modifiers_text else False
                
                var_type_annotation = f"{'var' if is_mutable else 'val'} {property_type}" if property_type else ('var' if is_mutable else 'val')
                
                result.global_variables.append(ExtractedVariable(
                    name=property_name,
                    start_line=self._get_line_number(property_node),
                    end_line=self._get_end_line_number(property_node),
                    scope_name="global",
                    scope_type="global_variable",
                    var_type=var_type_annotation
                )) 