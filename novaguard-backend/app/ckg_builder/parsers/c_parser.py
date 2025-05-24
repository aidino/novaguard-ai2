# novaguard-backend/app/ckg_builder/parsers/c_parser.py
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

class CParser(BaseCodeParser):
    """Basic C parser using tree-sitter."""
    
    QUERY_DEFINITIONS = {
        "includes_query": """
            (preproc_include) @include_node
        """,
        "function_definitions_query": """
            (function_definition) @function_node
        """,
        "function_declarations_query": """
            (declaration
              declarator: (function_declarator) @function_decl
            )
        """,
        "struct_definitions_query": """
            [
              (struct_specifier) @struct_node
              (union_specifier) @union_node
            ]
        """
    }
    
    def __init__(self):
        super().__init__("c")
        self.queries: Dict[str, Query] = {}
        for query_name, query_string in self.QUERY_DEFINITIONS.items():
            try:
                self.queries[query_name] = self.lang_object.query(query_string)
                logger.debug(f"CParser: Query '{query_name}' compiled successfully.")
            except Exception as e:
                logger.error(f"CParser: Error compiling query '{query_name}': {e}")
                
    def _get_query(self, query_name: str) -> Optional[Query]:
        return self.queries.get(query_name)
    
    def _parse_includes(self, root_node: Node, result: ParsedFileResult):
        """Parse #include statements."""
        includes_query = self._get_query("includes_query")
        if includes_query:
            captures = includes_query.captures(root_node)
            for node, capture_name in captures:
                if capture_name == "include_node":
                    include_text = self._get_node_text(node)
                    if include_text:
                        # Extract include path from #include "path" or #include <path>
                        if '"' in include_text:
                            start = include_text.find('"') + 1
                            end = include_text.rfind('"')
                            if start > 0 and end > start:
                                include_path = include_text[start:end]
                        elif '<' in include_text and '>' in include_text:
                            start = include_text.find('<') + 1
                            end = include_text.rfind('>')
                            if start > 0 and end > start:
                                include_path = include_text[start:end]
                        else:
                            include_path = include_text
                        
                        if include_path:
                            extracted_import = ExtractedImport(
                                import_type="include",
                                start_line=self._get_line_number(node),
                                end_line=self._get_end_line_number(node),
                                module_path=include_path
                            )
                            result.imports.append(extracted_import)
    
    def _parse_function_definition(self, function_node: Node, result: ParsedFileResult):
        """Parse C function definition."""
        # Get function name from declarator
        declarator_node = None
        for child in function_node.children:
            if child.type == "function_declarator":
                declarator_node = child
                break
        
        if not declarator_node:
            return
        
        # Get function name
        function_name = None
        for child in declarator_node.children:
            if child.type == "identifier":
                function_name = self._get_node_text(child)
                break
        
        if not function_name:
            return
        
        # Get function body
        body_node = None
        for child in function_node.children:
            if child.type == "compound_statement":
                body_node = child
                break
        
        extracted_function = ExtractedFunction(
            name=function_name,
            start_line=self._get_line_number(function_node),
            end_line=self._get_end_line_number(function_node),
            body_node=body_node
        )
        
        # Parse parameters
        parameter_list_node = None
        for child in declarator_node.children:
            if child.type == "parameter_list":
                parameter_list_node = child
                break
        
        if parameter_list_node:
            self._parse_function_parameters(parameter_list_node, extracted_function)
        
        result.functions.append(extracted_function)
    
    def _parse_function_parameters(self, parameter_list_node: Node, function: ExtractedFunction):
        """Parse C function parameters."""
        for child in parameter_list_node.children:
            if child.type == "parameter_declaration":
                param_name = None
                param_type = None
                
                # Find type and declarator
                for param_child in child.children:
                    if param_child.type in ["primitive_type", "type_identifier"]:
                        param_type = self._get_node_text(param_child)
                    elif param_child.type == "identifier":
                        param_name = self._get_node_text(param_child)
                    elif param_child.type in ["pointer_declarator", "array_declarator"]:
                        # Handle pointer and array parameters
                        for decl_child in param_child.children:
                            if decl_child.type == "identifier":
                                param_name = self._get_node_text(decl_child)
                
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
    
    def _parse_struct_definition(self, struct_node: Node, result: ParsedFileResult):
        """Parse C struct/union definition."""
        struct_name = None
        is_union = struct_node.type == "union_specifier"
        
        # Get struct name
        for child in struct_node.children:
            if child.type == "type_identifier":
                struct_name = self._get_node_text(child)
                break
        
        if not struct_name:
            return
        
        # Get struct body
        body_node = None
        for child in struct_node.children:
            if child.type == "field_declaration_list":
                body_node = child
                break
        
        extracted_struct = ExtractedClass(
            name=struct_name,
            start_line=self._get_line_number(struct_node),
            end_line=self._get_end_line_number(struct_node),
            body_node=body_node
        )
        
        # Mark as struct or union
        if is_union:
            extracted_struct.decorators.append("union")
        else:
            extracted_struct.decorators.append("struct")
        
        # Parse struct fields
        if body_node:
            for child in body_node.children:
                if child.type == "field_declaration":
                    self._parse_struct_field(child, extracted_struct)
        
        result.classes.append(extracted_struct)
    
    def _parse_struct_field(self, field_node: Node, struct_class: ExtractedClass):
        """Parse C struct field declaration."""
        field_name = None
        field_type = None
        
        for child in field_node.children:
            if child.type in ["primitive_type", "type_identifier"]:
                field_type = self._get_node_text(child)
            elif child.type == "field_identifier":
                field_name = self._get_node_text(child)
            elif child.type in ["pointer_declarator", "array_declarator"]:
                # Handle pointer and array fields
                for decl_child in child.children:
                    if decl_child.type == "field_identifier":
                        field_name = self._get_node_text(decl_child)
        
        if field_name:
            field = ExtractedVariable(
                name=field_name,
                start_line=self._get_line_number(field_node),
                end_line=self._get_end_line_number(field_node),
                scope_name=struct_class.name,
                scope_type="struct_field",
                var_type=field_type
            )
            struct_class.attributes.append(field)
    
    def _extract_entities(self, root_node: Node, result: ParsedFileResult):
        """Extract all entities from C code."""
        try:
            # Parse includes
            self._parse_includes(root_node, result)
            
            # Parse function definitions
            function_defs_query = self._get_query("function_definitions_query")
            if function_defs_query:
                captures = function_defs_query.captures(root_node)
                for node, capture_name in captures:
                    if capture_name == "function_node":
                        try:
                            self._parse_function_definition(node, result)
                        except Exception as e:
                            logger.debug(f"CParser: Error parsing function in {result.file_path}: {e}")
                            continue
            
            # Parse struct/union definitions
            struct_defs_query = self._get_query("struct_definitions_query")
            if struct_defs_query:
                captures = struct_defs_query.captures(root_node)
                for node, capture_name in captures:
                    if capture_name in ["struct_node", "union_node"]:
                        try:
                            self._parse_struct_definition(node, result)
                        except Exception as e:
                            logger.debug(f"CParser: Error parsing struct/union in {result.file_path}: {e}")
                            continue
                            
            logger.debug(f"CParser: Extracted {len(result.classes)} structs, {len(result.functions)} functions, "
                        f"{len(result.imports)} includes from {result.file_path}")
                        
        except Exception as e:
            logger.debug(f"CParser: Error during entity extraction from {result.file_path}: {e}") 