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
        self.decorators: List[str] = []
        self.raised_exceptions: Set[str] = set()
        self.handled_exceptions: Set[str] = set()

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
    # (Giữ nguyên BaseCodeParser)
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
        """
    }

    def __init__(self):
        super().__init__("python")
        self.queries: Dict[str, Query] = {}
        
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.info(f"PythonParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"PythonParser: CRITICAL - Error compiling query '{query_name}': {type(e).__name__} - {e}. This query will NOT be available.", exc_info=False)
        
        if not self.queries:
            logger.error("PythonParser initialized, but NO queries were compiled successfully. Parser will be largely ineffective.")
        elif len(self.queries) < len(self.QUERY_DEFINITIONS):
            logger.warning("PythonParser initialized with SOME query compilation errors. CKG features might be incomplete.")
        else:
            logger.info("PythonParser: All defined queries compiled successfully.")

    def _get_query(self, query_name: str) -> Optional[Query]:
        query = self.queries.get(query_name)
        if not query:
            logger.debug(f"PythonParser: Query '{query_name}' is not available (likely failed compilation).")
        return query
    
    
    def _parse_decorators(self, node_with_decorators: Node) -> List[str]:
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
        if not body_node:
            return

        # 1. Trích xuất Local Variables (assignments đơn giản) - giữ lại logic cũ
        assignment_query_str = "(assignment left: (identifier) @var_name)" # Query này an toàn
        try:
            assignment_query = self.lang_object.query(assignment_query_str)
            for match_tuple in assignment_query.matches(body_node):
                if not match_tuple or not match_tuple[1]: continue
                var_name_node = match_tuple[1].get("var_name")
                if var_name_node:
                    var_name_text = self._get_node_text(var_name_node)
                    if var_name_text and not any(p.name == var_name_text for p in owner_function.parameters):
                        if not any(lv.name == var_name_text for lv in owner_function.local_variables):
                            owner_function.local_variables.append(ExtractedVariable(
                                name=var_name_text,
                                start_line=self._get_line_number(var_name_node),
                                end_line=self._get_end_line_number(var_name_node),
                                scope_name=owner_function.name,
                                scope_type="local_variable"
                            ))
        except Exception as e:
            logger.warning(f"PythonParser: Error querying basic assignments in '{owner_function.name}' of {result.file_path}: {e}")


        # 2. Trích xuất Function Calls
        # Sử dụng (call_expression) vì đây là tên node chuẩn hơn, (call) là alias trong 1 số grammar.
        # Tuy nhiên, để an toàn hơn, chúng ta có thể thử cả hai hoặc kiểm tra grammar.
        # Với tree-sitter-python, (call) là node chính cho một function call expression.
        call_query_str = "(call) @call_node" 
        call_query: Optional[Query] = None
        try:
            call_query = self.lang_object.query(call_query_str)
            logger.debug(f"PythonParser: Call query for '{owner_function.name}' compiled successfully.")
        except Exception as e:
            logger.warning(f"PythonParser: CRITICAL - Failed to compile CALL query ('{call_query_str}') in '{owner_function.name}' of {result.file_path}: {type(e).__name__} - {e}. Call extraction will be skipped for this function.")
            # Không log exc_info ở đây nữa để tránh quá nhiều log nếu lỗi này lặp lại
            # exc_info=True
            return # Thoát khỏi _extract_body_details nếu query call không compile được

        if call_query and body_node: # Đảm bảo body_node cũng tồn tại
            processed_call_ids = set() # Để tránh xử lý trùng lặp nếu query phức tạp hơn sau này
            try:
                for match_tuple in call_query.matches(body_node): # Duyệt các match
                    if not match_tuple or not match_tuple[1]: continue
                    
                    call_node = match_tuple[1].get("call_node")
                    if not call_node or call_node.id in processed_call_ids:
                        continue
                    processed_call_ids.add(call_node.id)

                    function_part_node = call_node.child_by_field_name("function")
                    if not function_part_node:
                        continue

                    called_name_str: Optional[str] = None
                    base_object_name_str: Optional[str] = None
                    call_type = "unknown_call"
                    call_site_line = self._get_line_number(call_node)
                    
                    # Phân tích phần "function" của call_node
                    if function_part_node.type == "identifier":
                        called_name_str = self._get_node_text(function_part_node)
                        call_type = "direct_function_call"
                        # Heuristic for constructor calls (kiểm tra trong danh sách class đã parse của file)
                        if called_name_str and any(c.name == called_name_str for c in result.classes):
                            call_type = "constructor_call"
                    elif function_part_node.type == "attribute": # obj.method or Class.method
                        # child_by_field_name an toàn hơn child(index)
                        obj_node = function_part_node.child_by_field_name("object")
                        attr_node = function_part_node.child_by_field_name("attribute")
                        
                        called_name_str = self._get_node_text(attr_node) # Tên method
                        base_object_name_str = self._get_node_text(obj_node) # Tên object/class

                        if base_object_name_str == "self":
                            call_type = "instance_method_call"
                        elif owner_function.class_name and base_object_name_str == owner_function.class_name:
                             call_type = "class_method_call_on_own_class"
                        # Kiểm tra xem có phải là gọi method của class khác đã biết không
                        elif base_object_name_str and any(c.name == base_object_name_str for c in result.classes):
                            call_type = "class_method_call_on_other_class"
                        else:
                            call_type = "method_call_on_object"
                    # Thêm các trường hợp khác nếu cần: subscript (e.g., my_dict["func"]())
                    elif function_part_node.type == "subscript":
                        # Lấy toàn bộ text của subscript làm "tên hàm được gọi"
                        called_name_str = self._get_node_text(function_part_node)
                        # Lấy đối tượng bị subscript
                        obj_node = function_part_node.child_by_field_name("object")
                        if obj_node : base_object_name_str = self._get_node_text(obj_node)
                        call_type = "subscripted_call"
                    else:
                        # Trường hợp phức tạp khác, ví dụ (lambda x:x)()
                        called_name_str = self._get_node_text(function_part_node) # Lấy text của toàn bộ phần function
                        call_type = f"complex_call_{function_part_node.type}"


                    if called_name_str:
                        call_tuple = (called_name_str, base_object_name_str, call_type, call_site_line)
                        owner_function.calls.add(call_tuple)
            except Exception as e_match:
                logger.warning(f"PythonParser: Error processing call matches in '{owner_function.name}' of {result.file_path}: {e_match}", exc_info=True)

    def _parse_function_node(self, func_node: Node, result: ParsedFileResult, class_name: Optional[str] = None) -> Optional[ExtractedFunction]:
        # (Giữ nguyên logic, đảm bảo gọi _extract_body_details)
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
                name=func_name,
                start_line=self._get_line_number(func_node),
                end_line=self._get_end_line_number(func_node),
                signature=signature.strip(), parameters_str=params_str.strip(),
                class_name=class_name, body_node=body_node
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
                name=class_name,
                start_line=self._get_line_number(class_node),
                end_line=self._get_end_line_number(class_node),
                body_node=body_node
            )
            extracted_class.decorators = self._parse_decorators(class_node)

            superclasses_node = class_node.child_by_field_name("superclasses")
            if superclasses_node: 
                for sc_expr_node in superclasses_node.children:
                    if sc_expr_node.type not in ['(', ')', ',']:
                        sc_name = self._get_node_text(sc_expr_node)
                        if sc_name: extracted_class.superclasses.add(sc_name)
            
            if body_node:
                for child in body_node.named_children:
                    if child.type == "function_definition":
                        method = self._parse_function_node(child, result, class_name=class_name)
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
            main_module_path = imported_names_list[0][0]
            import_type = "direct_alias" if any(alias for _, alias in imported_names_list) else "direct"
            
            return ExtractedImport(
                import_type=import_type, start_line=start_line, end_line=end_line,
                module_path=main_module_path, imported_names=imported_names_list
            )
        return None

    def _parse_import_from_statement_node(self, import_from_node: Node, result: ParsedFileResult) -> Optional[ExtractedImport]:
        # (Cải thiện logic để lấy module path và items)
        try:
            start_line = self._get_line_number(import_from_node)
            end_line = self._get_end_line_number(import_from_node)
            module_path_text: Optional[str] = None
            imported_items_list: List[Tuple[str, Optional[str]]] = []
            relative_level = 0
            import_type = "from"

            module_node = import_from_node.child_by_field_name("module")
            if module_node:
                if module_node.type == "dotted_name":
                    module_path_text = self._get_node_text(module_node)
                elif module_node.type == "relative_import":
                    path_parts: List[str] = []
                    for child in module_node.children:
                        if child.type == ".":
                            relative_level += 1
                        elif child.field_name == "name" and (child.type == "identifier" or child.type == "dotted_name"):
                            part = self._get_node_text(child)
                            if part: path_parts.append(part)
                    
                    if path_parts:
                        module_path_text = ("." * relative_level) + ".".join(path_parts)
                    elif relative_level > 0:
                        module_path_text = "." * relative_level
                    else: # Should not happen if it's a relative_import node with no dots
                        module_path_text = None 
            
            name_field_node = import_from_node.child_by_field_name("name")
            if name_field_node:
                if name_field_node.type == "wildcard_import":
                    imported_items_list.append(("*", None))
                    import_type = "from_wildcard"
                elif name_field_node.type == "import_list":
                    for item_node in name_field_node.named_children:
                        if item_node.type == "dotted_name" or item_node.type == "identifier":
                            if name := self._get_node_text(item_node):
                                imported_items_list.append((name, None))
                        elif item_node.type == "aliased_import":
                            original_name_node = item_node.child_by_field_name("name")
                            alias_node = item_node.child_by_field_name("alias")
                            if original_name_node:
                                if orig_name := self._get_node_text(original_name_node):
                                    imported_items_list.append((orig_name, self._get_node_text(alias_node)))
            
            if module_path_text is not None and (imported_items_list or import_type == "from_wildcard"):
                return ExtractedImport(
                    import_type=import_type, start_line=start_line, end_line=end_line,
                    module_path=module_path_text, imported_names=imported_items_list,
                    relative_level=relative_level # relative_level đã được tính ở trên
                )
            else:
                # Không log warning ở đây nữa, vì có thể file không có import nào
                pass
            return None
        except Exception as e:
            logger.error(f"PythonParser: Error parsing import_from_statement_node at L{self._get_line_number(import_from_node)} in {result.file_path}: {e}", exc_info=True)
            return None

    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        # 1. Trích xuất Imports
        imports_query = self._get_query("imports_query")
        if imports_query:
            try:
                # Sửa lại cách duyệt `matches` cho query đơn giản hơn
                for match_tuple in imports_query.matches(root_node):
                    if not match_tuple or not match_tuple[1]: continue
                    node = match_tuple[1].get("import_node") # Lấy node từ capture name
                    
                    if node:
                        extracted_import = None
                        if node.type == "import_statement":
                            extracted_import = self._parse_import_statement_node(node, result)
                        elif node.type == "import_from_statement":
                            extracted_import = self._parse_import_from_statement_node(node, result)
                        
                        if extracted_import:
                            result.imports.append(extracted_import)
            except Exception as e:
                logger.error(f"PythonParser: Error during import extraction in {result.file_path}: {e}", exc_info=True)

        # 2. Trích xuất Classes, Global Functions, và Global Variables
        definitions_query = self._get_query("definitions_query")
        if definitions_query:
            try:
                for match_tuple in definitions_query.matches(root_node):
                    if not match_tuple or not match_tuple[1]: continue

                    node = match_tuple[1].get("definition_node") or \
                        match_tuple[1].get("global_assignment_in_expr_stmt") or \
                        match_tuple[1].get("direct_global_assignment")

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
                    elif node.type == "expression_statement" or node.type == "assignment":
                        var_name_node = None
                        actual_assignment_node = None

                        if node.type == "expression_statement":
                            # Expecting (expression_statement (assignment left: (identifier)))
                            first_child = node.child(0)
                            if first_child and first_child.type == "assignment":
                                actual_assignment_node = first_child
                        elif node.type == "assignment":
                            actual_assignment_node = node
                        
                        if actual_assignment_node:
                            var_name_node = actual_assignment_node.child_by_field_name("left")

                        if var_name_node and var_name_node.type == "identifier":
                            var_name = self._get_node_text(var_name_node)
                            if var_name and not any(gv.name == var_name for gv in result.global_variables):
                                result.global_variables.append(ExtractedVariable(
                                    name=var_name,
                                    start_line=self._get_line_number(var_name_node),
                                    end_line=self._get_end_line_number(var_name_node),
                                    scope_name=result.file_path,
                                    scope_type="global_variable"
                                ))
            except Exception as e:
                logger.error(f"PythonParser: Error during top-level entity extraction in {result.file_path}: {e}", exc_info=True)
        
        logger.info(
            f"PythonParser (Simplified AST Traversal V3 - Calls disabled) Extracted from {result.file_path}: "
            f"{len(result.imports)} imports, "
            f"{len(result.classes)} classes ({sum(len(c.methods) for c in result.classes)} methods), "
            f"{len(result.functions)} global functions, "
            f"{len(result.global_variables)} global variables."
        )
        

_parsers_cache: Dict[str, BaseCodeParser] = {}
def get_code_parser(language: str) -> Optional[BaseCodeParser]:
    language_key = language.lower().strip()
    if not language_key:
        logger.warning("get_code_parser called with empty language string.")
        return None

    parser_instance: Optional[BaseCodeParser] = None
    if language_key == "python":
        try:
            # Không cache nữa để đảm bảo luôn lấy instance mới nếu có lỗi compile query
            parser_instance = PythonParser()
            if isinstance(parser_instance, PythonParser): # Type guard
                 if parser_instance.QUERY_DEFINITIONS and not parser_instance.queries :
                    logger.error(f"PythonParser for '{language_key}' initialized, but NO queries were compiled. Parser will be ineffective.")
        except Exception as e: 
            logger.error(f"Failed to instantiate PythonParser for '{language_key}' due to: {type(e).__name__} - {e}", exc_info=True)
            return None 
    else:
        logger.warning(f"No specific parser class implemented for language: '{language}'.")
        return None
            
    return parser_instance