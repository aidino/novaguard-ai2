#!/usr/bin/env python3
"""
Script để check logs của analysis worker và xem prompt thực tế được gửi
"""
import subprocess
import re
import json
from datetime import datetime, timedelta

def get_worker_logs(lines=100):
    """Get worker logs from Docker"""
    print(f"📋 Getting Worker Logs (last {lines} lines)")
    print("=" * 50)
    
    try:
        # Get logs from novaguard_worker container
        result = subprocess.run(
            ["docker", "compose", "logs", "--tail", str(lines), "novaguard_analysis_worker"],
            capture_output=True,
            text=True,
            check=True
        )
        
        logs = result.stdout
        print(f"✅ Retrieved {len(logs.split('\\n'))} lines of logs")
        return logs
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error getting logs: {e}")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print(f"❌ Docker command not found. Make sure Docker is installed and running.")
        return None

def extract_full_scan_logs(logs):
    """Extract full scan related logs"""
    print(f"\\n🔍 Extracting Full Scan Logs")
    print("-" * 30)
    
    if not logs:
        return []
    
    # Look for full scan related log entries
    full_scan_patterns = [
        r".*Full.*[Ss]can.*",
        r".*create_full_project_dynamic_context.*",
        r".*query_ckg_for_project_summary.*",
        r".*run_full_project_analysis_agents.*",
        r".*architectural_analyst_full_project.*",
        r".*CKG Summary.*",
        r".*Dynamic Context.*"
    ]
    
    full_scan_logs = []
    lines = logs.split('\\n')
    
    for line in lines:
        for pattern in full_scan_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                full_scan_logs.append(line)
                break
    
    print(f"Found {len(full_scan_logs)} full scan related log entries")
    
    # Show recent ones
    recent_logs = full_scan_logs[-20:] if len(full_scan_logs) > 20 else full_scan_logs
    for i, log in enumerate(recent_logs, 1):
        # Clean up log format
        clean_log = re.sub(r'^.*?\\|', '', log).strip()
        print(f"   {i:2d}. {clean_log}")
    
    return full_scan_logs

def extract_context_data_logs(logs):
    """Extract context data from logs"""
    print(f"\\n📊 Extracting Context Data from Logs")
    print("-" * 30)
    
    if not logs:
        return {}
    
    context_data = {}
    lines = logs.split('\\n')
    
    # Look for specific context data patterns
    patterns = {
        'total_files': r'Total files: (\\d+)',
        'total_classes': r'Total classes: (\\d+)', 
        'total_functions': r'Total functions/methods: (\\d+)',
        'average_functions': r'Average functions per file: ([\\d.]+)',
        'project_name': r'project.*?([\\w/\\-]+)',
        'main_modules': r'Main modules.*?\\[(.*?)\\]',
        'largest_classes': r'Top 5 largest classes',
        'most_called': r'Top 5 most called functions'
    }
    
    for line in lines:
        for key, pattern in patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                if key not in context_data:
                    context_data[key] = []
                context_data[key].append(match.group(1) if match.groups() else match.group(0))
    
    # Show extracted data
    if context_data:
        print("✅ Extracted context data from logs:")
        for key, values in context_data.items():
            if len(values) == 1:
                print(f"   {key}: {values[0]}")
            else:
                print(f"   {key}: {values} (multiple entries)")
    else:
        print("❌ No context data found in logs")
    
    return context_data

def check_llm_prompt_logs(logs):
    """Check for LLM prompt related logs"""
    print(f"\\n🤖 Checking LLM Prompt Logs")
    print("-" * 30)
    
    if not logs:
        return
    
    # Look for LLM service logs
    llm_patterns = [
        r".*LLMService.*",
        r".*Final Formatted Prompt.*",
        r".*Raw LLM Response.*", 
        r".*Architectural analysis agent.*",
        r".*prompt template.*",
        r".*invoke_llm_analysis_chain.*"
    ]
    
    llm_logs = []
    lines = logs.split('\\n')
    
    for line in lines:
        for pattern in llm_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                llm_logs.append(line)
                break
    
    if llm_logs:
        print(f"Found {len(llm_logs)} LLM related log entries")
        
        # Show recent ones
        recent_llm_logs = llm_logs[-10:] if len(llm_logs) > 10 else llm_logs
        for i, log in enumerate(recent_llm_logs, 1):
            clean_log = re.sub(r'^.*?\\|', '', log).strip()
            # Truncate very long logs
            if len(clean_log) > 150:
                clean_log = clean_log[:150] + "..."
            print(f"   {i:2d}. {clean_log}")
            
        # Check for specific prompt debugging
        prompt_debug_logs = [log for log in llm_logs if "Final Formatted Prompt" in log or "prompt template" in log.lower()]
        if prompt_debug_logs:
            print(f"\\n🎯 Found {len(prompt_debug_logs)} prompt debugging logs")
        else:
            print(f"\\n⚠️ No detailed prompt debugging logs found")
            print(f"   Suggestion: Set logging level to DEBUG to see full prompts")
    else:
        print("❌ No LLM related logs found")

def check_error_logs(logs):
    """Check for error logs"""
    print(f"\\n❌ Checking Error Logs")
    print("-" * 30)
    
    if not logs:
        return
    
    error_patterns = [
        r".*ERROR.*",
        r".*Exception.*",
        r".*Traceback.*",
        r".*Failed.*",
        r".*missing.*variables.*"
    ]
    
    error_logs = []
    lines = logs.split('\\n')
    
    for line in lines:
        for pattern in error_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                error_logs.append(line)
                break
    
    if error_logs:
        print(f"Found {len(error_logs)} error/warning entries")
        
        # Show recent errors
        recent_errors = error_logs[-10:] if len(error_logs) > 10 else error_logs
        for i, log in enumerate(recent_errors, 1):
            clean_log = re.sub(r'^.*?\\|', '', log).strip()
            print(f"   {i:2d}. {clean_log}")
    else:
        print("✅ No errors found in recent logs")

def suggest_debugging_steps():
    """Suggest next debugging steps"""
    print(f"\\n💡 Debugging Suggestions")
    print("=" * 50)
    
    suggestions = [
        "1. Check if CKG data is being properly generated for the project",
        "2. Verify that all required variables are in the dynamic context",
        "3. Enable DEBUG logging to see full prompts",
        "4. Check for template variable syntax errors",
        "5. Test with a real full scan request to see actual data flow",
        "6. Verify Neo4j connection and CKG query results"
    ]
    
    for suggestion in suggestions:
        print(f"   {suggestion}")
    
    print(f"\\n🔧 Commands to run:")
    print(f"   # Enable DEBUG logging:")
    print(f"   docker compose exec novaguard_backend_api python -c \"import logging; logging.basicConfig(level=logging.DEBUG)\"")
    print(f"   ")
    print(f"   # Check Neo4j data:")
    print(f"   docker compose exec novaguard_neo4j cypher-shell -u neo4j -p yourStrongPassword")
    print(f"   ")
    print(f"   # Trigger a test full scan:")
    print(f"   curl -X POST http://localhost:8000/dashboard  # (after login)")

def main():
    """Main function"""
    print("🚀 NovaGuard Full Scan Prompt Logs Analyzer")
    print("=" * 60)
    
    # Get worker logs
    logs = get_worker_logs(200)  # Get more logs for better analysis
    
    if not logs:
        print("❌ Cannot proceed without logs")
        return
    
    # Extract different types of information
    full_scan_logs = extract_full_scan_logs(logs)
    context_data = extract_context_data_logs(logs)
    
    # Check LLM and error logs
    check_llm_prompt_logs(logs)
    check_error_logs(logs)
    
    # Save analysis results
    analysis_results = {
        "timestamp": datetime.now().isoformat(),
        "total_log_lines": len(logs.split('\\n')),
        "full_scan_log_count": len(full_scan_logs),
        "context_data": context_data,
        "recent_full_scan_logs": full_scan_logs[-10:] if full_scan_logs else []
    }
    
    with open("prompt_logs_analysis.json", 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, indent=2, ensure_ascii=False)
    
    print(f"\\n💾 Analysis results saved to: prompt_logs_analysis.json")
    
    # Provide debugging suggestions
    suggest_debugging_steps()

if __name__ == "__main__":
    main() 