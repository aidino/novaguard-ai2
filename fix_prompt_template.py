#!/usr/bin/env python3
"""
Script để sửa lỗi trong prompt template cho full scan
"""
import re
from pathlib import Path

def fix_prompt_template():
    """Fix issues in the prompt template"""
    print("🔧 Fixing Full Scan Prompt Template Issues")
    print("=" * 50)
    
    template_file = Path("novaguard-backend/app/prompts/architectural_analyst_full_project_v1.md")
    
    if not template_file.exists():
        print(f"❌ Template file not found: {template_file}")
        return False
    
    # Read current template
    try:
        original_content = template_file.read_text(encoding='utf-8')
        print(f"✅ Loaded template: {len(original_content)} characters")
    except Exception as e:
        print(f"❌ Error reading template: {e}")
        return False
    
    # Keep backup
    backup_file = template_file.with_suffix('.md.backup')
    backup_file.write_text(original_content, encoding='utf-8')
    print(f"💾 Backup saved to: {backup_file}")
    
    # Apply fixes
    fixed_content = original_content
    fixes_applied = []
    
    # Fix 1: Fix malformed template variables
    malformed_vars = [
        (r'\{ ckg_summary \| tojson\(indent=2\) ', '{ckg_summary | tojson(indent=2)}'),
        (r'\{ format_instructions ', '{format_instructions}'),
        (r'\{ important_files_preview \| tojson\(indent=2\) ', '{important_files_preview | tojson(indent=2)}')
    ]
    
    for pattern, replacement in malformed_vars:
        if re.search(pattern, fixed_content):
            fixed_content = re.sub(pattern, replacement, fixed_content)
            fixes_applied.append(f"Fixed malformed variable: {pattern} -> {replacement}")
    
    # Fix 2: Ensure all required variables are documented
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
    
    # Add documentation section for variables if not present
    if "## Template Variables Reference" not in fixed_content:
        var_docs = "\n\n## Template Variables Reference\n\n"
        var_docs += "The following variables are provided by the analysis context:\n\n"
        
        for var in required_vars:
            var_docs += f"- `{{{var}}}`: \n"
        
        var_docs += "\n"
        
        # Insert before the last section
        fixed_content = fixed_content + var_docs
        fixes_applied.append("Added template variables documentation")
    
    # Fix 3: Add debugging section if not present
    if "DEBUGGING INFORMATION" not in fixed_content:
        debug_section = """
## DEBUGGING INFORMATION FOR DEVELOPMENT

When debugging prompt issues, verify these elements:

1. **Template Variables**: All variables in curly braces `{variable}` must exist in context
2. **CKG Data Quality**: Ensure CKG summary contains meaningful data
3. **Context Coverage**: Check that context provides all required variables
4. **Anti-Hallucination**: Verify CKG data prevents fictional references

**Common Issues:**
- Empty CKG data leads to hallucination
- Missing variables cause template errors  
- Malformed JSON filters break rendering
- Insufficient context causes generic responses

"""
        fixed_content = fixed_content + debug_section
        fixes_applied.append("Added debugging information section")
    
    # Save fixed template
    try:
        template_file.write_text(fixed_content, encoding='utf-8')
        print(f"✅ Fixed template saved to: {template_file}")
    except Exception as e:
        print(f"❌ Error saving fixed template: {e}")
        return False
    
    # Report fixes
    print(f"\n🎯 Fixes Applied ({len(fixes_applied)} total):")
    for i, fix in enumerate(fixes_applied, 1):
        print(f"   {i}. {fix}")
    
    # Verify fixes
    print(f"\n🔍 Verifying Fixes:")
    new_content = template_file.read_text(encoding='utf-8')
    
    # Check for malformed variables
    malformed_patterns = [
        r'\{ [^}]+ \|',  # Variables with spaces around pipes
        r'\{ [^}]+ (?!\|)[^}]*$',  # Variables with trailing spaces
    ]
    
    issues_found = 0
    for pattern in malformed_patterns:
        matches = re.findall(pattern, new_content, re.MULTILINE)
        if matches:
            print(f"   ⚠️ Still found potentially malformed variables: {matches}")
            issues_found += len(matches)
    
    if issues_found == 0:
        print(f"   ✅ No malformed variables found")
    
    # Check variable syntax
    variables = re.findall(r'\{([^}]+)\}', new_content)
    print(f"   ✅ Found {len(variables)} template variables")
    
    unique_vars = sorted(set(variables))
    print(f"   ✅ {len(unique_vars)} unique variables")
    
    return True

def create_context_validator():
    """Create a script to validate context data"""
    print(f"\n📝 Creating Context Validator Script")
    
    validator_content = '''#!/usr/bin/env python3
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
'''
    
    validator_file = Path("novaguard-backend/app/analysis_worker/context_validator.py")
    validator_file.write_text(validator_content, encoding='utf-8')
    print(f"✅ Context validator created: {validator_file}")

def main():
    """Main function"""
    print("🚀 NovaGuard Full Scan Prompt Template Fixer")
    print("=" * 60)
    
    # Fix the template
    if fix_prompt_template():
        print(f"\n✅ Template fixes completed successfully!")
        
        # Create additional tools
        create_context_validator()
        
        print(f"\n💡 Next Steps:")
        print(f"   1. Test the fixed template with a real full scan")
        print(f"   2. Check worker logs for any remaining issues")
        print(f"   3. Verify that CKG data is properly populated")
        print(f"   4. Use context validator in worker code for debugging")
        print(f"   5. Enable DEBUG logging to see full prompts")
        
        print(f"\n🔧 To test:")
        print(f"   # Trigger a full scan from dashboard")
        print(f"   # Check logs with: docker compose logs -f novaguard_analysis_worker")
        
    else:
        print(f"\n❌ Template fixes failed!")

if __name__ == "__main__":
    main() 