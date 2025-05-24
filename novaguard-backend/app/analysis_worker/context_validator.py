#!/usr/bin/env python3
"""
Validator for full scan context data
"""
import sys
from typing import Dict, Any, List

def validate_context(context: Dict[str, Any]) -> List[str]:
    """Validate that context has all required variables"""
    required_vars = [
        'project_name',
        'project_language',
        'project_custom_notes', 
        'main_branch',
        'requested_output_language',
        'total_files',
        'total_classes',
        'total_functions_methods',
        'average_functions_per_file',
        'directory_listing_top_level',
        'important_files_preview',
        'ckg_summary',
        'format_instructions'
    ]
    
    issues = []
    
    for var in required_vars:
        if var not in context:
            issues.append(f"Missing variable: {var}")
        elif context[var] is None:
            issues.append(f"Variable is None: {var}")
        elif isinstance(context[var], str) and not context[var].strip():
            issues.append(f"Variable is empty string: {var}")
    
    # Check CKG summary structure
    if 'ckg_summary' in context and isinstance(context['ckg_summary'], dict):
        ckg = context['ckg_summary']
        required_ckg_keys = [
            'total_files', 'total_classes', 'total_functions_methods',
            'main_modules', 'top_5_largest_classes_by_methods', 'top_5_most_called_functions'
        ]
        
        for key in required_ckg_keys:
            if key not in ckg:
                issues.append(f"Missing CKG key: {key}")
            elif not ckg[key]:  # Empty or zero
                issues.append(f"Empty CKG data: {key}")
    
    return issues

# Example usage in worker:
# issues = validate_context(full_project_context)
# if issues:
#     logger.error(f"Context validation failed: {issues}")
#     return basic_fallback_response()
