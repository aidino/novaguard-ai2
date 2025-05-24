"""
Models for CKG builder - compatibility layer and type definitions
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass

# Define minimal stubs to avoid circular import
class ExtractedVariable:
    def __init__(self, name, start_line, end_line, scope_name, scope_type, var_type=None, is_parameter=False):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.scope_name = scope_name
        self.scope_type = scope_type
        self.var_type = var_type
        self.is_parameter = is_parameter

class ExtractedFunction:
    def __init__(self, name, start_line, end_line, signature=None, class_name=None, body_node=None, parameters_str=None):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.signature = signature
        self.class_name = class_name
        self.parameters = []
        self.decorators = []

class ExtractedClass:
    def __init__(self, name, start_line, end_line, body_node=None):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.methods = []
        self.attributes = []
        self.superclasses = set()
        self.decorators = []

class ExtractedImport:
    def __init__(self, import_type, start_line, end_line, module_path=None, imported_names=None, relative_level=0):
        self.import_type = import_type
        self.start_line = start_line
        self.end_line = end_line
        self.module_path = module_path
        self.imported_names = imported_names or []

class ParsedFileResult:
    def __init__(self, file_path, language):
        self.file_path = file_path
        self.language = language
        self.functions = []
        self.classes = []
        self.imports = []
        self.global_variables = []

# Create aliases for compatibility
ParsedData = ParsedFileResult
ClassInfo = ExtractedClass
FunctionInfo = ExtractedFunction
VariableInfo = ExtractedVariable
ImportInfo = ExtractedImport

# Export all the classes and aliases
__all__ = [
    'ParsedData',
    'ClassInfo',
    'FunctionInfo', 
    'VariableInfo',
    'ImportInfo',
    'ExtractedVariable',
    'ExtractedFunction',
    'ExtractedClass',
    'ExtractedImport',
    'ParsedFileResult'
] 