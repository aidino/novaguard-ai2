# LLM Output Logging Documentation

## Overview

Comprehensive logging has been added to the NovaGuard analysis worker to provide detailed visibility into LLM interactions, outputs, and parsing processes. This makes debugging and monitoring much easier.

## Logging Levels

### INFO Level Logs (Always Visible)
- LLM request initiation
- Raw LLM response content  
- Parsing success/failure status
- Final parsed output (JSON format)
- Analysis results summary
- Error messages

### DEBUG Level Logs (When DEBUG enabled)
- Format instructions sent to LLM
- Full formatted prompt content
- Dynamic context details
- Parsing error details

## LLM Service Logging (`app/llm_service/service.py`)

### 1. **Request Initiation**
```
LLMService: Invoking analysis chain with provider: openai, model: gpt-4o-mini-2024-07-18
LLMService: Sending request to openai (gpt-4o-mini-2024-07-18)...
```

### 2. **Raw LLM Response**
```
LLMService: Raw LLM Response from openai (gpt-4o-mini-2024-07-18):
---RAW LLM OUTPUT START---
{
  "findings": [
    {
      "file_path": "app/models/user.py",
      "line_start": 42,
      "severity": "Error",
      "message": "Function get_user() can return None but is accessed without null check"
    }
  ]
}
---RAW LLM OUTPUT END---
```

### 3. **Parsing Status**
```
LLMService: ✅ Successfully parsed response with basic Pydantic parser
```
or
```
LLMService: ⚠️ Basic Pydantic parsing failed: ValidationError...
LLMService: Attempting to fix response using OutputFixingParser...
LLMService: ✅ Successfully parsed response using OutputFixingParser
```

### 4. **Final Parsed Output**
```
LLMService: Final Parsed Output (JSON):
---PARSED OUTPUT START---
{
  "findings": [
    {
      "file_path": "app/models/user.py",
      "line_start": 42,
      "line_end": 45,
      "severity": "Error",
      "message": "Function get_user() can return None but is accessed without null check",
      "suggestion": "Add null check before accessing user properties",
      "finding_type": "logic_error",
      "meta_data": {
        "function_name": "get_user",
        "issue_type": "null_pointer"
      }
    }
  ]
}
---PARSED OUTPUT END---
```

### 5. **Analysis Summary**
```
LLMService: Analysis Summary - Found 3 findings
LLMService: Finding #1: Error in app/models/user.py - Function get_user() can return None but is accessed without null check...
LLMService: Finding #2: Warning in app/api/auth.py - Missing rate limiting on authentication endpoint...
```

## Worker Analysis Logging (`app/analysis_worker/consumer.py`)

### 1. **PR Analysis Results**
```
Worker (PR): LLM Analysis Results Summary for 'Fix user authentication bug':
Worker (PR): Finding #1: [Error] app/models/user.py L42 - Function get_user() can return None but is accessed...
Worker (PR): Finding #2: [Warning] app/api/auth.py L15 - Missing rate limiting on authentication...
Worker (PR): Severity breakdown: {'Error': 1, 'Warning': 2}
Worker (PR): Files with issues: 2
```

### 2. **Full Project Analysis Results**
```
Worker (Full Scan): Full Project Analysis Results for 'novaguard-ai2':
Worker (Full Scan): - Project-level findings: 2
Worker (Full Scan): - Granular findings: 0
Worker (Full Scan): Project Summary: The project consists of 53 files and 75 classes with moderate complexity...
Worker (Full Scan): Project Finding #1: [Warning] Code Quality - TestProjectCRUD class has 10 methods... (Components: test_crud_project.py)
Worker (Full Scan): Project findings severity breakdown: {'Warning': 2}
```

## Debug Level Logging

### Format Instructions
```
LLMService: Format instructions sent to LLM:
The output should be formatted as a JSON instance that conforms to the JSON schema below...
```

### Full Prompt Content  
```
LLMService: Final Formatted Prompt:
---PROMPT START---
Human: You are an expert code reviewer AI specializing in deep logic analysis...
---PROMPT END---
```

## Error Logging

### Parsing Failures
```
LLMService: ❌ OutputFixingParser also failed: ValidationError
LLMService: Raw response that failed to parse:
{ "findings": [ invalid json here...
```

### LLM Service Errors
```
LLMService: LangChain specific error during chain invocation with openai: API rate limit exceeded
```

## Benefits for Debugging

### 1. **Hallucination Detection**
- Raw LLM output shows if fictional file paths are generated
- Easy to spot when LLM creates non-existent files

### 2. **JSON Format Issues**
- See exact parsing errors and what OutputFixingParser attempts
- Raw vs parsed output comparison

### 3. **Analysis Quality Assessment**
- Summary statistics show finding distribution
- Easy to identify if analysis is too strict or lenient

### 4. **Performance Monitoring**
- Track LLM response times and success rates
- Identify which models/providers work best

### 5. **Troubleshooting**
- Complete visibility into the analysis pipeline
- Step-by-step debugging capability

## Log Example: Full Analysis Flow

```
2025-05-23 04:15:22 - LLMService: Invoking analysis chain with provider: openai, model: gpt-4o-mini-2024-07-18
2025-05-23 04:15:22 - LLMService: Sending request to openai (gpt-4o-mini-2024-07-18)...
2025-05-23 04:15:25 - LLMService: Raw LLM Response from openai (gpt-4o-mini-2024-07-18):
---RAW LLM OUTPUT START---
{
  "project_summary": "The project 'novaguard-ai2' consists of 53 files and 75 classes...",
  "project_level_findings": [
    {
      "finding_category": "Code Quality",
      "description": "TestProjectCRUD class has 10 methods approaching god class threshold",
      "severity": "Warning",
      "relevant_components": ["tests/project_service/test_crud_project.py"]
    }
  ],
  "granular_findings": []
}
---RAW LLM OUTPUT END---
2025-05-23 04:15:25 - LLMService: ✅ Successfully parsed response with basic Pydantic parser
2025-05-23 04:15:25 - LLMService: Final Parsed Output (JSON):
---PARSED OUTPUT START---
{
  "project_summary": "The project 'novaguard-ai2' consists of 53 files and 75 classes...",
  "project_level_findings": [
    {
      "finding_category": "Code Quality", 
      "description": "TestProjectCRUD class has 10 methods approaching god class threshold",
      "severity": "Warning",
      "relevant_components": ["tests/project_service/test_crud_project.py"]
    }
  ],
  "granular_findings": []
}
---PARSED OUTPUT END---
2025-05-23 04:15:25 - LLMService: Project Analysis Summary - 1 project findings, 0 granular findings
2025-05-23 04:15:25 - LLMService: Project Summary: The project 'novaguard-ai2' consists of 53 files and 75 classes...
2025-05-23 04:15:25 - Worker (Full Scan): Full Project Analysis Results for 'novaguard-ai2':
2025-05-23 04:15:25 - Worker (Full Scan): - Project-level findings: 1
2025-05-23 04:15:25 - Worker (Full Scan): - Granular findings: 0
2025-05-23 04:15:25 - Worker (Full Scan): Project Finding #1: [Warning] Code Quality - TestProjectCRUD class has 10 methods...
```

## Configuration

The logging respects the existing logger configuration:
- **INFO level**: Always shows key information and results
- **DEBUG level**: Shows detailed technical information
- **ERROR level**: Shows parsing failures and service errors

To enable debug logging, set the log level to DEBUG in your environment configuration. 