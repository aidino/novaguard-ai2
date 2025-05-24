#!/usr/bin/env python3
"""
Script sửa lỗi template để tương thích với Langchain
"""
import re
from pathlib import Path

def fix_langchain_template_issues():
    """Fix Langchain compatibility issues in template"""
    print("🔧 Fixing Langchain Template Compatibility Issues")
    print("=" * 60)
    
    template_file = Path("novaguard-backend/app/prompts/architectural_analyst_full_project_v1.md")
    
    if not template_file.exists():
        print(f"❌ Template file not found: {template_file}")
        return False
    
    # Read template
    original_content = template_file.read_text(encoding='utf-8')
    print(f"✅ Loaded template: {len(original_content)} characters")
    
    # Create backup
    backup_file = template_file.with_suffix('.md.langchain_backup')
    backup_file.write_text(original_content, encoding='utf-8')
    print(f"💾 Backup saved to: {backup_file}")
    
    # Apply fixes
    fixed_content = original_content
    fixes_applied = []
    
    # Fix 1: Convert Jinja2 syntax to Langchain format
    # Langchain expects {variable} not {{variable}}
    jinja_patterns = [
        (r'\{\{([^}]+)\}\}', r'{\1}'),  # Convert {{var}} to {var}
    ]
    
    for pattern, replacement in jinja_patterns:
        matches = re.findall(pattern, fixed_content)
        if matches:
            fixed_content = re.sub(pattern, replacement, fixed_content)
            fixes_applied.append(f"Converted Jinja2 to Langchain format: {len(matches)} instances")
    
    # Fix 2: Escape literal braces in examples and documentation
    # Find text that has braces but shouldn't be variables
    literal_brace_fixes = [
        # Escape braces in code examples and documentation
        (r'All variables in curly braces `\{variable\}` must exist', 
         'All variables in curly braces `{{variable}}` must exist'),
        (r'`\{([^}]+)\}`: *\n', r'`{{\1}}`: \n'),  # Variable reference docs
    ]
    
    for pattern, replacement in literal_brace_fixes:
        if re.search(pattern, fixed_content):
            fixed_content = re.sub(pattern, replacement, fixed_content)
            fixes_applied.append(f"Escaped literal braces: {pattern}")
    
    # Fix 3: Handle malformed variable references
    # Look for incomplete variable patterns
    malformed_patterns = [
        (r'\{ *([^}]+) *\}', r'{\1}'),  # Remove extra spaces
        (r'\{([^}]*)\{', r'{{\1{{'),     # Fix nested braces
    ]
    
    for pattern, replacement in malformed_patterns:
        matches = re.findall(pattern, fixed_content)
        if matches:
            fixed_content = re.sub(pattern, replacement, fixed_content)
            fixes_applied.append(f"Fixed malformed variables: {len(matches)} instances")
    
    # Fix 4: Validate all variables are properly formatted
    variables = re.findall(r'\{([^}]+)\}', fixed_content)
    valid_variables = [
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
    
    # Allow JSON filters
    valid_patterns = valid_variables + [
        'ckg_summary | tojson(indent=2)',
        'important_files_preview | tojson(indent=2)'
    ]
    
    print(f"\n🔍 Template Variable Validation:")
    print(f"   Found {len(variables)} variable references")
    
    invalid_vars = []
    for var in set(variables):
        if var not in valid_patterns and not any(valid in var for valid in valid_variables):
            invalid_vars.append(var)
    
    if invalid_vars:
        print(f"   ⚠️ Potentially invalid variables: {invalid_vars}")
        for var in invalid_vars:
            # Remove or fix invalid variables
            if 'variable' in var.lower() and var != 'variable':
                # This seems like documentation, escape it
                fixed_content = fixed_content.replace(f'{{{var}}}', f'{{{{{var}}}}}')
                fixes_applied.append(f"Escaped documentation variable: {var}")
    else:
        print(f"   ✅ All variables appear valid")
    
    # Save fixed template
    template_file.write_text(fixed_content, encoding='utf-8')
    print(f"✅ Fixed template saved to: {template_file}")
    
    print(f"\n🎯 Fixes Applied ({len(fixes_applied)} total):")
    for i, fix in enumerate(fixes_applied, 1):
        print(f"   {i}. {fix}")
    
    return True

def update_worker_context():
    """Add missing variables to worker context creation"""
    print(f"\n🔧 Updating Worker Context Creation")
    print("-" * 40)
    
    consumer_file = Path("novaguard-backend/app/analysis_worker/consumer.py")
    
    if not consumer_file.exists():
        print(f"❌ Consumer file not found: {consumer_file}")
        return False
    
    content = consumer_file.read_text(encoding='utf-8')
    
    # Look for the context creation function
    if 'create_full_project_dynamic_context' not in content:
        print(f"❌ Context creation function not found")
        return False
    
    # Check if format_instructions is already handled
    if 'format_instructions' in content:
        print(f"✅ format_instructions already exists in worker")
        return True
    
    print(f"ℹ️ Need to add format_instructions to worker context")
    print(f"   Please add this line to create_full_project_dynamic_context:")
    print(f'   context["format_instructions"] = "Return valid JSON format as specified in schema"')
    
    return True

def test_template_parsing():
    """Test if template can be parsed by Langchain"""
    print(f"\n🧪 Testing Template Parsing")
    print("-" * 30)
    
    template_file = Path("novaguard-backend/app/prompts/architectural_analyst_full_project_v1.md")
    
    if not template_file.exists():
        print(f"❌ Template file not found")
        return False
    
    content = template_file.read_text(encoding='utf-8')
    
    # Simple validation - check for unmatched braces
    open_braces = content.count('{')
    close_braces = content.count('}')
    
    print(f"   Open braces: {open_braces}")
    print(f"   Close braces: {close_braces}")
    
    if open_braces != close_braces:
        print(f"   ⚠️ Unmatched braces detected!")
        return False
    
    # Look for problematic patterns
    problems = []
    
    # Single closing braces
    single_close = re.findall(r'[^}]\}[^}]', content)
    if single_close:
        problems.append(f"Single closing braces: {len(single_close)}")
    
    # Empty variables
    empty_vars = re.findall(r'\{\s*\}', content)
    if empty_vars:
        problems.append(f"Empty variables: {len(empty_vars)}")
    
    if problems:
        print(f"   ⚠️ Potential issues: {problems}")
        return False
    
    print(f"   ✅ Template syntax looks valid")
    return True

def main():
    """Main function"""
    print("🚀 NovaGuard Langchain Template Fixer")
    print("=" * 60)
    
    # Fix template
    if fix_langchain_template_issues():
        print(f"\n✅ Template fixes completed!")
        
        # Test parsing
        if test_template_parsing():
            print(f"✅ Template parsing test passed!")
        else:
            print(f"⚠️ Template may still have parsing issues")
        
        # Update worker
        update_worker_context()
        
        print(f"\n💡 Next Steps:")
        print(f"   1. Add format_instructions to worker context")
        print(f"   2. Test with docker compose restart novaguard_analysis_worker")
        print(f"   3. Trigger a new full scan")
        print(f"   4. Check logs: docker compose logs -f novaguard_analysis_worker")
        
        print(f"\n🔧 Additional Issues from Logs:")
        print(f"   • CKG data missing top_5_largest_classes_by_methods and top_5_most_called_functions")
        print(f"   • Need to investigate CKG query functions")
        print(f"   • Context missing format_instructions variable")
        
    else:
        print(f"\n❌ Template fixes failed!")

if __name__ == "__main__":
    main() 