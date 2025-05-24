#!/usr/bin/env python3
"""
Script debug để kiểm tra prompt và thông tin đưa vào full scan project
"""
import asyncio
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any

# Thêm đường dẫn để import modules
sys.path.append(str(Path(__file__).parent / "novaguard-backend"))

from app.core.db import get_db
from app.models import Project, FullProjectAnalysisRequest
from app.project_service.crud_project import get_project_by_id
from app.project_service.crud_full_scan import get_full_scan_request_by_id
from app.analysis_worker.consumer import (
    create_full_project_dynamic_context,
    query_ckg_for_project_summary,
    load_prompt_template_str
)
from app.ckg_builder.builder import CKGBuilder
from app.core.config import get_settings

async def debug_ckg_data(project_id: int, scan_request_id: int = None):
    """Debug CKG data for a project"""
    print(f"🔍 Debug CKG Data cho Project ID: {project_id}")
    
    # Get database session
    db = next(get_db())
    
    # Get project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        print(f"❌ Không tìm thấy project với ID: {project_id}")
        return
    
    print(f"✅ Project: {project.repo_name}")
    print(f"   - Language: {project.language}")
    print(f"   - Main branch: {project.main_branch}")
    print(f"   - Custom notes: {project.custom_project_notes[:100] if project.custom_project_notes else 'None'}...")
    
    # Get scan request if provided
    scan_request = None
    if scan_request_id:
        scan_request = get_full_scan_request_by_id(db, scan_request_id)
        if scan_request:
            print(f"✅ Scan Request: {scan_request.id} - Status: {scan_request.status.value}")
            print(f"   - Branch: {scan_request.branch_name}")
            print(f"   - Project Graph ID: {scan_request.project_graph_id}")
        else:
            print(f"❌ Không tìm thấy scan request với ID: {scan_request_id}")
    
    # Create CKG Builder
    print(f"\n📊 Checking CKG Data...")
    try:
        # Sử dụng project graph ID từ scan request hoặc tạo fallback
        if scan_request and scan_request.project_graph_id:
            project_graph_id = scan_request.project_graph_id
        else:
            project_graph_id = f"novaguard_project_{project.id}"
        
        print(f"   Project Graph ID: {project_graph_id}")
        
        # Create temporary CKG builder
        ckg_builder = CKGBuilder(project_id=project.id, branch_name=project.main_branch)
        ckg_builder.project_graph_id = project_graph_id
        
        # Query CKG summary
        ckg_summary = await query_ckg_for_project_summary(project_graph_id, ckg_builder)
        
        print(f"\n📈 CKG Summary Results:")
        print(f"   - Total files: {ckg_summary.get('total_files', 0)}")
        print(f"   - Total classes: {ckg_summary.get('total_classes', 0)}")
        print(f"   - Total functions/methods: {ckg_summary.get('total_functions_methods', 0)}")
        print(f"   - Average functions per file: {ckg_summary.get('average_functions_per_file', 0)}")
        
        print(f"\n📁 Main Modules:")
        main_modules = ckg_summary.get('main_modules', [])
        if main_modules:
            for i, module in enumerate(main_modules[:10], 1):  # Show first 10
                print(f"   {i}. {module}")
            if len(main_modules) > 10:
                print(f"   ... và {len(main_modules) - 10} modules khác")
        else:
            print("   Không có main modules")
        
        print(f"\n🏗️ Top 5 Largest Classes:")
        largest_classes = ckg_summary.get('top_5_largest_classes_by_methods', [])
        if largest_classes:
            for i, cls in enumerate(largest_classes, 1):
                print(f"   {i}. {cls.get('name')} ({cls.get('method_count')} methods)")
                print(f"      File: {cls.get('file_path')}")
        else:
            print("   Không có classes được tìm thấy")
        
        print(f"\n🔥 Top 5 Most Called Functions:")
        most_called = ckg_summary.get('top_5_most_called_functions', [])
        if most_called:
            for i, func in enumerate(most_called, 1):
                print(f"   {i}. {func.get('name')} ({func.get('call_count')} calls)")
                print(f"      File: {func.get('file_path')}")
        else:
            print("   Không có functions được tìm thấy")
        
        return ckg_summary
        
    except Exception as e:
        print(f"❌ Lỗi khi query CKG data: {e}")
        import traceback
        traceback.print_exc()
        return None

async def debug_dynamic_context(project_id: int):
    """Debug dynamic context creation"""
    print(f"\n🔧 Debug Dynamic Context cho Project ID: {project_id}")
    
    # Get database session  
    db = next(get_db())
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        print(f"❌ Không tìm thấy project")
        return None
    
    # Fake local path for testing (in production this would be real cloned code)
    fake_local_path = f"/tmp/fake_project_{project_id}"
    
    try:
        # Create CKG builder
        ckg_builder = CKGBuilder(project_id=project.id, branch_name=project.main_branch)
        ckg_builder.project_graph_id = f"novaguard_project_{project.id}"
        
        # Create dynamic context
        context = await create_full_project_dynamic_context(
            project_model=project,
            project_code_local_path=fake_local_path,
            ckg_builder=ckg_builder
        )
        
        print(f"\n📋 Dynamic Context Keys:")
        for key in sorted(context.keys()):
            value = context[key]
            if isinstance(value, str):
                preview = value[:100] + "..." if len(value) > 100 else value
                print(f"   {key}: {preview}")
            elif isinstance(value, dict):
                print(f"   {key}: Dict with {len(value)} keys - {list(value.keys())}")
            elif isinstance(value, list):
                print(f"   {key}: List with {len(value)} items")
            else:
                print(f"   {key}: {type(value)} - {value}")
        
        return context
        
    except Exception as e:
        print(f"❌ Lỗi khi tạo dynamic context: {e}")
        import traceback
        traceback.print_exc()
        return None

def debug_prompt_template():
    """Debug prompt template loading"""
    print(f"\n📝 Debug Prompt Template")
    
    try:
        # Load prompt template
        prompt_template = load_prompt_template_str("architectural_analyst_full_project_v1.md")
        
        print(f"✅ Prompt template loaded successfully")
        print(f"   Length: {len(prompt_template)} characters")
        lines_count = len(prompt_template.split('\n'))
        print(f"   Lines: {lines_count} lines")
        
        # Extract variables from template
        import re
        variables = re.findall(r'\{([^}]+)\}', prompt_template)
        unique_variables = sorted(set(variables))
        
        print(f"\n🔍 Template Variables ({len(unique_variables)} unique):")
        for var in unique_variables:
            print(f"   - {var}")
        
        # Show template preview  
        print(f"\n📄 Template Preview (first 500 chars):")
        print("-" * 50)
        print(prompt_template[:500])
        print("-" * 50)
        
        return prompt_template, unique_variables
        
    except Exception as e:
        print(f"❌ Lỗi khi load prompt template: {e}")
        import traceback
        traceback.print_exc()
        return None, []

def simulate_prompt_rendering(context: Dict[str, Any], template_variables: list):
    """Simulate prompt rendering with context data"""
    print(f"\n🎨 Simulate Prompt Rendering")
    
    # Check which variables are available vs required
    context_keys = set(context.keys()) if context else set()
    required_vars = set(template_variables)
    
    missing_vars = required_vars - context_keys
    extra_vars = context_keys - required_vars
    
    print(f"   Required variables: {len(required_vars)}")
    print(f"   Available variables: {len(context_keys)}")
    print(f"   Missing variables: {len(missing_vars)}")
    print(f"   Extra variables: {len(extra_vars)}")
    
    if missing_vars:
        print(f"\n❌ Missing Required Variables:")
        for var in sorted(missing_vars):
            print(f"   - {var}")
    
    if extra_vars:
        print(f"\n➕ Extra Available Variables:")
        for var in sorted(list(extra_vars)[:10]):  # Show first 10
            print(f"   - {var}")
        if len(extra_vars) > 10:
            print(f"   ... và {len(extra_vars) - 10} variables khác")
    
    # Show sample variable values
    print(f"\n📊 Sample Variable Values:")
    sample_vars = ['project_name', 'total_files', 'total_classes', 'project_language', 'requested_output_language']
    for var in sample_vars:
        if var in context:
            value = context[var]
            if isinstance(value, str) and len(value) > 100:
                preview = value[:100] + "..."
            else:
                preview = value
            print(f"   {var}: {preview}")

async def main():
    """Main debug function"""
    print("🚀 NovaGuard Full Scan Prompt Debugger")
    print("=" * 50)
    
    # Get project ID from command line or use default
    if len(sys.argv) > 1:
        try:
            project_id = int(sys.argv[1])
        except ValueError:
            print(f"❌ Invalid project ID: {sys.argv[1]}")
            return
    else:
        # Use default project ID (you can change this)
        project_id = 1
        print(f"⚠️ Sử dụng default project ID: {project_id}")
    
    # Get scan request ID if provided
    scan_request_id = None
    if len(sys.argv) > 2:
        try:
            scan_request_id = int(sys.argv[2])
        except ValueError:
            print(f"❌ Invalid scan request ID: {sys.argv[2]}")
            return
    
    # Step 1: Debug CKG data
    ckg_summary = await debug_ckg_data(project_id, scan_request_id)
    
    # Step 2: Debug dynamic context creation
    context = await debug_dynamic_context(project_id)
    
    # Step 3: Debug prompt template
    template, variables = debug_prompt_template()
    
    # Step 4: Simulate prompt rendering
    if context and variables:
        simulate_prompt_rendering(context, variables)
    
    # Step 5: Save debug data to file
    debug_data = {
        "project_id": project_id,
        "scan_request_id": scan_request_id,
        "ckg_summary": ckg_summary,
        "context_keys": list(context.keys()) if context else [],
        "template_variables": variables,
        "missing_variables": list(set(variables) - set(context.keys())) if context and variables else [],
    }
    
    debug_file = f"debug_full_scan_project_{project_id}.json"
    with open(debug_file, 'w', encoding='utf-8') as f:
        json.dump(debug_data, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n💾 Debug data saved to: {debug_file}")
    print(f"\n✅ Debug completed!")

if __name__ == "__main__":
    print("Usage: python debug_full_scan_prompt.py [project_id] [scan_request_id]")
    print("Example: python debug_full_scan_prompt.py 1 5")
    
    asyncio.run(main()) 