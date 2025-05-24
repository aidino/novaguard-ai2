# novaguard-backend/app/ckg_builder/parsers/javascript_parser.py
import logging
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from tree_sitter import Language, Parser, Node, Query # type: ignore
from tree_sitter_languages import get_language

from ..parsers import BaseCodeParser, ParsedFileResult, ExtractedFunction, ExtractedClass, ExtractedImport, ExtractedVariable

logger = logging.getLogger(__name__)

class JavaScriptParser(BaseCodeParser):
    """Parser for JavaScript and TypeScript files using tree-sitter."""

    QUERY_DEFINITIONS = {
        "imports_query": """
            [
              (import_statement) @import_node
              (import_statement
                source: (string) @import_source
              ) @import_with_source
            ]
        """,
        "exports_query": """
            [
              (export_statement) @export_node
              (export_statement
                value: (_) @export_value
              ) @export_with_value
            ]
        """,
        "definitions_query": """
            [
              (class_declaration) @definition_node
              (function_declaration) @definition_node
              (method_definition) @definition_node
              (arrow_function) @definition_node
              (variable_declarator
                name: (identifier) @var_name
                value: (arrow_function) @arrow_func
              ) @arrow_function_assignment
              (variable_declarator
                name: (identifier) @var_name
                value: (function_expression) @func_expr
              ) @function_expression_assignment
              (lexical_declaration
                (variable_declarator
                  name: (identifier) @global_var_name
                )
              ) @global_var_declaration
              (variable_declaration
                (variable_declarator
                  name: (identifier) @global_var_name
                )
              ) @global_var_declaration
            ]
        """,
        "body_assignments_query": """
            (assignment_expression
                left: (_) @assignment_target_node
                right: (_) @assignment_value_node
            ) @assignment_expr
        """,
        "body_identifiers_query": """
            (identifier) @id_node
        """,
        "body_calls_query": """
            (call_expression
                function: (_) @call_function_node
                arguments: (_) @call_arguments_node
            ) @call_expr
        """
    }

    def __init__(self, language_name: str = "javascript"):
        """Initialize JavaScript/TypeScript parser.
        
        Args:
            language_name: Either "javascript" or "typescript"
        """
        super().__init__(language_name)
        self.queries: Dict[str, Query] = {}
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"JavaScriptParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"JavaScriptParser: Error compiling query '{query_name}': {type(e).__name__} - {e}")

    def _get_query(self, query_name: str) -> Optional[Query]:
        return self.queries.get(query_name)

    def _parse_parameters_node(self, parameters_node: Optional[Node], owner_func_name: str) -> Tuple[List[ExtractedVariable], str]:
        """Parse function parameters from formal_parameters node."""
        parameters: List[ExtractedVariable] = []
        parameters_str = ""
        
        if not parameters_node:
            return parameters, parameters_str

        parameters_str = self._get_node_text(parameters_node) or ""
        
        for param_child in parameters_node.named_children:
            param_name = None
            param_type = None
            
            if param_child.type == "identifier":
                param_name = self._get_node_text(param_child)
            elif param_child.type == "required_parameter":
                # TypeScript required parameter
                pattern_node = param_child.child_by_field_name("pattern")
                type_node = param_child.child_by_field_name("type")
                if pattern_node and pattern_node.type == "identifier":
                    param_name = self._get_node_text(pattern_node)
                if type_node:
                    param_type = self._get_node_text(type_node)
            elif param_child.type == "optional_parameter":
                # TypeScript optional parameter
                pattern_node = param_child.child_by_field_name("pattern")
                type_node = param_child.child_by_field_name("type")
                if pattern_node and pattern_node.type == "identifier":
                    param_name = self._get_node_text(pattern_node)
                if type_node:
                    param_type = self._get_node_text(type_node)
            elif param_child.type == "rest_parameter":
                # Rest parameter (...args)
                pattern_node = param_child.child_by_field_name("pattern")
                if pattern_node and pattern_node.type == "identifier":
                    param_name = f"...{self._get_node_text(pattern_node)}"
                    
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
        """Extract function calls, variable usage, and local variable declarations from function body."""
        if not body_node:
            return

        # Extract function calls
        calls_query = self._get_query("body_calls_query")
        if calls_query:
            try:
                for pattern_idx, captures_dict in calls_query.matches(body_node):
                    call_node = captures_dict.get("call_expr")
                    func_node = captures_dict.get("call_function_node")
                    
                    if call_node and func_node:
                        call_line = self._get_line_number(call_node)
                        
                        # Extract function name
                        func_name = None
                        if func_node.type == "identifier":
                            func_name = self._get_node_text(func_node)
                        elif func_node.type == "member_expression":
                            # object.method() calls
                            property_node = func_node.child_by_field_name("property")
                            if property_node:
                                func_name = self._get_node_text(property_node)
                                
                        if func_name:
                            owner_function.calls.add((func_name, None, None, call_line))
                            
            except Exception as e:
                logger.error(f"JavaScriptParser: Error extracting calls from body: {e}")

        # Extract variable declarations
        for child in body_node.named_children:
            if child.type in ["lexical_declaration", "variable_declaration"]:
                self._extract_local_variables_from_declaration(child, owner_function)
            # Recursively process nested blocks
            elif child.type in ["block", "if_statement", "for_statement", "while_statement"]:
                self._extract_body_details(child, owner_function, result)

    def _extract_local_variables_from_declaration(self, declaration_node: Node, owner_function: ExtractedFunction):
        """Extract local variable declarations from var/let/const declarations."""
        for declarator in declaration_node.named_children:
            if declarator.type == "variable_declarator":
                name_node = declarator.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    var_name = self._get_node_text(name_node)
                    if var_name:
                        var_type = None
                        # Check for TypeScript type annotation
                        type_node = declarator.child_by_field_name("type")
                        if type_node:
                            var_type = self._get_node_text(type_node)
                            
                        owner_function.local_variables.append(ExtractedVariable(
                            name=var_name,
                            start_line=self._get_line_number(name_node),
                            end_line=self._get_end_line_number(name_node),
                            scope_name=owner_function.name,
                            scope_type="local_variable",
                            var_type=var_type,
                            is_parameter=False
                        ))

    def _parse_function_node(self, func_node: Node, result: ParsedFileResult, class_name: Optional[str] = None) -> Optional[ExtractedFunction]:
        """Parse function_declaration, method_definition, or arrow_function node."""
        try:
            func_name = None
            signature = None
            
            if func_node.type == "function_declaration":
                name_node = func_node.child_by_field_name("name")
                if name_node:
                    func_name = self._get_node_text(name_node)
                signature = self._get_node_text(func_node)
                
            elif func_node.type == "method_definition":
                key_node = func_node.child_by_field_name("key")
                if key_node:
                    func_name = self._get_node_text(key_node)
                signature = self._get_node_text(func_node)
                
            elif func_node.type in ["arrow_function", "function_expression"]:
                # For arrow functions assigned to variables, get name from context
                parent = func_node.parent
                if parent and parent.type == "variable_declarator":
                    name_node = parent.child_by_field_name("name")
                    if name_node:
                        func_name = self._get_node_text(name_node)
                else:
                    func_name = f"<anonymous_{self._get_line_number(func_node)}>"
                signature = self._get_node_text(func_node)
                
            if not func_name:
                logger.warning(f"JavaScriptParser: Could not extract function name from {func_node.type}")
                return None

            parameters_node = func_node.child_by_field_name("parameters")
            body_node = func_node.child_by_field_name("body")
            
            parameters, parameters_str = self._parse_parameters_node(parameters_node, func_name)
            
            extracted_function = ExtractedFunction(
                name=func_name,
                start_line=self._get_line_number(func_node),
                end_line=self._get_end_line_number(func_node),
                signature=signature,
                class_name=class_name,
                body_node=body_node,
                parameters_str=parameters_str
            )
            
            extracted_function.parameters = parameters
            self._extract_body_details(body_node, extracted_function, result)
            
            return extracted_function
            
        except Exception as e:
            logger.error(f"JavaScriptParser: Error parsing function node: {e}")
            return None

    def _parse_class_node(self, class_node: Node, result: ParsedFileResult) -> Optional[ExtractedClass]:
        """Parse class_declaration node."""
        try:
            name_node = class_node.child_by_field_name("name")
            if not name_node:
                logger.warning(f"JavaScriptParser: Class node without name at line {self._get_line_number(class_node)}")
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

            # Extract superclass
            superclass_node = class_node.child_by_field_name("superclass")
            if superclass_node:
                superclass_name = self._get_node_text(superclass_node)
                if superclass_name:
                    extracted_class.superclasses.add(superclass_name)

            # Extract methods and properties from class body
            if body_node:
                for child_node in body_node.named_children:
                    if child_node.type == "method_definition":
                        method = self._parse_function_node(child_node, result, class_name=class_name)
                        if method:
                            extracted_class.methods.append(method)
                    elif child_node.type == "field_definition":
                        # Class field/property
                        key_node = child_node.child_by_field_name("property")
                        if key_node and key_node.type == "property_identifier":
                            prop_name = self._get_node_text(key_node)
                            if prop_name:
                                prop_type = None
                                type_node = child_node.child_by_field_name("type")
                                if type_node:
                                    prop_type = self._get_node_text(type_node)
                                    
                                extracted_class.attributes.append(ExtractedVariable(
                                    name=prop_name,
                                    start_line=self._get_line_number(key_node),
                                    end_line=self._get_end_line_number(key_node),
                                    scope_name=class_name,
                                    scope_type="class_attribute",
                                    var_type=prop_type,
                                    is_parameter=False
                                ))

            return extracted_class
            
        except Exception as e:
            logger.error(f"JavaScriptParser: Error parsing class node: {e}")
            return None

    def _parse_import_statement_node(self, import_node: Node, result: ParsedFileResult) -> Optional[ExtractedImport]:
        """Parse import_statement node."""
        try:
            start_line = self._get_line_number(import_node)
            end_line = self._get_end_line_number(import_node)
            
            source_node = import_node.child_by_field_name("source")
            if not source_node:
                return None
                
            module_path = self._get_node_text(source_node)
            if module_path:
                # Remove quotes
                module_path = module_path.strip('"\'')
                
            imported_names: List[Tuple[str, Optional[str]]] = []
            import_type = "default"
            
            # Parse import clause
            import_clause = import_node.child_by_field_name("import")
            if import_clause:
                if import_clause.type == "import_specifier":
                    # Named import: import { name } from 'module'
                    name_node = import_clause.child_by_field_name("name")
                    if name_node:
                        imported_names.append((self._get_node_text(name_node), None))
                        import_type = "named"
                elif import_clause.type == "namespace_import":
                    # Namespace import: import * as name from 'module'
                    name_node = import_clause.child_by_field_name("name")
                    if name_node:
                        imported_names.append(("*", self._get_node_text(name_node)))
                        import_type = "namespace"
                elif import_clause.type == "identifier":
                    # Default import: import name from 'module'
                    imported_names.append((self._get_node_text(import_clause), None))
                    import_type = "default"

            return ExtractedImport(
                import_type=import_type,
                start_line=start_line,
                end_line=end_line,
                module_path=module_path,
                imported_names=imported_names,
                relative_level=1 if module_path and module_path.startswith('.') else 0
            )
            
        except Exception as e:
            logger.error(f"JavaScriptParser: Error parsing import statement: {e}")
            return None

    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        """Extract all entities from the AST root node."""
        
        # Extract imports
        imports_query = self._get_query("imports_query")
        if imports_query:
            try:
                for pattern_idx, captures_dict in imports_query.matches(root_node):
                    import_node = captures_dict.get("import_node")
                    if import_node:
                        extracted_import = self._parse_import_statement_node(import_node, result)
                        if extracted_import:
                            result.imports.append(extracted_import)
            except Exception as e:
                logger.error(f"JavaScriptParser: Error during import extraction: {e}")

        # Extract top-level definitions
        definitions_query = self._get_query("definitions_query")
        if definitions_query:
            try:
                for pattern_idx, captures_dict in definitions_query.matches(root_node):
                    
                    # Check what type of definition we found
                    if "definition_node" in captures_dict:
                        node = captures_dict["definition_node"]
                        
                        # Ensure this is a top-level definition
                        parent = node.parent
                        is_top_level = parent and parent.type == "program"
                        
                        if not is_top_level:
                            continue
                            
                        if node.type == "class_declaration":
                            cls = self._parse_class_node(node, result)
                            if cls:
                                result.classes.append(cls)
                        elif node.type in ["function_declaration", "method_definition"]:
                            func = self._parse_function_node(node, result)
                            if func:
                                result.functions.append(func)
                                
                    elif "global_var_declaration" in captures_dict:
                        decl_node = captures_dict["global_var_declaration"]
                        var_name_node = captures_dict.get("global_var_name")
                        
                        if var_name_node:
                            var_name = self._get_node_text(var_name_node)
                            if var_name and not any(gv.name == var_name for gv in result.global_variables):
                                var_type = None
                                # Check for TypeScript type annotation
                                parent_declarator = var_name_node.parent
                                if parent_declarator and parent_declarator.type == "variable_declarator":
                                    type_node = parent_declarator.child_by_field_name("type")
                                    if type_node:
                                        var_type = self._get_node_text(type_node)
                                        
                                result.global_variables.append(ExtractedVariable(
                                    name=var_name,
                                    start_line=self._get_line_number(var_name_node),
                                    end_line=self._get_end_line_number(var_name_node),
                                    scope_name=result.file_path,
                                    scope_type="global_variable",
                                    var_type=var_type,
                                    is_parameter=False
                                ))
                                
            except Exception as e:
                logger.error(f"JavaScriptParser: Error during definition extraction: {e}")

        logger.info(
            f"JavaScriptParser Extracted from {result.file_path}: "
            f"{len(result.imports)} imports, "
            f"{len(result.classes)} classes ("
            f"{sum(len(c.methods) for c in result.classes)} methods, "
            f"{sum(len(c.attributes) for c in result.classes)} class_attrs), "
            f"{len(result.functions)} global funcs, "
            f"{len(result.global_variables)} global vars."
        ) 