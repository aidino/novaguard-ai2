# Export core data structures and parser functions
# Import from individual parser modules to avoid circular imports

from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Re-export core classes from the main parsers module for external use
def get_core_classes():
    """Lazy import of core classes to avoid circular imports."""
    try:
        from .base_classes import (
            ParsedFileResult,
            ExtractedFunction,
            ExtractedClass,
            ExtractedImport,
            ExtractedVariable,
            BaseCodeParser
        )
        return {
            'ParsedFileResult': ParsedFileResult,
            'ExtractedFunction': ExtractedFunction,
            'ExtractedClass': ExtractedClass,
            'ExtractedImport': ExtractedImport,
            'ExtractedVariable': ExtractedVariable,
            'BaseCodeParser': BaseCodeParser
        }
    except ImportError as e:
        logger.warning(f"Could not import core classes from base_classes.py: {e}")
        return {}

def get_android_manifest_parser():
    """Get Android Manifest parser instance."""
    try:
        from .android_manifest_parser import AndroidManifestParser
        return AndroidManifestParser()
    except ImportError:
        logger.warning("AndroidManifestParser not available")
        return None

def get_gradle_parser(file_path: str = "build.gradle"):
    """Get Gradle parser instance based on file extension."""
    try:
        from .gradle_parser import get_gradle_parser as _get_gradle_parser
        return _get_gradle_parser(file_path)
    except ImportError:
        logger.warning("GradleParser not available")
        return None

def get_code_parser(language: str):
    """Get code parser for specified language."""
    try:
        language_key = language.lower().strip()
        if language_key == "kotlin":
            from .kotlin_parser import KotlinParser
            return KotlinParser()
        elif language_key == "java":
            from .java_parser import JavaParser
            return JavaParser()
        elif language_key in ["c", "c_lang"]:
            from .c_parser import CParser
            return CParser()
        elif language_key == "python":
            # Python parser not yet implemented in new structure
            logger.warning("PythonParser not yet available in new parser structure")
            return None
        else:
            logger.warning(f"No parser available for language: {language}")
            return None
    except ImportError as e:
        logger.warning(f"Parser for {language} not available: {e}")
        return None

# Export public API
__all__ = [
    'get_code_parser',
    'get_android_manifest_parser',
    'get_gradle_parser',
    'get_core_classes'
]

# Try to import and re-export core classes for backward compatibility
try:
    _core_classes = get_core_classes()
    if _core_classes:
        globals().update(_core_classes)
        __all__.extend(_core_classes.keys())
except Exception as e:
    logger.warning(f"Could not re-export core classes: {e}") 