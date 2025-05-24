"""
Shared base classes for all parsers to avoid circular imports.
"""
import logging
from typing import Optional, Set, List, Tuple, Dict, Any
from tree_sitter import Node, Query, Language, Parser
from tree_sitter_languages import get_language

logger = logging.getLogger(__name__)

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
    def __init__(self, language_name: str):
        self.language_name = language_name
        try:
            self.lang_object: Language = get_language(language_name)
            self.parser: Parser = Parser()
            self.parser.set_language(self.lang_object)
            logger.info(f"Tree-sitter parser for '{language_name}' initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to load tree-sitter language grammar for '{language_name}': {e}")
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
                error_details = []
                
                def find_error_nodes(node: Node, max_errors: int = 3):
                    nonlocal error_node_found, first_error_node_info, error_details
                    if len(error_details) >= max_errors:
                        return
                        
                    if node.type == 'ERROR' or node.is_missing:
                        error_node_found = True
                        line_num = max(1, self._get_line_number(node))  # Ensure line is at least 1
                        error_text = self._get_node_text(node) or "<unknown>"
                        
                        # Get more context about the error
                        context_info = ""
                        if node.parent:
                            parent_text = self._get_node_text(node.parent)
                            if parent_text and len(parent_text) > 10:
                                context_info = f" in {parent_text[:30]}..."
                        
                        error_info = f"type: {node.type}, line: {line_num}{context_info}"
                        
                        if not first_error_node_info or first_error_node_info == "Unknown error location":
                            first_error_node_info = error_info
                            
                        error_details.append({
                            "type": node.type,
                            "line": line_num,
                            "text": error_text[:50] + "..." if len(error_text) > 50 else error_text,
                            "context": context_info
                        })
                        return
                        
                    for child_node in node.children:
                        if len(error_details) >= max_errors:
                            break
                        find_error_nodes(child_node, max_errors)
                
                find_error_nodes(tree.root_node)
                
                # Log detailed error information but continue parsing
                if error_details:
                    error_summary = ", ".join([f"L{err['line']}:{err['type']}" for err in error_details])
                    logger.debug(
                        f"Syntax errors in {file_path} "
                        f"(errors at: {error_summary}). Attempting partial parsing."
                    )
                else:
                    logger.debug(
                        f"Syntax errors in {file_path} (e.g., near {first_error_node_info}). "
                        f"Attempting partial parsing."
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