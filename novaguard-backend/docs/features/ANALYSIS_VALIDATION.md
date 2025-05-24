# NovaGuard AI Full Scan Hallucination Fix

## Issue Analysis

The Full Scan analysis was experiencing LLM hallucination where the model generated findings about non-existent files and entities:

### Observed Hallucinations:
- **Fictional Files**: `src/data_processor.py`, `src/utils.py`, `src/metrics.py`
- **Non-existent Classes**: `DataProcessor` with 15 methods
- **Imaginary Functions**: `calculate_metrics` called 8 times
- **Wrong Directory Structure**: Using `src/` instead of actual `novaguard-backend/app/`

### Root Causes:
1. **Insufficient Anti-Hallucination Constraints** in the prompt
2. **Missing Data Validation** in Pydantic schemas
3. **Sparse CKG Data** leading to LLM filling gaps with fictional content
4. **Schema Validation Issues** (dict instead of string for project_summary)

## Implemented Solutions

### 1. Enhanced Prompt Template (`architectural_analyst_full_project_v1.md`)

#### Added Strong Anti-Hallucination Measures:
```markdown
## ⚠️ CRITICAL ANTI-HALLUCINATION REQUIREMENTS ⚠️

**ABSOLUTE PROHIBITION**: 
- DO NOT analyze fictional files like "src/data_processor.py", "src/utils.py"
- DO NOT reference non-existent classes like "DataProcessor", "UserManager"
- DO NOT mention imaginary functions like "calculate_metrics"

**VERIFICATION CHECKPOINT**: Before writing ANY finding, ask yourself:
- ❓ Is this file path in the actual CKG data provided?
- ❓ Is this class name from the real `top_5_largest_classes_by_methods` list?
- ❓ Is this function from the real `top_5_most_called_functions` list?
```

#### Real Data Examples:
```markdown
✅ **CORRECT**: "Based on CKG data, class 'TestProjectCRUD' in file 'tests/project_service/test_crud_project.py' has 12 methods"

❌ **WRONG**: "The DataProcessor class has too many responsibilities."
```

### 2. Enhanced Pydantic Schema Validation (`llm_schemas.py`)

#### Added Robust Field Validators:
```python
@field_validator('project_summary', mode='before')
@classmethod
def _validate_project_summary(cls, value):
    """Ensure project_summary is a string, not a dict"""
    if isinstance(value, dict):
        logger.warning(f"LLM returned dict for project_summary, converting to string.")
        return f"Project contains {value.get('total_files', 'unknown')} files..."
    return value

@field_validator('severity', mode='before')  
@classmethod
def _validate_severity(cls, value: str) -> SeverityLevel:
    try:
        return SeverityLevel(value.capitalize())
    except ValueError:
        logger.warning(f"Invalid severity value '{value}'. Defaulting to Note.")
        return SeverityLevel.NOTE
```

### 3. CKG Data Quality Monitoring (`consumer.py`)

#### Added Comprehensive Logging:
```python
# Enhanced logging to debug CKG data quality
logger.info(f"Full project dynamic context - CKG Summary for {project_model.repo_name}:")
logger.info(f"  - Total files: {ckg_summary.get('total_files', 0)}")
logger.info(f"  - Total classes: {ckg_summary.get('total_classes', 0)}")

if ckg_summary.get('top_5_largest_classes_by_methods'):
    logger.info(f"  - Top 5 largest classes:")
    for i, cls in enumerate(ckg_summary['top_5_largest_classes_by_methods'][:5], 1):
        logger.info(f"    {i}. {cls.get('name')} ({cls.get('method_count')} methods)")
```

### 4. Empty Data Safeguards

#### Intelligent Fallback for Sparse CKG Data:
```python
has_meaningful_data = (
    ckg_summary.get('total_files', 0) > 0 and
    total_entities > 0 and
    (ckg_summary.get('top_5_largest_classes_by_methods') or 
     ckg_summary.get('top_5_most_called_functions') or
     ckg_summary.get('main_modules'))
)

if not has_meaningful_data:
    # Provide basic summary without LLM to avoid hallucination
    basic_summary = f"Project analysis completed. Analyzed {total_files} files..."
    return basic_response
```

## Validation Steps

### 1. Check Logs for CKG Data Quality
Monitor worker logs for:
```
Full project dynamic context - CKG Summary for [project]:
  - Total files: [number]
  - Top 5 largest classes:
    1. [ClassName] ([X] methods) in [real/file/path]
```

### 2. Verify Real Entity References
Ensure findings reference actual project entities:
```json
{
  "project_level_findings": [
    {
      "description": "Class 'TestProjectCRUD' (from CKG data) has 12 methods...",
      "relevant_components": ["tests/project_service/test_crud_project.py"]
    }
  ]
}
```

### 3. Schema Validation Success
Look for successful parsing logs:
```
LLMService: ✅ Successfully parsed response with basic Pydantic parser
LLMService: Project Analysis Summary - [X] project findings, [Y] granular findings
```

### 4. Anti-Hallucination Effectiveness
Confirm absence of:
- Fictional file paths (src/data_processor.py, etc.)
- Non-existent classes (DataProcessor, UserManager, etc.)
- Imaginary functions (calculate_metrics, process_data, etc.)

## Expected Improvements

### Before Fix:
```
❌ Findings about "DataProcessor" class with 15 methods
❌ References to "src/utils.py" with 20 functions  
❌ "calculate_metrics" function called 8 times
❌ project_summary as dict causing validation errors
```

### After Fix:
```
✅ Real findings about actual classes from CKG data
✅ References to real file paths from project structure
✅ Actual function names from top_5_most_called_functions
✅ project_summary as proper string
```

## Monitoring and Maintenance

### Key Metrics to Track:
1. **Hallucination Rate**: Percentage of findings referencing non-existent entities
2. **CKG Data Quality**: Average entities per project analysis
3. **Validation Success**: Pydantic parsing success rate
4. **Real Entity Coverage**: Percentage of findings using CKG data

### Red Flags to Watch:
- Empty `top_5_largest_classes_by_methods` arrays
- Zero total_files or total_classes in CKG summary
- Validation errors for project_summary format
- Generic file names in findings (module1.py, utils.py)

### Regular Validation:
```bash
# Check recent analysis logs for hallucination patterns
grep -E "(src/|DataProcessor|calculate_metrics)" worker_logs.txt

# Verify CKG data quality
grep "CKG Summary for" worker_logs.txt -A 10

# Monitor validation success rates  
grep "Successfully parsed response" worker_logs.txt | wc -l
```

This comprehensive fix addresses the hallucination issue through multiple layers of validation, ensuring the LLM analyzes only real project data while providing meaningful fallbacks for sparse datasets. 