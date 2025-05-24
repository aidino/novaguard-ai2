#!/usr/bin/env python3
"""
Script debug đơn giản để kiểm tra prompt template cho full scan
"""
import re
import json
from pathlib import Path

def debug_prompt_template():
    """Debug prompt template loading"""
    print("📝 Debug Full Scan Prompt Template")
    print("=" * 50)
    
    prompt_file = Path("novaguard-backend/app/prompts/architectural_analyst_full_project_v1.md")
    
    if not prompt_file.exists():
        print(f"❌ Prompt file không tồn tại: {prompt_file}")
        return None, []
    
    try:
        # Load prompt template
        prompt_template = prompt_file.read_text(encoding='utf-8')
        
        print(f"✅ Prompt template loaded successfully")
        print(f"   File: {prompt_file}")
        print(f"   Length: {len(prompt_template)} characters")
        
        lines_count = len(prompt_template.split('\n'))
        print(f"   Lines: {lines_count} lines")
        
        # Extract variables from template (both single and double braces)
        single_brace_vars = re.findall(r'(?<!\{)\{([^}]+)\}(?!\})', prompt_template)
        double_brace_vars = re.findall(r'\{\{([^}]+)\}\}', prompt_template)
        variables = single_brace_vars + double_brace_vars
        unique_variables = sorted(set(variables))
        
        print(f"\n🔍 Template Variables ({len(unique_variables)} unique):")
        for i, var in enumerate(unique_variables, 1):
            print(f"   {i:2d}. {var}")
        
        # Show template preview  
        print(f"\n📄 Template Preview (first 800 chars):")
        print("-" * 50)
        print(prompt_template[:800])
        print("-" * 50)
        if len(prompt_template) > 800:
            print(f"... (còn {len(prompt_template) - 800} ký tự nữa)")
        
        # Check for anti-hallucination content
        anti_hallucination_keywords = [
            "ANTI-HALLUCINATION",
            "ABSOLUTE PROHIBITION", 
            "DO NOT analyze fictional files",
            "DO NOT reference non-existent",
            "VERIFICATION CHECKPOINT"
        ]
        
        print(f"\n🛡️ Anti-Hallucination Measures:")
        for keyword in anti_hallucination_keywords:
            if keyword in prompt_template:
                print(f"   ✅ Found: '{keyword}'")
            else:
                print(f"   ❌ Missing: '{keyword}'")
        
        # Look for specific instructions about CKG data
        ckg_keywords = [
            "ckg_summary",
            "total_files",
            "total_classes", 
            "main_modules",
            "top_5_largest_classes",
            "top_5_most_called_functions"
        ]
        
        print(f"\n📊 CKG Data References:")
        for keyword in ckg_keywords:
            if keyword in prompt_template:
                print(f"   ✅ Found: '{keyword}'")
            else:
                print(f"   ❌ Missing: '{keyword}'")
        
        return prompt_template, unique_variables
        
    except Exception as e:
        print(f"❌ Lỗi khi load prompt template: {e}")
        import traceback
        traceback.print_exc()
        return None, []

def analyze_template_structure(template_content: str):
    """Analyze the structure of the prompt template"""
    print(f"\n🏗️ Template Structure Analysis:")
    
    # Count sections
    sections = re.findall(r'^#+\s+(.+)$', template_content, re.MULTILINE)
    print(f"   Sections found: {len(sections)}")
    for i, section in enumerate(sections[:10], 1):  # Show first 10 sections
        print(f"   {i:2d}. {section}")
    if len(sections) > 10:
        print(f"   ... and {len(sections) - 10} more sections")
    
    # Count different types of instructions
    instruction_patterns = {
        "Requirements": r"REQUIRED?[:.]",
        "Prohibitions": r"DO NOT|NEVER|FORBIDDEN",
        "Examples": r"Example|✅|❌",
        "Variables": r"\{[^}]+\}",
        "JSON format": r"JSON|json"
    }
    
    print(f"\n📋 Instruction Types:")
    for inst_type, pattern in instruction_patterns.items():
        matches = re.findall(pattern, template_content, re.IGNORECASE)
        print(f"   {inst_type}: {len(matches)} instances")

def simulate_context_data():
    """Simulate typical context data that would be passed to the template"""
    print(f"\n🎭 Simulated Context Data:")
    
    # This simulates what create_full_project_dynamic_context would return
    mock_context = {
        "project_id": 1,
        "project_name": "aidino/AmazeFileManager",
        "project_language": "Java, Kotlin",
        "project_custom_notes": "File manager app for Android",
        "main_branch": "release/4.0",
        "requested_output_language": "en",
        "total_files": 110,
        "total_classes": 155,
        "total_functions_methods": 892,
        "average_functions_per_file": 8.1,
        "ckg_summary": {
            "total_files": 110,
            "total_classes": 155,
            "total_functions_methods": 892,
            "main_modules": [
                "app/src/main/java/com/amaze/filemanager/MainActivity.java",
                "app/src/main/java/com/amaze/filemanager/adapters/DataAdapter.java",
                "app/src/main/java/com/amaze/filemanager/utils/Utils.java"
            ],
            "top_5_largest_classes_by_methods": [
                {"name": "MainActivity", "file_path": "app/src/main/java/com/amaze/filemanager/MainActivity.java", "method_count": 45},
                {"name": "DataAdapter", "file_path": "app/src/main/java/com/amaze/filemanager/adapters/DataAdapter.java", "method_count": 32},
                {"name": "Utils", "file_path": "app/src/main/java/com/amaze/filemanager/utils/Utils.java", "method_count": 28}
            ],
            "top_5_most_called_functions": [
                {"name": "onCreate", "file_path": "MainActivity.java", "call_count": 15},
                {"name": "getSystemService", "file_path": "Utils.java", "call_count": 12},
                {"name": "findViewById", "file_path": "MainActivity.java", "call_count": 10}
            ]
        }
    }
    
    print(f"   Mock context has {len(mock_context)} top-level keys")
    for key, value in mock_context.items():
        if isinstance(value, dict):
            print(f"   {key}: Dict with {len(value)} keys")
        elif isinstance(value, list):
            print(f"   {key}: List with {len(value)} items")
        elif isinstance(value, str) and len(value) > 50:
            print(f"   {key}: String ({len(value)} chars)")
        else:
            print(f"   {key}: {value}")
    
    return mock_context

def check_template_variables_coverage(template_vars: list, context_data: dict):
    """Check if context data covers all template variables"""
    print(f"\n🎯 Template Variable Coverage Check:")
    
    context_keys = set(context_data.keys())
    template_vars_set = set(template_vars)
    
    # Add nested keys from ckg_summary
    if 'ckg_summary' in context_data:
        ckg_data = context_data['ckg_summary']
        for key in ckg_data.keys():
            context_keys.add(key)
    
    missing_vars = template_vars_set - context_keys
    extra_vars = context_keys - template_vars_set
    covered_vars = template_vars_set & context_keys
    
    print(f"   Total template variables: {len(template_vars_set)}")
    print(f"   Covered by context: {len(covered_vars)}")
    print(f"   Missing from context: {len(missing_vars)}")
    print(f"   Extra in context: {len(extra_vars)}")
    
    coverage_percentage = (len(covered_vars) / len(template_vars_set)) * 100 if template_vars_set else 0
    print(f"   Coverage: {coverage_percentage:.1f}%")
    
    if missing_vars:
        print(f"\n❌ Missing Variables:")
        for var in sorted(missing_vars):
            print(f"   - {var}")
    
    if extra_vars and len(extra_vars) <= 10:
        print(f"\n➕ Extra Variables (not used in template):")
        for var in sorted(extra_vars):
            print(f"   - {var}")
    elif extra_vars:
        print(f"\n➕ Extra Variables: {len(extra_vars)} variables not used in template")
    
    return coverage_percentage >= 90  # Consider 90%+ as good coverage

def main():
    """Main debug function"""
    print("🚀 Simple Full Scan Prompt Debugger")
    print("=" * 60)
    
    # Step 1: Load and analyze prompt template
    template, variables = debug_prompt_template()
    
    if not template:
        print("❌ Cannot proceed without template")
        return
    
    # Step 2: Analyze template structure
    analyze_template_structure(template)
    
    # Step 3: Simulate context data
    context = simulate_context_data()
    
    # Step 4: Check variable coverage
    coverage_ok = check_template_variables_coverage(variables, context)
    
    # Step 5: Save debug results
    debug_results = {
        "template_file": "novaguard-backend/app/prompts/architectural_analyst_full_project_v1.md",
        "template_length": len(template),
        "template_lines": len(template.split('\n')),
        "template_variables": variables,
        "unique_variables_count": len(set(variables)),
        "context_keys": list(context.keys()),
        "coverage_percentage": (len(set(variables) & set(context.keys())) / len(set(variables))) * 100 if variables else 0,
        "missing_variables": list(set(variables) - set(context.keys())),
        "coverage_ok": coverage_ok
    }
    
    debug_file = "simple_prompt_debug_results.json"
    with open(debug_file, 'w', encoding='utf-8') as f:
        json.dump(debug_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Debug results saved to: {debug_file}")
    
    if coverage_ok:
        print(f"\n✅ Template appears to be well-structured with good variable coverage!")
    else:
        print(f"\n⚠️ Template may have variable coverage issues - check missing variables")
    
    print(f"\n🎯 Summary:")
    print(f"   - Template has {len(set(variables))} unique variables")
    print(f"   - Context provides {len(context)} data points")
    print(f"   - Coverage: {debug_results['coverage_percentage']:.1f}%")
    print(f"   - Missing: {len(debug_results['missing_variables'])} variables")

if __name__ == "__main__":
    main() 