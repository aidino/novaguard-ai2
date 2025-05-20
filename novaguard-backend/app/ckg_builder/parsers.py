# novaguard-backend/app/ckg_builder/parsers.py
import logging
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from tree_sitter import Language, Parser, Node, Query # type: ignore
from tree_sitter_languages import get_language

logger = logging.getLogger(__name__)

# --- Data Structures (Giữ nguyên) ---
class ExtractedVariable:
    def __init__(self, name: str, start_line: int, end_line: int,
                scope_name: str,
                scope_type: str,
                var_type: Optional[str] = None,
                is_parameter: bool = False):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.scope_name = scope_name
        self.scope_type = scope_type
        self.var_type = var_type
        self.is_parameter = is_parameter

class ExtractedFunction:
    def __init__(self, name: str, start_line: int, end_line: int, signature: Optional[str] = None, class_name: Optional[str] = None, body_node: Optional[Node] = None, parameters_str: Optional[str] = None):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.signature = signature
        self.parameters_str = parameters_str
        self.class_name = class_name
        self.body_node = body_node
        self.calls: Set[Tuple[str, Optional[str], Optional[str], int]] = set()
        self.parameters: List[ExtractedVariable] = []
        self.local_variables: List[ExtractedVariable] = []
        self.global_variables_accessed: Set[str] = set()
        self.nonlocal_variables_accessed: Set[str] = set()
        self.attributes_read: Set[Tuple[Optional[str], str]] = set()
        self.attributes_written: Set[Tuple[Optional[str], str]] = set()
        self.decorators: List[str] = []
        self.raised_exceptions: Set[str] = set()
        self.handled_exceptions: Set[str] = set()
        self.data_flows: List[Dict[str, Any]] = []

class ExtractedClass:
    def __init__(self, name: str, start_line: int, end_line: int, body_node: Optional[Node] = None):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.body_node = body_node
        self.methods: List[ExtractedFunction] = []
        self.superclasses: Set[str] = set()
        self.attributes: List[ExtractedVariable] = []
        self.decorators: List[str] = []

class ExtractedImport:
    def __init__(self, import_type: str, start_line: int, end_line: int, module_path: Optional[str] = None, imported_names: Optional[List[Tuple[str, Optional[str]]]] = None, relative_level: int = 0):
        self.import_type = import_type
        self.start_line = start_line
        self.end_line = end_line
        self.module_path = module_path
        self.imported_names = imported_names if imported_names else []
        self.relative_level = relative_level

class ParsedFileResult:
    def __init__(self, file_path: str, language: str):
        self.file_path = file_path
        self.language = language
        self.functions: List[ExtractedFunction] = []
        self.classes: List[ExtractedClass] = []
        self.imports: List[ExtractedImport] = []
        self.global_variables: List[ExtractedVariable] = []

class BaseCodeParser:
    def __init__(self, language_name: str):
        self.language_name = language_name
        try:
            self.lang_object: Language = get_language(language_name)
            self.parser: Parser = Parser()
            self.parser.set_language(self.lang_object)
            logger.info(f"Tree-sitter parser for '{language_name}' initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to load tree-sitter language grammar for '{language_name}': {e}. ")
            raise ValueError(f"Could not initialize parser for {language_name}") from e

    def parse(self, code_content: str, file_path: str) -> Optional[ParsedFileResult]:
        if not self.parser or not self.lang_object:
            logger.error(f"Parser for {self.language_name} not properly initialized for file {file_path}.")
            return None
        try:
            tree = self.parser.parse(bytes(code_content, "utf8"))
            result = ParsedFileResult(file_path=file_path, language=self.language_name)

            if tree.root_node.has_error:
                error_node_found = False
                first_error_node_info = "Unknown error location"
                def find_first_error_node(node: Node):
                    nonlocal error_node_found, first_error_node_info
                    if error_node_found: return
                    if node.type == 'ERROR' or node.is_missing:
                        error_node_found = True
                        first_error_node_info = f"type: {node.type}, line: {self._get_line_number(node)}"
                        return
                    for child in node.children:
                        if error_node_found: return
                        find_first_error_node(child)

                find_first_error_node(tree.root_node)
                logger.warning(
                    f"Syntax errors found in file {file_path} during parsing (e.g., near {first_error_node_info}). "
                    f"CKG data might be incomplete or inaccurate."
                )
            self._extract_entities(tree.root_node, result)
            return result
        except Exception as e:
            logger.error(f"Error parsing file {file_path} with {self.language_name} parser: {e}", exc_info=True)
            return None

    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        raise NotImplementedError("Subclasses must implement _extract_entities")

    def _get_node_text(self, node: Optional[Node]) -> Optional[str]:
        return node.text.decode('utf8').strip() if node and node.text else None

    def _get_line_number(self, node: Node) -> int:
        return node.start_point[0] + 1

    def _get_end_line_number(self, node: Node) -> int:
        return node.end_point[0] + 1

class PythonParser(BaseCodeParser):

    # Định nghĩa các query strings ở đây để dễ quản lý
    QUERY_DEFINITIONS = {
        "imports": """
            (import_statement
                name: [
                    (dotted_name) @module_path
                    (aliased_import
                        name: (dotted_name) @module_path_in_alias
                        alias: (identifier) @alias)
                ]
            ) @import_direct_statement

            (import_from_statement
                module: [ 
                    (dotted_name) @from_module_path 
                    (relative_import 
                        ("." @relative_dots)+
                        name:? (dotted_name) @relative_module_name_part 
                    ) @captured_relative_import
                ]
                name: [ 
                    (wildcard_import) @wildcard
                    (import_list) @import_list_node
                ]
            ) @import_from_statement
        """,
        "classes": """
            (class_definition
                name: (identifier) @class.name
                superclasses:? (argument_list . (_) @superclass)
                body: (block) @class.body
                decorator: (decorator)* @class.decorator_list
            ) @class.definition
        """,
        "functions_and_methods": """
            (function_definition
                name: (identifier) @function.name
                parameters: (parameters) @function.parameters_node
                return_type:? (type) @function.return_type
                body: (block) @function.body
                decorator: (decorator)* @function.decorator_list
            ) @function.definition
        """,
        "calls": """
            (call
                function: [
                    (identifier) @func_name_direct
                    (attribute object: (_) @base_obj attribute: (identifier) @method_name)
                    (subscript object: (_) @base_obj_subscript index: (_) @subscript_index)
                ]
                arguments: (argument_list) @arguments_node
            ) @call_expression
        """,
        "assignments_and_declarations": """
            [
                (assignment
                    left: [
                        (identifier) @var.name.assigned
                        (attribute object: (_) @obj_name attribute: (identifier) @attr.name.assigned)
                        (subscript) @subscript.assigned
                    ]
                    right: (_) @assigned_value
                    type:? (type) @var.type_hint_assigned
                ) @assignment_expr

                (expression_statement
                    (assignment
                        left: (identifier) @var.name.assigned
                        type: (type) @var.type_hint_assigned
                    )
                ) @typed_variable_no_assignment_stmt

                (typed_parameter name: (identifier) @param.name type: (type) @param.type) @param_def
                (default_parameter name: (identifier) @param.name type:? (type) @param.type value: (_)) @default_param_def

                (global_statement (identifier) @global.var.name) @global_stmt
                (nonlocal_statement (identifier) @nonlocal.var.name) @nonlocal_stmt

                (for_statement
                    left: [
                        (identifier) @loop.var.name
                        (tuple_pattern (identifier) @loop.var.name_in_tuple *)
                    ]
                ) @for_loop
                
                (with_statement
                    (with_clause
                        (with_item
                            value: (_) @with_expr
                            alias:? (as_pattern target: (identifier) @with.alias.name)
                        )
                    )
                ) @with_stmt
            ]
        """,
        "variable_reads": """
            [
                (identifier) @var.read
                (attribute object: (_) @base_obj.read attribute: (identifier) @attr.read)
            ]
        """,
        "exceptions": """
            (raise_statement (expression_list . (_) @raised_exception_expr)?) @raise_stmt
            (try_statement
                body: (block) @try_body
                (except_clause
                    type:? [
                        (expression_list . (_) @handled_exception_type_in_list)
                        (identifier) @handled_exception_type_direct
                        (attribute) @handled_exception_type_attr
                        (tuple . (_) @handled_exception_in_tuple_item)
                    ]
                    alias?: (as_pattern target: (identifier) @handled_exception_alias)
                    body: (block) @except_body
                )* @except_clauses
                else_clause?: (else_clause body: (block) @else_body) @else_clause
                finally_clause?: (finally_clause body: (block) @finally_body) @finally_clause
            ) @try_stmt
        """
    }

    def __init__(self):
        super().__init__("python")
        self.queries: Dict[str, Query] = {} # Khởi tạo là dict rỗng
        
        has_compilation_error = False
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"PythonParser: Query '{query_name}' compiled successfully.")
            except SyntaxError as se:
                logger.error(f"PythonParser: SyntaxError compiling query '{query_name}': {se}. This query will be skipped.", exc_info=False) # Log lỗi cụ thể
                has_compilation_error = True
            except Exception as e:
                logger.error(f"PythonParser: Unexpected error compiling query '{query_name}': {e}. This query will be skipped.", exc_info=True)
                has_compilation_error = True
        
        if has_compilation_error:
            logger.warning("PythonParser initialized with one or more query compilation errors. Some CKG features might be incomplete.")
        else:
            logger.info("PythonParser: All queries compiled successfully.")

    def _get_query(self, query_name: str) -> Optional[Query]:
        """Helper to safely get a compiled query."""
        query = self.queries.get(query_name)
        if not query:
            logger.warning(f"PythonParser: Query '{query_name}' was not compiled successfully or does not exist. Skipping extraction that depends on it.")
            return None
        return query

    def _process_match_item(self, query_obj: Query, match_as_tuple: Any,
                                main_capture_names_without_at: List[str]) -> Tuple[Optional[Node], Dict[str, List[Node]]]:
        # (Giữ nguyên logic của _process_match_item)
        if not (isinstance(match_as_tuple, tuple) and len(match_as_tuple) == 2):
            return None, {}
        _pattern_index, captures_map_from_iterator = match_as_tuple
        if not isinstance(captures_map_from_iterator, dict):
            return None, {}

        main_node: Optional[Node] = None
        validated_captures_map: Dict[str, List[Node]] = {}

        for raw_capture_key, captured_value in captures_map_from_iterator.items():
            if not isinstance(raw_capture_key, str):
                continue

            nodes_list_for_key: List[Node] = []
            if isinstance(captured_value, Node):
                nodes_list_for_key = [captured_value]
            elif isinstance(captured_value, list) and all(isinstance(n, Node) for n in captured_value):
                nodes_list_for_key = captured_value
            else:
                continue 

            normalized_key = raw_capture_key[1:] if raw_capture_key.startswith('@') else raw_capture_key

            if normalized_key in validated_captures_map:
                validated_captures_map[normalized_key].extend(nodes_list_for_key)
            else:
                validated_captures_map[normalized_key] = nodes_list_for_key

            if main_capture_names_without_at and normalized_key in main_capture_names_without_at:
                if nodes_list_for_key and main_node is None: 
                    main_node = nodes_list_for_key[0]
        return main_node, validated_captures_map
    
    def _extract_imports(self, root_node: Node, result: ParsedFileResult):
        query_obj = self._get_query("imports")
        if not query_obj: return

        processed_statement_node_ids = set()
        try:
            for match_as_tuple in query_obj.matches(root_node):
                main_statement_node, captures_dict = self._process_match_item(
                    query_obj, match_as_tuple, ["import_direct_statement", "import_from_statement"]
                )
                if not main_statement_node or main_statement_node.id in processed_statement_node_ids:
                    continue
                processed_statement_node_ids.add(main_statement_node.id)
                start_line = self._get_line_number(main_statement_node)
                end_line = self._get_end_line_number(main_statement_node)

                if main_statement_node.type == "import_statement":
                    module_path_nodes = captures_dict.get("module_path", [])
                    alias_nodes = captures_dict.get("alias", [])
                    module_path_in_alias_nodes = captures_dict.get("module_path_in_alias", [])

                    actual_module_path_text: Optional[str] = None
                    if module_path_nodes:
                        actual_module_path_text = self._get_node_text(module_path_nodes[0])
                    elif module_path_in_alias_nodes:
                        actual_module_path_text = self._get_node_text(module_path_in_alias_nodes[0])

                    alias_text = self._get_node_text(alias_nodes[0]) if alias_nodes else None
                    import_type = "direct_alias" if alias_text and actual_module_path_text else "direct"
                    imported_names_list = [(actual_module_path_text, alias_text)] if actual_module_path_text else []

                    if actual_module_path_text:
                        result.imports.append(ExtractedImport(
                            import_type=import_type, start_line=start_line, end_line=end_line,
                            module_path=actual_module_path_text, imported_names=imported_names_list
                        ))

                elif main_statement_node.type == "import_from_statement":
                    from_module_path_text: Optional[str] = None
                    relative_level = 0
                    
                    if "from_module_path" in captures_dict and captures_dict["from_module_path"]:
                        from_module_path_text = self._get_node_text(captures_dict["from_module_path"][0])
                    elif "captured_relative_import" in captures_dict and captures_dict["captured_relative_import"]:
                        relative_import_node = captures_dict["captured_relative_import"][0]
                        
                        dot_nodes = []
                        # query_obj ở đây là self.queries['imports']
                        for cap_idx, node_in_cap in query_obj.captures(relative_import_node):
                            cap_name_str = query_obj.string_value_for_id(cap_idx) # Lấy tên string của capture
                            if cap_name_str == "relative_dots":
                                dot_nodes.append(node_in_cap)
                        relative_level = len(dot_nodes)

                        module_prefix = "." * relative_level
                        
                        name_part_nodes = []
                        for cap_idx, node_in_cap in query_obj.captures(relative_import_node):
                             cap_name_str = query_obj.string_value_for_id(cap_idx)
                             if cap_name_str == "relative_module_name_part":
                                name_part_nodes.append(node_in_cap)
                        
                        relative_part_name = self._get_node_text(name_part_nodes[0]) if name_part_nodes else None

                        if relative_part_name:
                            from_module_path_text = module_prefix + relative_part_name
                        elif relative_level > 0: 
                            from_module_path_text = module_prefix 

                    imported_items_list: List[Tuple[str, Optional[str]]] = []
                    import_type = "from"

                    if "wildcard" in captures_dict:
                        imported_items_list.append(("*", None))
                        import_type = "from_wildcard"
                    elif "import_list_node" in captures_dict and captures_dict["import_list_node"]:
                        import_list_node = captures_dict["import_list_node"][0]
                        for item_node in import_list_node.named_children:
                            if item_node.type == "dotted_name" or item_node.type == "identifier":
                                if name := self._get_node_text(item_node):
                                    imported_items_list.append((name, None))
                            elif item_node.type == "aliased_import":
                                original_name_node = item_node.child_by_field_name("name")
                                alias_node = item_node.child_by_field_name("alias")
                                if original_name_node:
                                    if orig_name := self._get_node_text(original_name_node):
                                        imported_items_list.append((orig_name, self._get_node_text(alias_node)))
                    
                    final_module_path = from_module_path_text
                    if from_module_path_text is None and relative_level > 0:
                        final_module_path = "." * relative_level # e.g. from . import X

                    if final_module_path is not None and (imported_items_list or import_type == "from_wildcard"):
                        result.imports.append(ExtractedImport(
                            import_type=import_type, start_line=start_line, end_line=end_line,
                            module_path=final_module_path, imported_names=imported_items_list,
                            relative_level=relative_level
                        ))
                    else:
                        logger.warning(f"PythonParser: Could not fully determine 'from' import at L{start_line} in {result.file_path}. Path: '{final_module_path}', Level: {relative_level}, Items: {len(imported_items_list)}")
        except Exception as e:
            logger.error(f"PythonParser: Error extracting imports from {result.file_path}: {e}", exc_info=True)

    def _extract_calls(self, scope_node: Node, current_owner_entity: ExtractedFunction, result: ParsedFileResult):
        query_obj_calls = self._get_query("calls")
        if not query_obj_calls or not scope_node : return
        
        processed_call_node_ids = set()
        try:
            for match_as_tuple in query_obj_calls.matches(scope_node):
                call_expression_node, captures_dict = self._process_match_item(
                    query_obj_calls, match_as_tuple, ["call_expression"]
                )
                if not call_expression_node or call_expression_node.id in processed_call_node_ids:
                    continue
                processed_call_node_ids.add(call_expression_node.id)

                function_being_called_node = call_expression_node.child_by_field_name("function")
                if not function_being_called_node: continue

                call_type = "unknown_call"
                called_name_str: Optional[str] = None
                base_object_name_str: Optional[str] = None
                call_site_line = self._get_line_number(call_expression_node)

                if function_being_called_node.type == "identifier":
                    called_name_str = self._get_node_text(function_being_called_node)
                    call_type = "direct_function_call"
                    if called_name_str and any(c.name == called_name_str for c in result.classes):
                        call_type = "constructor_call"
                elif function_being_called_node.type == "attribute":
                    base_obj_node = function_being_called_node.child_by_field_name("object")
                    method_name_node = function_being_called_node.child_by_field_name("attribute")
                    called_name_str = self._get_node_text(method_name_node)
                    if base_obj_node:
                        base_object_name_str = self._get_node_text(base_obj_node)
                        if base_object_name_str == "self":
                            call_type = "instance_method_call"
                        elif current_owner_entity.class_name and base_object_name_str == current_owner_entity.class_name:
                            call_type = "class_method_call_on_own_class"
                        elif any(c.name == base_object_name_str for c in result.classes):
                            call_type = "class_method_call_on_other_class"
                        else:
                            call_type = "method_call_on_object"
                elif function_being_called_node.type == "subscript":
                    called_name_str = self._get_node_text(function_being_called_node) 
                    obj_node = function_being_called_node.child_by_field_name("object")
                    if obj_node:
                        base_object_name_str = self._get_node_text(obj_node)
                    call_type = "subscripted_call"
                else: 
                    called_name_str = self._get_node_text(function_being_called_node)
                    call_type = f"complex_call_{function_being_called_node.type}"

                if called_name_str:
                    current_owner_entity.calls.add(
                        (called_name_str, base_object_name_str, call_type, call_site_line)
                    )
        except Exception as e:
            logger.error(f"PythonParser: Error extracting calls in '{current_owner_entity.name}' from {result.file_path}: {e}", exc_info=True)

    def _extract_functions_and_methods(self, scope_node: Node, result: ParsedFileResult,
                                    current_class_obj: Optional[ExtractedClass] = None,
                                    is_global_scope: bool = False):
        query_obj_funcs = self._get_query("functions_and_methods")
        if not query_obj_funcs or not scope_node: return
        
        processed_func_def_node_ids = set()
        try:
            for match_as_tuple in query_obj_funcs.matches(scope_node):
                func_def_node, captures_dict = self._process_match_item(query_obj_funcs, match_as_tuple, ["function.definition"])
                if not func_def_node or func_def_node.id in processed_func_def_node_ids: continue
                processed_func_def_node_ids.add(func_def_node.id)

                is_valid_scope = False
                if current_class_obj: 
                    if func_def_node.parent and func_def_node.parent == scope_node: 
                        is_valid_scope = True
                elif is_global_scope: 
                    if func_def_node.parent and (func_def_node.parent == scope_node or \
                       (func_def_node.parent.type == 'block' and func_def_node.parent.parent == scope_node)):
                        is_valid_scope = True
                if not is_valid_scope: continue

                func_name_nodes = captures_dict.get("function.name", [])
                func_name = self._get_node_text(func_name_nodes[0]) if func_name_nodes else None
                if not func_name:
                    logger.warning(f"PythonParser: Could not extract function name at line {self._get_line_number(func_def_node)} in {result.file_path}")
                    continue

                params_nodes = captures_dict.get("function.parameters_node", [])
                params_node = params_nodes[0] if params_nodes else None
                extracted_parameters = self._extract_parameters(params_node, func_name) if params_node else []
                params_str = self._get_node_text(params_node) if params_node else "()"

                return_type_nodes = captures_dict.get("function.return_type", [])
                return_type_str = self._get_node_text(return_type_nodes[0]) if return_type_nodes else None

                body_nodes = captures_dict.get("function.body", [])
                func_body_node = body_nodes[0] if body_nodes else None

                func_decorators_nodes = captures_dict.get("function.decorator_list", [])
                func_decorators = [self._get_node_text(dec.child(0)) for dec in func_decorators_nodes if dec.child(0) and self._get_node_text(dec.child(0))]

                signature = f"{params_str}" + (f" -> {return_type_str}" if return_type_str else "")
                func_obj = ExtractedFunction(
                    name=func_name,
                    start_line=self._get_line_number(func_def_node),
                    end_line=self._get_end_line_number(func_def_node),
                    signature=signature.strip(),
                    parameters_str=params_str.strip(),
                    class_name=current_class_obj.name if current_class_obj else None,
                    body_node=func_body_node
                )
                func_obj.parameters = extracted_parameters
                func_obj.decorators = func_decorators

                if func_body_node:
                    self._extract_calls(func_body_node, func_obj, result)
                    self._extract_variables_and_assignments(func_body_node, result, func_obj, "method" if current_class_obj else "function")
                    self._extract_exceptions(func_body_node, result, func_obj)

                if current_class_obj:
                    current_class_obj.methods.append(func_obj)
                elif is_global_scope:
                    result.functions.append(func_obj)
        except Exception as e:
            owner_name = current_class_obj.name if current_class_obj else "global scope"
            logger.error(f"PythonParser: Error extracting functions/methods in '{owner_name}' from {result.file_path}: {e}", exc_info=True)

    def _extract_classes(self, root_node: Node, result: ParsedFileResult):
        query_obj_classes = self._get_query("classes")
        if not query_obj_classes: return
        
        processed_class_def_node_ids = set()
        try:
            for match_as_tuple in query_obj_classes.matches(root_node):
                class_def_node, captures_dict = self._process_match_item(query_obj_classes, match_as_tuple, ["class.definition"])
                if not class_def_node or class_def_node.id in processed_class_def_node_ids: continue
                processed_class_def_node_ids.add(class_def_node.id)

                if not (class_def_node.parent and (class_def_node.parent == root_node or \
                    (class_def_node.parent.type == 'block' and class_def_node.parent.parent == root_node))):
                    continue

                class_name_nodes = captures_dict.get("class.name", [])
                class_name = self._get_node_text(class_name_nodes[0]) if class_name_nodes else None
                if not class_name:
                    logger.warning(f"PythonParser: Could not extract class name at line {self._get_line_number(class_def_node)} in {result.file_path}")
                    continue

                body_nodes = captures_dict.get("class.body", [])
                class_body_node = body_nodes[0] if body_nodes else None
                
                superclasses_nodes = captures_dict.get("superclass", [])
                superclasses_set = {text for sc_node in superclasses_nodes if (text := self._get_node_text(sc_node))}

                class_decorators_nodes = captures_dict.get("class.decorator_list", [])
                class_decorators = [self._get_node_text(dec.child(0)) for dec in class_decorators_nodes if dec.child(0) and self._get_node_text(dec.child(0))]

                class_obj = ExtractedClass(
                    name=class_name,
                    start_line=self._get_line_number(class_def_node),
                    end_line=self._get_end_line_number(class_def_node),
                    body_node=class_body_node
                )
                class_obj.superclasses = superclasses_set
                class_obj.decorators = class_decorators

                if class_body_node: 
                    self._extract_functions_and_methods(class_body_node, result, class_obj, False) # Methods
                    self._extract_variables_and_assignments(class_body_node, result, class_obj, "class") # Class attributes
                    self._extract_exceptions(class_body_node, result, class_obj) # Exceptions defined/handled in class body (less common)
                result.classes.append(class_obj)
        except Exception as e:
            logger.error(f"PythonParser: Error extracting classes from {result.file_path}: {e}", exc_info=True)

    def _extract_variables_and_assignments(
        self, scope_node: Node, result: ParsedFileResult,
        current_owner_entity: Optional[Union[ExtractedFunction, ExtractedClass]] = None,
        scope_type: str = "unknown"
    ):
        query_obj = self._get_query("assignments_and_declarations")
        if not query_obj or not scope_node: return
        
        newly_extracted_vars: List[ExtractedVariable] = []
        owner_name_for_scope = current_owner_entity.name if current_owner_entity else result.file_path

        try:
            for match_as_tuple in query_obj.matches(scope_node):
                main_capture_names = ["assignment_expr", "typed_variable_no_assignment_stmt", "global_stmt", "nonlocal_stmt", "for_loop", "with_stmt"]
                statement_node, captures_dict = self._process_match_item(query_obj, match_as_tuple, main_capture_names)

                if not statement_node: continue

                if statement_node.type == "global_statement":
                    if isinstance(current_owner_entity, ExtractedFunction):
                        for gvar_node in captures_dict.get("global.var.name", []):
                            if name := self._get_node_text(gvar_node):
                                current_owner_entity.global_variables_accessed.add(name)
                    continue
                if statement_node.type == "nonlocal_statement":
                    if isinstance(current_owner_entity, ExtractedFunction):
                        for nlvar_node in captures_dict.get("nonlocal.var.name", []):
                            if name := self._get_node_text(nlvar_node):
                                current_owner_entity.nonlocal_variables_accessed.add(name)
                    continue

                var_name: Optional[str] = None
                var_type_hint_text: Optional[str] = None
                var_scope_type_detail: str = scope_type 
                node_for_lines: Optional[Node] = None
                attribute_owner_name: Optional[str] = None

                if statement_node.type == "assignment" or \
                   (statement_node.type == "expression_statement" and statement_node.child_count > 0 and statement_node.child(0) and statement_node.child(0).type == "assignment"):
                    
                    actual_assignment_node = statement_node if statement_node.type == "assignment" else statement_node.child(0)
                    if not actual_assignment_node: continue

                    left_node = actual_assignment_node.child_by_field_name("left")
                    type_hint_node = actual_assignment_node.child_by_field_name("type") 
                    var_type_hint_text = self._get_node_text(type_hint_node)

                    if not left_node: continue
                    node_for_lines = left_node

                    if left_node.type == "identifier":
                        var_name = self._get_node_text(left_node)
                        if scope_type == "file": var_scope_type_detail = "global_variable"
                        elif scope_type in ["function", "method"]: var_scope_type_detail = "local_variable"
                        elif scope_type == "class": var_scope_type_detail = "class_attribute"
                    elif left_node.type == "attribute":
                        obj_node = left_node.child_by_field_name("object")
                        attr_node = left_node.child_by_field_name("attribute")
                        var_name = self._get_node_text(attr_node)
                        attribute_owner_name = self._get_node_text(obj_node)

                        if isinstance(current_owner_entity, ExtractedFunction):
                            if attribute_owner_name == "self":
                                var_scope_type_detail = "instance_attribute"
                                current_owner_entity.attributes_written.add((attribute_owner_name, var_name) if var_name else ("", ""))
                            elif current_owner_entity.class_name and attribute_owner_name == current_owner_entity.class_name:
                                var_scope_type_detail = "class_attribute" 
                                current_owner_entity.attributes_written.add((attribute_owner_name, var_name) if var_name else ("", ""))
                            else: 
                                current_owner_entity.attributes_written.add((attribute_owner_name, var_name) if var_name else ("", ""))
                                continue 
                        elif isinstance(current_owner_entity, ExtractedClass): 
                            if attribute_owner_name == current_owner_entity.name:
                                var_scope_type_detail = "class_attribute"
                            else:
                                continue
                
                elif statement_node.type == "expression_statement" and \
                     captures_dict.get("var.name.assigned") and captures_dict.get("var.type_hint_assigned") and \
                     not captures_dict.get("assigned_value"): 
                    
                    var_name_node_list = captures_dict.get("var.name.assigned", [])
                    type_hint_node_list = captures_dict.get("var.type_hint_assigned", [])

                    if var_name_node_list and type_hint_node_list:
                        var_name = self._get_node_text(var_name_node_list[0])
                        var_type_hint_text = self._get_node_text(type_hint_node_list[0])
                        node_for_lines = var_name_node_list[0]
                        if scope_type in ["function", "method"]: var_scope_type_detail = "local_variable"
                        elif scope_type == "class": var_scope_type_detail = "class_attribute" 
                        elif scope_type == "file": var_scope_type_detail = "global_variable"

                elif statement_node.type == "for_statement":
                    loop_var_nodes = captures_dict.get("loop.var.name", []) + captures_dict.get("loop.var.name_in_tuple", [])
                    if isinstance(current_owner_entity, ExtractedFunction):
                        for l_var_node in loop_var_nodes:
                            if name := self._get_node_text(l_var_node):
                                if not any(v.name == name for v in current_owner_entity.local_variables): 
                                    newly_extracted_vars.append(ExtractedVariable(
                                        name=name, start_line=self._get_line_number(l_var_node),
                                        end_line=self._get_end_line_number(l_var_node),
                                        scope_name=owner_name_for_scope, scope_type="local_variable"
                                    ))
                    continue 

                elif statement_node.type == "with_statement":
                    if with_alias_nodes := captures_dict.get("with.alias.name", []):
                        if isinstance(current_owner_entity, ExtractedFunction):
                            if name := self._get_node_text(with_alias_nodes[0]):
                                if not any(v.name == name for v in current_owner_entity.local_variables): 
                                    newly_extracted_vars.append(ExtractedVariable(
                                        name=name, start_line=self._get_line_number(with_alias_nodes[0]),
                                        end_line=self._get_end_line_number(with_alias_nodes[0]),
                                        scope_name=owner_name_for_scope, scope_type="local_variable"
                                    ))
                    continue 

                if var_name and node_for_lines:
                    is_duplicate = False
                    if var_scope_type_detail == "local_variable" and isinstance(current_owner_entity, ExtractedFunction):
                        if any(v.name == var_name for v in current_owner_entity.local_variables): is_duplicate = True
                    elif var_scope_type_detail == "class_attribute" and isinstance(current_owner_entity, ExtractedClass):
                        if any(attr.name == var_name for attr in current_owner_entity.attributes): is_duplicate = True
                    elif var_scope_type_detail == "global_variable" and scope_type == "file":
                        if any(g_var.name == var_name for g_var in result.global_variables): is_duplicate = True
                    
                    if not is_duplicate:
                        newly_extracted_vars.append(ExtractedVariable(
                            name=var_name,
                            start_line=self._get_line_number(node_for_lines),
                            end_line=self._get_end_line_number(node_for_lines),
                            scope_name=attribute_owner_name or owner_name_for_scope, 
                            scope_type=var_scope_type_detail,
                            var_type=var_type_hint_text
                        ))
        except Exception as e:
            logger.error(f"PythonParser: Error extracting variables/assignments in '{owner_name_for_scope}' from {result.file_path}: {e}", exc_info=True)

        for var_obj in newly_extracted_vars:
            if var_obj.scope_type == "local_variable" and isinstance(current_owner_entity, ExtractedFunction):
                current_owner_entity.local_variables.append(var_obj)
            elif var_obj.scope_type == "class_attribute" and isinstance(current_owner_entity, ExtractedClass):
                current_owner_entity.attributes.append(var_obj)
            elif var_obj.scope_type == "global_variable" and scope_type == "file": 
                result.global_variables.append(var_obj)
    
    def _extract_exceptions(
        self, scope_node: Node, result: ParsedFileResult,
        current_owner_entity: Optional[Union[ExtractedFunction, ExtractedClass]] = None
    ):
        query_obj = self._get_query("exceptions")
        if not query_obj or not scope_node or not isinstance(current_owner_entity, (ExtractedFunction, ExtractedClass)): return
        
        processed_exception_nodes = set()
        try:
            for match_as_tuple in query_obj.matches(scope_node):
                main_expr_node, captures_dict = self._process_match_item(query_obj, match_as_tuple, ["raise_stmt", "try_stmt"])
                if not main_expr_node or main_expr_node.id in processed_exception_nodes: continue
                processed_exception_nodes.add(main_expr_node.id)

                if main_expr_node.type == "raise_statement":
                    if isinstance(current_owner_entity, ExtractedFunction): 
                        if raised_expr_nodes := captures_dict.get("raised_exception_expr", []):
                            if raised_expr_nodes[0]: 
                                name_node = raised_expr_nodes[0]
                                name_to_add: Optional[str] = None
                                if name_node.type == "identifier":
                                    name_to_add = self._get_node_text(name_node)
                                elif name_node.type == "call":
                                    func_node = name_node.child_by_field_name("function")
                                    if func_node: name_to_add = self._get_node_text(func_node)
                                elif name_node.type == "attribute":
                                    name_to_add = self._get_node_text(name_node) 
                                if name_to_add:
                                    current_owner_entity.raised_exceptions.add(name_to_add)
                elif main_expr_node.type == "try_statement":
                    if try_body_node := main_expr_node.child_by_field_name("body"):
                        self._extract_exceptions(try_body_node, result, current_owner_entity)

                    for except_clause_node in main_expr_node.children_by_field_name("except_clause"):
                        if isinstance(current_owner_entity, ExtractedFunction): 
                            type_field_node = except_clause_node.child_by_field_name("type")
                            if type_field_node:
                                if type_field_node.type == "tuple":
                                    for child_in_tuple in type_field_node.named_children:
                                        if name := self._get_node_text(child_in_tuple):
                                            current_owner_entity.handled_exceptions.add(name)
                                elif type_field_node.type == "expression_list": 
                                    for child_in_list in type_field_node.named_children:
                                        if name := self._get_node_text(child_in_list): 
                                            current_owner_entity.handled_exceptions.add(name)
                                elif type_field_node.type in ["identifier", "attribute"]:
                                    if name := self._get_node_text(type_field_node):
                                        current_owner_entity.handled_exceptions.add(name)
                            if not type_field_node: 
                                current_owner_entity.handled_exceptions.add("AnyException") 
                        
                        if except_body_node := except_clause_node.child_by_field_name("body"):
                            self._extract_exceptions(except_body_node, result, current_owner_entity)
                    
                    if else_clause_node := main_expr_node.child_by_field_name("else_clause"):
                        if else_body_node := else_clause_node.child_by_field_name("body"):
                             self._extract_exceptions(else_body_node, result, current_owner_entity)
                    if finally_clause_node := main_expr_node.child_by_field_name("finally_clause"):
                        if finally_body_node := finally_clause_node.child_by_field_name("body"):
                             self._extract_exceptions(finally_body_node, result, current_owner_entity)
        except Exception as e:
            logger.error(f"PythonParser: Error extracting exceptions in '{current_owner_entity.name if current_owner_entity else 'unknown scope'}' from {result.file_path}: {e}", exc_info=True)

    def _extract_parameters(self, parameters_node: Optional[Node], owner_func_name: str) -> List[ExtractedVariable]:
        extracted_params: List[ExtractedVariable] = []
        if not parameters_node: return extracted_params
        try:
            for param_child_node in parameters_node.children: 
                param_name_str: Optional[str] = None
                param_type_str: Optional[str] = None
                node_for_lines: Node = param_child_node 
                node_type = param_child_node.type

                if node_type == "identifier": 
                    param_name_str = self._get_node_text(param_child_node)
                elif node_type == "typed_parameter": 
                    name_node = param_child_node.child_by_field_name("name")
                    type_node = param_child_node.child_by_field_name("type")
                    if name_node: param_name_str = self._get_node_text(name_node)
                    if type_node: param_type_str = self._get_node_text(type_node)
                    if name_node: node_for_lines = name_node 
                elif node_type == "default_parameter": 
                    name_node = param_child_node.child_by_field_name("name")
                    type_node = param_child_node.child_by_field_name("type") 
                    if name_node: param_name_str = self._get_node_text(name_node)
                    if type_node: param_type_str = self._get_node_text(type_node)
                    if name_node: node_for_lines = name_node
                elif node_type in ["list_splat_parameter", "list_splat_pattern"]: 
                    name_node = param_child_node.child_by_field_name("name")
                    if not name_node: 
                        for child in param_child_node.children:
                            if child.type == "identifier": name_node = child; break
                    if name_node: param_name_str = "*" + self._get_node_text(name_node) if self._get_node_text(name_node) else None
                    elif self._get_node_text(param_child_node) == '*': continue 
                    if name_node: node_for_lines = name_node
                elif node_type in ["dictionary_splat_parameter", "dictionary_splat_pattern"]: 
                    name_node = param_child_node.child_by_field_name("name")
                    if not name_node:
                         for child in param_child_node.children:
                            if child.type == "identifier": name_node = child; break
                    if name_node: param_name_str = "**" + self._get_node_text(name_node) if self._get_node_text(name_node) else None
                    if name_node: node_for_lines = name_node
                elif node_type == "keyword_separator": 
                    continue
                elif node_type == "positional_separator": 
                    continue
                elif node_type in ['(', ')', ',']: 
                    continue
                
                if param_name_str:
                    extracted_params.append(ExtractedVariable(
                        name=param_name_str,
                        start_line=self._get_line_number(node_for_lines),
                        end_line=self._get_end_line_number(node_for_lines),
                        scope_name=owner_func_name,
                        scope_type="parameter",
                        var_type=param_type_str,
                        is_parameter=True
                    ))
        except Exception as e:
             logger.error(f"PythonParser: Error extracting parameters for '{owner_func_name}': {e}", exc_info=True)
        return extracted_params
        
    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        # Các lệnh gọi _extract_* sẽ tự kiểm tra xem query tương ứng có tồn tại không
        self._extract_imports(root_node, result)
        self._extract_variables_and_assignments(root_node, result, current_owner_entity=None, scope_type="file")
        self._extract_classes(root_node, result) 
        self._extract_functions_and_methods(root_node, result, current_class_obj=None, is_global_scope=True)
        
        logger.debug(
            f"PythonParser Extracted from {result.file_path}: "
            f"{len(result.imports)} imports, "
            f"{len(result.classes)} classes ("
            f"{sum(len(c.methods) for c in result.classes if c.methods)} methods), "
            f"{len(result.functions)} global functions, "
            f"{len(result.global_variables)} global variables."
        )

_parsers_cache: Dict[str, BaseCodeParser] = {}
def get_code_parser(language: str) -> Optional[BaseCodeParser]:
    language_key = language.lower().strip()
    if not language_key:
        logger.warning("get_code_parser called with empty language string.")
        return None

    if language_key in _parsers_cache:
        parser = _parsers_cache[language_key]
        # Kiểm tra xem parser có query nào không, nếu không có nghĩa là có lỗi lúc init
        if isinstance(parser, PythonParser) and not parser.queries:
             logger.warning(f"Returning cached PythonParser for '{language_key}' but it had query compilation errors. Re-attempting instantiation might be needed if code changed.")
        return parser


    parser_instance: Optional[BaseCodeParser] = None
    if language_key == "python":
        try:
            parser_instance = PythonParser()
            # Sau khi khởi tạo, kiểm tra xem có query nào được compile thành công không
            if not parser_instance.queries: # type: ignore
                logger.error(f"PythonParser for '{language_key}' initialized, but no queries were compiled successfully. Parser will be ineffective.")
                # Quyết định xem có nên trả về parser lỗi hay không
                # return None # Hoặc trả về để CKGBuilder log "No parser for lang"
        except Exception as e: 
            logger.error(f"Failed to instantiate PythonParser for '{language_key}' due to: {type(e).__name__} - {e}", exc_info=True)
            return None 
    else:
        logger.warning(f"No specific parser class implemented for language: '{language}'.")
        return None

    if parser_instance: 
        _parsers_cache[language_key] = parser_instance
    return parser_instance