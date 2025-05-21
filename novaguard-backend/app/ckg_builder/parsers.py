# novaguard-backend/app/ckg_builder/parsers.py
import logging
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from tree_sitter import Language, Parser, Node, Query # type: ignore
from tree_sitter_languages import get_language

logger = logging.getLogger(__name__)

# --- Data Structures (Giữ nguyên như lần cập nhật trước) ---
class ExtractedVariable:
    def __init__(self, name: str, start_line: int, end_line: int,
                scope_name: str,
                scope_type: str, # e.g., "parameter", "local_variable", "global_variable", "class_attribute"
                var_type: Optional[str] = None,
                is_parameter: bool = False):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.scope_name = scope_name
        self.scope_type = scope_type
        self.var_type = var_type
        self.is_parameter = is_parameter

    def __repr__(self):
        return f"ExtractedVariable(name='{self.name}', scope='{self.scope_name}', type='{self.scope_type}')"

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
        self.decorators: List[str] = []
        self.raised_exceptions: Set[str] = set()
        self.handled_exceptions: Set[str] = set()
        self.uses_variables: Set[Tuple[str, int]] = set()
        self.modifies_variables: Set[Tuple[str, int, str]] = set()
        self.created_objects: Set[Tuple[str, int]] = set()

    def __repr__(self):
        return f"ExtractedFunction(name='{self.name}', class='{self.class_name}', lines={self.start_line}-{self.end_line})"

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

    def __repr__(self):
        return f"ExtractedClass(name='{self.name}', lines={self.start_line}-{self.end_line})"

class ExtractedImport:
    def __init__(self, import_type: str, start_line: int, end_line: int, module_path: Optional[str] = None, imported_names: Optional[List[Tuple[str, Optional[str]]]] = None, relative_level: int = 0):
        self.import_type = import_type
        self.start_line = start_line
        self.end_line = end_line
        self.module_path = module_path
        self.imported_names = imported_names if imported_names else []
        self.relative_level = relative_level

    def __repr__(self):
        return f"ExtractedImport(type='{self.import_type}', module='{self.module_path}', names='{self.imported_names}')"

class ParsedFileResult:
    def __init__(self, file_path: str, language: str):
        self.file_path = file_path
        self.language = language
        self.functions: List[ExtractedFunction] = []
        self.classes: List[ExtractedClass] = []
        self.imports: List[ExtractedImport] = []
        self.global_variables: List[ExtractedVariable] = []

    def __repr__(self):
        return f"ParsedFileResult(file='{self.file_path}', lang='{self.language}')"

class BaseCodeParser:
    # (Giữ nguyên như đã cung cấp trước đó)
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
                    for child_node in node.children:
                        if error_node_found: return
                        find_first_error_node(child_node)
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

    QUERY_DEFINITIONS = {
        # SỬA imports_query
        "imports_query": """
            [
              (import_statement) @import_node
              (import_from_statement) @import_node
            ]
        """,
        "definitions_query": """
            [
              (class_definition) @definition_node
              (function_definition) @definition_node
              (expression_statement
                (assignment
                  left: (identifier) @global_var_name_in_expr_stmt_ass
                )
              ) @global_assignment_in_expr_stmt
              (assignment
                left: (identifier) @global_var_name_in_direct_ass
              ) @direct_global_assignment
            ]
        """,
        "body_assignments_query": """
            (assignment
                left: (_) @assignment_target_node
                right: (_) @assignment_value_node
            ) @assignment_expr
        """,
        "body_augmented_assignments_query": """
            (augmented_assignment
                left: (_) @aug_assignment_target_node
                right: (_) @aug_assignment_value_node
            ) @aug_assignment_expr
        """,
        "body_identifiers_query": """
            (identifier) @id_node
        """,
        "body_calls_query": """
            (call
                function: (_) @call_function_node
                arguments: (_) @call_arguments_node
            ) @call_expr
        """
    }

    def __init__(self):
        super().__init__("python")
        self.queries: Dict[str, Query] = {}
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"PythonParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"PythonParser: CRITICAL - Error compiling query '{query_name}': {type(e).__name__} - {e}. This query will NOT be available.", exc_info=False)
        
        if not self.queries:
            logger.error("PythonParser initialized, but NO queries were compiled successfully. Parser will be largely ineffective.")
        elif len(self.queries) < len(self.QUERY_DEFINITIONS):
            logger.warning("PythonParser initialized with SOME query compilation errors. CKG features might be incomplete.")
        else:
            logger.info("PythonParser: All defined queries compiled successfully.")


    def _get_query(self, query_name: str) -> Optional[Query]:
        return self.queries.get(query_name)

    def _parse_decorators(self, node_with_decorators: Node) -> List[str]:
        # (Giữ nguyên logic)
        decorators = []
        for child in node_with_decorators.children:
            if child.type == "decorator":
                decorator_expr_node = child.child(0)
                if decorator_expr_node:
                    decorator_text = self._get_node_text(decorator_expr_node)
                    if decorator_expr_node.type == "call": 
                        func_node = decorator_expr_node.child_by_field_name("function")
                        if func_node:
                            decorator_text = self._get_node_text(func_node)
                    if decorator_text:
                        decorators.append(decorator_text)
        return decorators

    def _parse_parameters_node(self, parameters_node: Optional[Node], owner_func_name: str) -> Tuple[List[ExtractedVariable], str]:
        # (Giữ nguyên logic)
        params_list: List[ExtractedVariable] = []
        raw_params_text = self._get_node_text(parameters_node) if parameters_node else "()"

        if not parameters_node:
            return params_list, raw_params_text

        for child in parameters_node.children:
            param_name: Optional[str] = None
            param_type_hint: Optional[str] = None
            node_for_lines = child

            if child.type == "identifier":
                param_name = self._get_node_text(child)
            elif child.type == "typed_parameter":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node: param_name = self._get_node_text(name_node); node_for_lines = name_node
                if type_node: param_type_hint = self._get_node_text(type_node)
            elif child.type == "default_parameter":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node: param_name = self._get_node_text(name_node); node_for_lines = name_node
                if type_node: param_type_hint = self._get_node_text(type_node)
            elif child.type in ["list_splat_parameter", "list_splat_pattern", "splat_argument"]:
                id_node = child.child_by_field_name("name") or child.child(0)
                if id_node and id_node.type == "identifier":
                    param_name = "*" + self._get_node_text(id_node)
                    node_for_lines = id_node
                elif self._get_node_text(child) == "*":
                    continue
            elif child.type in ["dictionary_splat_parameter", "dictionary_splat_pattern", "keyword_argument"]:
                id_node = child.child_by_field_name("name") or child.child(0)
                if id_node and id_node.type == "identifier":
                    param_name = "**" + self._get_node_text(id_node)
                    node_for_lines = id_node
            elif child.type in ['(', ')', ',','keyword_separator', 'positional_separator']:
                continue

            if param_name:
                params_list.append(ExtractedVariable(
                    name=param_name,
                    start_line=self._get_line_number(node_for_lines),
                    end_line=self._get_end_line_number(node_for_lines),
                    scope_name=owner_func_name, scope_type="parameter",
                    var_type=param_type_hint, is_parameter=True
                ))
        return params_list, raw_params_text

    def _extract_body_details(self, body_node: Optional[Node], owner_function: ExtractedFunction, result: ParsedFileResult):
        # (Giữ nguyên logic như phiên bản sửa lỗi TypeError trước đó)
        if not body_node:
            return

        param_names = {p.name for p in owner_function.parameters}
        current_local_var_names = {lv.name for lv in owner_function.local_variables}

        assignment_query = self._get_query("body_assignments_query")
        if assignment_query:
            for pattern_idx, captures_dict in assignment_query.matches(body_node):
                assignment_expr_node = captures_dict.get("assignment_expr")
                target_node = captures_dict.get("assignment_target_node")
                value_node = captures_dict.get("assignment_value_node")

                if not assignment_expr_node or not target_node: continue
                line_num = self._get_line_number(assignment_expr_node)

                if target_node.type == "identifier":
                    var_name = self._get_node_text(target_node)
                    if var_name:
                        owner_function.modifies_variables.add((var_name, line_num, "assignment"))
                        if var_name not in param_names and var_name not in current_local_var_names:
                            owner_function.local_variables.append(ExtractedVariable(
                                name=var_name, start_line=self._get_line_number(target_node),
                                end_line=self._get_end_line_number(target_node),
                                scope_name=owner_function.name, scope_type="local_variable"
                            ))
                            current_local_var_names.add(var_name)
                elif target_node.type == "attribute":
                    obj_node = target_node.child_by_field_name("object")
                    attr_node = target_node.child_by_field_name("attribute")
                    obj_name = self._get_node_text(obj_node)
                    attr_name = self._get_node_text(attr_node)
                    if obj_name and attr_name:
                        full_attr_name = f"{obj_name}.{attr_name}"
                        owner_function.modifies_variables.add((full_attr_name, line_num, "attribute_assignment"))
                
                if value_node:
                    self._find_used_identifiers(value_node, owner_function, param_names, current_local_var_names, result)
        
        aug_assignment_query = self._get_query("body_augmented_assignments_query")
        if aug_assignment_query:
            for pattern_idx, captures_dict in aug_assignment_query.matches(body_node):
                aug_expr_node = captures_dict.get("aug_assignment_expr")
                target_node = captures_dict.get("aug_assignment_target_node")
                value_node = captures_dict.get("aug_assignment_value_node")

                if not aug_expr_node or not target_node: continue
                line_num = self._get_line_number(aug_expr_node)
                
                target_name_aug: Optional[str] = None
                if target_node.type == "identifier":
                    target_name_aug = self._get_node_text(target_node)
                elif target_node.type == "attribute":
                    obj_node = target_node.child_by_field_name("object")
                    attr_node = target_node.child_by_field_name("attribute")
                    obj_name = self._get_node_text(obj_node)
                    attr_name = self._get_node_text(attr_node)
                    if obj_name and attr_name:
                        target_name_aug = f"{obj_name}.{attr_name}"
                
                if target_name_aug:
                    owner_function.modifies_variables.add((target_name_aug, line_num, "augmented_assignment"))
                    owner_function.uses_variables.add((target_name_aug, line_num))

                if value_node:
                    self._find_used_identifiers(value_node, owner_function, param_names, current_local_var_names, result)

        call_query = self._get_query("body_calls_query")
        if call_query:
            for pattern_idx, captures_dict in call_query.matches(body_node):
                call_expr_node = captures_dict.get("call_expr")
                function_node = captures_dict.get("call_function_node")
                arguments_node = captures_dict.get("call_arguments_node")

                if not call_expr_node or not function_node: continue
                line_num = self._get_line_number(call_expr_node)

                if arguments_node:
                    self._find_used_identifiers(arguments_node, owner_function, param_names, current_local_var_names, result)

                called_name_str: Optional[str] = None
                base_object_name_str: Optional[str] = None
                call_type = "unknown_call"

                if function_node.type == "identifier":
                    called_name_str = self._get_node_text(function_node)
                    if called_name_str and any(c.name == called_name_str for c in result.classes):
                        call_type = "constructor_call"
                        owner_function.created_objects.add((called_name_str, line_num))
                    else:
                        is_imported_class_constructor = False
                        if called_name_str:
                            for imp_item in result.imports:
                                if imp_item.import_type.startswith("from"):
                                    for name_orig, name_alias in imp_item.imported_names:
                                        actual_imp_name = name_alias if name_alias else name_orig
                                        if actual_imp_name == called_name_str and actual_imp_name[0].isupper():
                                            owner_function.created_objects.add((actual_imp_name, line_num))
                                            is_imported_class_constructor = True; call_type = "constructor_call_imported_from"; break
                                if is_imported_class_constructor: break
                        if not is_imported_class_constructor:
                            call_type = "direct_function_call"

                elif function_node.type == "attribute":
                    base_obj_node = function_node.child_by_field_name("object")
                    attr_method_node = function_node.child_by_field_name("attribute")
                    base_object_name_str = self._get_node_text(base_obj_node)
                    called_name_str = self._get_node_text(attr_method_node)

                    if base_object_name_str == "self": call_type = "instance_method_call"
                    elif owner_function.class_name and base_object_name_str == owner_function.class_name: call_type = "class_method_call_on_own_class"
                    elif base_object_name_str and any(c.name == base_object_name_str for c in result.classes):
                        call_type = "class_method_call_on_other_class"
                        if called_name_str and called_name_str[0].isupper():
                             owner_function.created_objects.add((called_name_str, line_num))
                    else: 
                        call_type = "method_call_on_object"
                        is_constructor_via_module = False
                        if base_object_name_str and called_name_str and called_name_str[0].isupper():
                            for imp_item in result.imports: 
                                if imp_item.import_type == "direct" or imp_item.import_type == "direct_alias":
                                    for name_orig, name_alias in imp_item.imported_names:
                                        actual_mod_name = name_alias if name_alias else name_orig
                                        if actual_mod_name == base_object_name_str:
                                            owner_function.created_objects.add((called_name_str, line_num))
                                            is_constructor_via_module = True; call_type = "constructor_call_module_attr"; break
                                    if is_constructor_via_module: break
                        if is_constructor_via_module and base_object_name_str: 
                             owner_function.uses_variables.add((base_object_name_str, line_num))
                elif function_node.type == "subscript":
                    called_name_str = self._get_node_text(function_node)
                    base_sub_node = function_node.child_by_field_name("value")
                    base_object_name_str = self._get_node_text(base_sub_node)
                    call_type = "subscripted_call"
                else:
                    called_name_str = self._get_node_text(function_node)
                    call_type = f"complex_call_{function_node.type}"

                if called_name_str:
                    owner_function.calls.add((called_name_str, base_object_name_str, call_type, line_num))
        
        id_query = self._get_query("body_identifiers_query")
        if id_query:
            for pattern_idx, captures_dict in id_query.matches(body_node):
                id_node = captures_dict.get("id_node")
                if id_node:
                    var_name = self._get_node_text(id_node)
                    if self._is_variable_usage_context(id_node, var_name, owner_function, param_names, current_local_var_names, result):
                        owner_function.uses_variables.add((var_name, self._get_line_number(id_node)))

    def _is_variable_usage_context(self, id_node: Node, var_name: Optional[str],
                                   owner_function: ExtractedFunction,
                                   param_names: Set[str],
                                   local_var_names: Set[str],
                                   result: ParsedFileResult) -> bool:
        # (Giữ nguyên logic)
        if not var_name or var_name == "self": return False
        parent = id_node.parent
        if not parent: return False
        if parent.type == "function_definition" and parent.child_by_field_name("name") == id_node: return False
        if parent.type == "class_definition" and parent.child_by_field_name("name") == id_node: return False
        if parent.type in ["parameters", "typed_parameter", "default_parameter"] and \
           (parent.child_by_field_name("name") == id_node or (parent.type == "identifier" and parent == id_node and parent.parent and parent.parent.type in ["parameters", "typed_parameter", "default_parameter"])): return False
        grandparent = parent.parent
        if parent.type == "assignment" and parent.child_by_field_name("left") == id_node: return False
        if parent.type == "augmented_assignment" and parent.child_by_field_name("left") == id_node: return False
        if parent.type == "for_in_clause" and parent.child_by_field_name("left") == id_node: return False
        if parent.type == "with_item" and parent.child_by_field_name("alias") == id_node: return False
        if parent.type == "attribute" and parent.child_by_field_name("attribute") == id_node: return False
        if parent.type == "call" and parent.child_by_field_name("function") == id_node: return False
        if parent.type == "decorator": return False
        if grandparent and grandparent.type == "decorator" and parent.type == "call" and parent.child_by_field_name("function") == id_node : return False
        if parent.type == "aliased_import" and parent.child_by_field_name("alias") == id_node: return False
        if parent.type == "dotted_name" and parent.parent and parent.parent.type == "aliased_import" and parent.parent.child_by_field_name("name") == parent : return False
        if parent.type == "dotted_name" and parent.parent and parent.parent.type == "import_statement": return False
        if parent.type == "dotted_name" and parent.parent and parent.parent.type == "import_from_statement" and parent.parent.child_by_field_name("module") == parent : return False
        if any(c.name == var_name for c in result.classes): return False
        if any(f.name == var_name for f in result.functions): return False
        return True

    def _find_used_identifiers(self, node: Node, owner_function: ExtractedFunction,
                               param_names: Set[str], local_var_names: Set[str], result: ParsedFileResult):
        # (Giữ nguyên logic)
        if node.type == 'identifier':
            var_name = self._get_node_text(node)
            if self._is_variable_usage_context(node, var_name, owner_function, param_names, local_var_names, result):
                 owner_function.uses_variables.add((var_name, self._get_line_number(node)))
        for child_idx in range(node.child_count):
            child = node.child(child_idx)
            if child:
                 self._find_used_identifiers(child, owner_function, param_names, local_var_names, result)

    def _parse_function_node(self, func_node: Node, result: ParsedFileResult, class_name: Optional[str] = None) -> Optional[ExtractedFunction]:
        # (Giữ nguyên logic)
        try:
            name_node = func_node.child_by_field_name("name")
            func_name = self._get_node_text(name_node)
            if not func_name: return None
            parameters_node = func_node.child_by_field_name("parameters")
            params_list, params_str = self._parse_parameters_node(parameters_node, func_name)
            return_type_node = func_node.child_by_field_name("return_type")
            return_type_str = self._get_node_text(return_type_node)
            signature = f"{params_str}" + (f" -> {return_type_str}" if return_type_str else "")
            body_node = func_node.child_by_field_name("body")
            extracted_func = ExtractedFunction(
                name=func_name, start_line=self._get_line_number(func_node),
                end_line=self._get_end_line_number(func_node), signature=signature.strip(),
                parameters_str=params_str.strip(), class_name=class_name, body_node=body_node
            )
            extracted_func.parameters = params_list
            extracted_func.decorators = self._parse_decorators(func_node)
            self._extract_body_details(body_node, extracted_func, result)
            return extracted_func
        except Exception as e:
            logger.error(f"PythonParser: Error parsing function '{self._get_node_text(func_node.child_by_field_name('name'))}' in {result.file_path}: {e}", exc_info=True)
            return None

    def _parse_class_node(self, class_node: Node, result: ParsedFileResult) -> Optional[ExtractedClass]:
        # (Giữ nguyên logic)
        try:
            name_node = class_node.child_by_field_name("name")
            class_name = self._get_node_text(name_node)
            if not class_name: return None
            body_node = class_node.child_by_field_name("body")
            extracted_class = ExtractedClass(
                name=class_name, start_line=self._get_line_number(class_node),
                end_line=self._get_end_line_number(class_node), body_node=body_node
            )
            extracted_class.decorators = self._parse_decorators(class_node)
            superclasses_node = class_node.child_by_field_name("superclasses")
            if superclasses_node:
                for sc_expr_node in superclasses_node.children:
                    if sc_expr_node.type not in ['(', ')', ',']:
                        sc_name = self._get_node_text(sc_expr_node)
                        if sc_name: extracted_class.superclasses.add(sc_name)
            if body_node:
                for child_node in body_node.children:
                    assignment_node_for_attr = None
                    if child_node.type == "expression_statement" and child_node.child(0) and child_node.child(0).type == "assignment":
                        assignment_node_for_attr = child_node.child(0)
                    elif child_node.type == "assignment":
                        assignment_node_for_attr = child_node
                    elif child_node.type == "typed_assignment":
                        assignment_node_for_attr = child_node
                    if assignment_node_for_attr:
                        left_node = assignment_node_for_attr.child_by_field_name("left")
                        attr_type_str_class: Optional[str] = None
                        if assignment_node_for_attr.type == "typed_assignment":
                            type_node = assignment_node_for_attr.child_by_field_name("type")
                            attr_type_str_class = self._get_node_text(type_node)
                        if left_node and left_node.type == "identifier":
                            attr_name = self._get_node_text(left_node)
                            if attr_name and not any(attr.name == attr_name for attr in extracted_class.attributes):
                                 extracted_class.attributes.append(ExtractedVariable(
                                    name=attr_name, start_line=self._get_line_number(left_node),
                                    end_line=self._get_end_line_number(left_node),
                                    scope_name=class_name, scope_type="class_attribute", var_type=attr_type_str_class
                                ))
                    elif child_node.type == "function_definition":
                        method = self._parse_function_node(child_node, result, class_name=class_name)
                        if method: extracted_class.methods.append(method)
            return extracted_class
        except Exception as e:
            logger.error(f"PythonParser: Error parsing class '{self._get_node_text(class_node.child_by_field_name('name'))}' in {result.file_path}: {e}", exc_info=True)
            return None

    def _parse_import_statement_node(self, import_node: Node, result: ParsedFileResult) -> Optional[ExtractedImport]:
        # (Giữ nguyên logic)
        start_line = self._get_line_number(import_node)
        end_line = self._get_end_line_number(import_node)
        imported_names_list: List[Tuple[str, Optional[str]]] = []
        for name_node in import_node.named_children:
            if name_node.type == "dotted_name":
                module_path = self._get_node_text(name_node)
                if module_path: imported_names_list.append((module_path, None))
            elif name_node.type == "aliased_import":
                original_name_node = name_node.child_by_field_name("name")
                alias_node = name_node.child_by_field_name("alias")
                if original_name_node:
                    module_path = self._get_node_text(original_name_node)
                    alias_text = self._get_node_text(alias_node)
                    if module_path: imported_names_list.append((module_path, alias_text))
        if imported_names_list:
            main_module_path_for_object = imported_names_list[0][0]
            import_type = "direct_alias" if any(alias for _, alias in imported_names_list) else "direct"
            return ExtractedImport(
                import_type=import_type, start_line=start_line, end_line=end_line,
                module_path=main_module_path_for_object, imported_names=imported_names_list
            )
        return None

    def _parse_import_from_statement_node(self, import_from_node: Node, result: ParsedFileResult) -> Optional[ExtractedImport]:
        # (Giữ nguyên logic)
        try:
            start_line = self._get_line_number(import_from_node)
            end_line = self._get_end_line_number(import_from_node)
            module_path_text: Optional[str] = None
            imported_items_list: List[Tuple[str, Optional[str]]] = []
            relative_level = 0
            module_node = import_from_node.child_by_field_name("module")
            if module_node:
                if module_node.type == "dotted_name":
                    module_path_text = self._get_node_text(module_node)
                elif module_node.type == "relative_import":
                    path_parts: List[str] = []
                    for child_rel in module_node.children:
                        if child_rel.type == ".": relative_level += 1
                        elif child_rel.field_name == "name" and (child_rel.type == "identifier" or child_rel.type == "dotted_name"):
                            part = self._get_node_text(child_rel)
                            if part: path_parts.append(part)
                    if path_parts: module_path_text = ("." * relative_level) + ".".join(path_parts)
                    elif relative_level > 0: module_path_text = "." * relative_level
            name_field_node = import_from_node.child_by_field_name("name")
            import_type = "from"
            if name_field_node:
                if name_field_node.type == "wildcard_import":
                    imported_items_list.append(("*", None)); import_type = "from_wildcard"
                elif name_field_node.type == "import_list":
                    has_alias = False
                    for item_node in name_field_node.named_children:
                        if item_node.type == "dotted_name" or item_node.type == "identifier":
                            if name := self._get_node_text(item_node): imported_items_list.append((name, None))
                        elif item_node.type == "aliased_import":
                            original_name_node = item_node.child_by_field_name("name")
                            alias_node = item_node.child_by_field_name("alias")
                            if original_name_node:
                                if orig_name := self._get_node_text(original_name_node):
                                    imported_items_list.append((orig_name, self._get_node_text(alias_node))); has_alias = True
                    if has_alias: import_type = "from_alias"
            if module_path_text is not None and (imported_items_list or import_type == "from_wildcard"):
                return ExtractedImport(
                    import_type=import_type, start_line=start_line, end_line=end_line,
                    module_path=module_path_text, imported_names=imported_items_list,
                    relative_level=relative_level )
            return None
        except Exception as e:
            logger.error(f"PythonParser: Error parsing import_from_statement_node at L{self._get_line_number(import_from_node)} in {result.file_path}: {e}", exc_info=True)
            return None

    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        # SỬA LỖI TypeError và NameError: Dùng query.matches() và dict access cho captures
        imports_query = self._get_query("imports_query")
        if imports_query:
            try:
                for pattern_idx, captures_dict in imports_query.matches(root_node):
                    node = captures_dict.get("import_node") 
                    if node:
                        extracted_import = None
                        if node.type == "import_statement":
                            extracted_import = self._parse_import_statement_node(node, result)
                        elif node.type == "import_from_statement":
                            extracted_import = self._parse_import_from_statement_node(node, result)
                        if extracted_import:
                            result.imports.append(extracted_import)
            except Exception as e:
                logger.error(f"PythonParser: Error during import extraction main loop in {result.file_path}: {e}", exc_info=True)

        definitions_query = self._get_query("definitions_query")
        if definitions_query:
            try:
                for pattern_idx, captures_dict in definitions_query.matches(root_node):
                    node_type_key = None
                    if "definition_node" in captures_dict: node_type_key = "definition_node"
                    elif "global_assignment_in_expr_stmt" in captures_dict: node_type_key = "global_assignment_in_expr_stmt"
                    elif "direct_global_assignment" in captures_dict: node_type_key = "direct_global_assignment"
                    
                    node = captures_dict.get(node_type_key) if node_type_key else None
                    if not node: continue

                    parent = node.parent
                    is_top_level = parent and (parent.type == "module" or
                                            (parent.type == "block" and parent.parent and parent.parent.type == "module"))
                    if not is_top_level: continue

                    if node.type == "class_definition":
                        cls = self._parse_class_node(node, result)
                        if cls: result.classes.append(cls)
                    elif node.type == "function_definition":
                        func = self._parse_function_node(node, result, class_name=None)
                        if func: result.functions.append(func)
                    elif node.type == "expression_statement" and node_type_key == "global_assignment_in_expr_stmt":
                        var_name_node = captures_dict.get("global_var_name_in_expr_stmt_ass")
                        if var_name_node:
                            var_name = self._get_node_text(var_name_node)
                            if var_name and not any(gv.name == var_name for gv in result.global_variables):
                                result.global_variables.append(ExtractedVariable(
                                    name=var_name, start_line=self._get_line_number(var_name_node),
                                    end_line=self._get_end_line_number(var_name_node),
                                    scope_name=result.file_path, scope_type="global_variable" ))
                    elif node.type == "assignment" and node_type_key == "direct_global_assignment":
                        var_name_node = captures_dict.get("global_var_name_in_direct_ass")
                        if var_name_node:
                            var_name = self._get_node_text(var_name_node)
                            if var_name and not any(gv.name == var_name for gv in result.global_variables):
                                result.global_variables.append(ExtractedVariable(
                                    name=var_name, start_line=self._get_line_number(var_name_node),
                                    end_line=self._get_end_line_number(var_name_node),
                                    scope_name=result.file_path, scope_type="global_variable" ))
            except Exception as e:
                logger.error(f"PythonParser: Error during top-level entity extraction in {result.file_path}: {e}", exc_info=True)

        logger.info(
             f"PythonParser Extracted from {result.file_path}: "
             f"{len(result.imports)} imports, "
             f"{len(result.classes)} classes ("
             f"{sum(len(c.methods) for c in result.classes)} methods, "
             f"{sum(len(c.attributes) for c in result.classes)} class_attrs), "
             f"{len(result.functions)} global funcs, "
             f"{len(result.global_variables)} global vars."
        )
        for func_item in result.functions + [method for cls in result.classes for method in cls.methods]:
            if func_item.uses_variables or func_item.modifies_variables or func_item.created_objects:
                 logger.debug(f"  Func '{func_item.class_name + '.' if func_item.class_name else ''}{func_item.name}': "
                              f"Uses({len(func_item.uses_variables)}) {list(func_item.uses_variables)[:3]}, "
                              f"Mods({len(func_item.modifies_variables)}) {list(func_item.modifies_variables)[:3]}, "
                              f"Creates({len(func_item.created_objects)}) {list(func_item.created_objects)[:3]}")


_parsers_cache: Dict[str, BaseCodeParser] = {}
def get_code_parser(language: str) -> Optional[BaseCodeParser]:
    # (Giữ nguyên logic)
    language_key = language.lower().strip()
    if not language_key:
        logger.warning("get_code_parser called with empty language string.")
        return None
    parser_instance: Optional[BaseCodeParser] = None
    if language_key == "python":
        try:
            parser_instance = PythonParser()
            if isinstance(parser_instance, PythonParser):
                 if parser_instance.QUERY_DEFINITIONS and not parser_instance.queries :
                    logger.error(f"PythonParser for '{language_key}' initialized, but NO queries were compiled. Parser will be ineffective.")
                 elif parser_instance.QUERY_DEFINITIONS and len(parser_instance.queries) < len(parser_instance.QUERY_DEFINITIONS):
                    logger.warning(f"PythonParser for '{language_key}' initialized with SOME query compilation errors. Results may be incomplete.")
        except Exception as e:
            logger.error(f"Failed to instantiate PythonParser for '{language_key}' due to: {type(e).__name__} - {e}", exc_info=True)
            return None
    else:
        logger.warning(f"No specific parser class implemented for language: '{language}'.")
        return None
    return parser_instance