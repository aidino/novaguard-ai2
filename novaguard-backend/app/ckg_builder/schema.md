# Code Knowledge Graph (CKG) Schema Documentation

## Overview
The Code Knowledge Graph (CKG) is a Neo4j-based representation of code structure, relationships, and semantic information. It enables deep code analysis by capturing not just syntax but also semantic relationships between code entities.

## Node Types

### 1. Project
Represents a NovaGuard project/repository.

**Labels:** `:Project`

**Properties:**
- `graph_id` (string, unique): Composite identifier `novaguard_project_{project_id}`
- `name` (string): Repository name
- `novaguard_id` (string): Reference to NovaGuard project ID
- `language` (string): Primary programming language
- `created_at` (timestamp): Node creation time
- `updated_at` (timestamp): Last update time

### 2. File
Represents a source code file.

**Labels:** `:File`

**Properties:**
- `composite_id` (string, unique): `{project_graph_id}:{file_path}`
- `path` (string): File path within the repository
- `project_graph_id` (string): Reference to parent project
- `language` (string): File's programming language
- `size_bytes` (integer): File size in bytes
- `created_at` (timestamp): Node creation time
- `updated_at` (timestamp): Last update time

### 3. Module
Represents a logical module or namespace.

**Labels:** `:Module`

**Properties:**
- `composite_id` (string, unique): Module identifier within project
- `path` (string): Module path/namespace
- `name` (string): Module name
- `project_graph_id` (string): Reference to parent project

### 4. Class
Represents a class or type definition.

**Labels:** `:Class`

**Properties:**
- `composite_id` (string, unique): `{project_graph_id}:{file_path}:{class_name}:{start_line}`
- `name` (string): Class name
- `file_path` (string): File containing the class
- `start_line` (integer): Starting line number
- `end_line` (integer): Ending line number
- `project_graph_id` (string): Reference to parent project
- `placeholder` (boolean): Whether this is a placeholder for external class

### 5. Function
Represents functions and methods.

**Labels:** `:Function` (and `:Method` for class methods)

**Properties:**
- `composite_id` (string, unique): Function identifier
- `name` (string): Function/method name
- `file_path` (string): File containing the function
- `start_line` (integer): Starting line number
- `end_line` (integer): Ending line number
- `signature` (string): Function signature
- `parameters_str` (string): Parameter list as string
- `class_name` (string, optional): For methods, the containing class
- `is_method` (boolean): Whether this is a class method
- `project_graph_id` (string): Reference to parent project

### 6. Variable
Represents variables, parameters, and attributes.

**Labels:** `:Variable`

**Properties:**
- `composite_id` (string, unique): Variable identifier
- `name` (string): Variable name
- `file_path` (string): File containing the variable
- `start_line` (integer): Starting line number
- `end_line` (integer): Ending line number
- `scope_name` (string): Name of containing scope
- `scope_type` (string): Type of scope (parameter, local_variable, global_variable, class_attribute)
- `var_type` (string, optional): Variable type annotation
- `is_parameter` (boolean): Whether this is a function parameter
- `project_graph_id` (string): Reference to parent project

### 7. Decorator
Represents decorators applied to classes or functions.

**Labels:** `:Decorator`

**Properties:**
- `composite_id` (string, unique): Decorator identifier
- `name` (string): Decorator name
- `file_path` (string): File containing the decorator
- `start_line` (integer): Line number
- `project_graph_id` (string): Reference to parent project

### 8. ExceptionType
Represents exception types used in the codebase.

**Labels:** `:ExceptionType`

**Properties:**
- `name` (string): Exception type name
- `project_graph_id` (string): Reference to parent project

## Relationship Types

### 1. BELONGS_TO
Connects entities to their parent project.
- **From:** Any code entity
- **To:** `:Project`

### 2. DEFINED_IN
Connects code entities to the file where they are defined.
- **From:** `:Class`, `:Function`, etc.
- **To:** `:File`

### 3. DEFINED_IN_FILE
Specific relationship for global variables.
- **From:** `:Variable` (global)
- **To:** `:File`

### 4. HAS_PARAMETER
Connects functions to their parameters.
- **From:** `:Function`
- **To:** `:Variable` (parameter)

### 5. DECLARES_VARIABLE
Connects functions to local variables they declare.
- **From:** `:Function`
- **To:** `:Variable` (local)

### 6. DECLARES_ATTRIBUTE
Connects classes to their attributes.
- **From:** `:Class`
- **To:** `:Variable` (attribute)

### 7. CALLS
Represents function calls.
- **From:** `:Function`
- **To:** `:Function`
- **Properties:**
  - `call_site_line` (integer): Line where call occurs
  - `type` (string): Type of call

### 8. INHERITS_FROM
Represents class inheritance.
- **From:** `:Class`
- **To:** `:Class`

### 9. USES_VARIABLE
Represents variable usage within functions.
- **From:** `:Function`
- **To:** `:Variable`
- **Properties:**
  - `usage_line` (integer): Line where variable is used

### 10. MODIFIES_VARIABLE
Represents variable modification within functions.
- **From:** `:Function`
- **To:** `:Variable`
- **Properties:**
  - `modification_line` (integer): Line where variable is modified
  - `modification_type` (string): Type of modification

### 11. CREATES_OBJECT
Represents object instantiation.
- **From:** `:Function`
- **To:** `:Class`
- **Properties:**
  - `creation_line` (integer): Line where object is created

### 12. RAISES_EXCEPTION
Represents exception raising.
- **From:** `:Function`
- **To:** `:ExceptionType`

### 13. HANDLES_EXCEPTION
Represents exception handling.
- **From:** `:Function`
- **To:** `:ExceptionType`

### 14. DECORATED_BY
Represents decorator application.
- **From:** `:Function` or `:Class`
- **To:** `:Decorator`

## Current Language Support

### Python
- ✅ Classes and inheritance
- ✅ Functions and methods
- ✅ Variables (global, local, parameters, attributes)
- ✅ Function calls
- ✅ Imports
- ✅ Decorators
- ✅ Exception handling

### Other Languages
- ❌ JavaScript/TypeScript
- ❌ Java
- ❌ Go
- ❌ C/C++
- ❌ Rust

## Planned Enhancements

### Node Types to Add
- `:Interface` - Interface definitions
- `:Enum` - Enumeration types
- `:Constant` - Constant definitions
- `:APIEndpoint` - REST/GraphQL endpoints
- `:DatabaseTable` - Database schema entities
- `:ConfigurationFile` - Configuration files

### Relationship Types to Add
- `IMPLEMENTS` - Interface implementation
- `DEPENDS_ON` - Module dependencies
- `EXPOSES_API` - API exposure
- `ACCESSES_DB` - Database access
- `IMPORTS` - Import relationships with version tracking

### Enhanced Properties
- Code metrics (complexity, LOC, etc.)
- Documentation strings
- Type annotations
- Security annotations
- Performance characteristics

## Usage Examples

### Find all functions that call a specific function
```cypher
MATCH (caller:Function)-[:CALLS]->(target:Function {name: "target_function"})
RETURN caller.name, caller.file_path
```

### Find all classes that inherit from a base class
```cypher
MATCH (child:Class)-[:INHERITS_FROM*]->(base:Class {name: "BaseClass"})
RETURN child.name, child.file_path
```

### Find circular dependencies
```cypher
MATCH path = (a:Class)-[:CALLS*]->(a)
WHERE length(path) > 1
RETURN path
``` 