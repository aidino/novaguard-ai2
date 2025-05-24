from .builder import CKGBuilder
from .models import (
    ParsedData,
    ParsedFileResult, 
    ExtractedFunction, 
    ExtractedClass, 
    ExtractedImport, 
    ExtractedVariable,
    ClassInfo,
    FunctionInfo
)

# Import parser functions separately to avoid circular import
def get_code_parser(language: str):
    """Get code parser for specified language."""
    from .parsers import get_code_parser as _get_code_parser
    return _get_code_parser(language)

def get_android_manifest_parser():
    """Get Android Manifest parser."""
    from .parsers import get_android_manifest_parser as _get_android_manifest_parser
    return _get_android_manifest_parser()

def get_gradle_parser(file_path: str = "build.gradle"):
    """Get Gradle parser."""
    from .parsers import get_gradle_parser as _get_gradle_parser
    return _get_gradle_parser(file_path)

__all__ = [
    "get_code_parser",
    "ParsedFileResult",
    "ParsedData",
    "ExtractedFunction",
    "ExtractedClass",
    "ExtractedImport",
    "ExtractedVariable",
    "ClassInfo",
    "FunctionInfo",
    "CKGBuilder",
    "get_android_manifest_parser",
    "get_gradle_parser"
]