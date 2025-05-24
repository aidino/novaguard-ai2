# NovaGuard AI: Android/Java/Kotlin Support Roadmap

## Overview
This roadmap outlines the implementation plan to add comprehensive Android, Java, and Kotlin project scanning capabilities to NovaGuard AI.

**Total Estimated Time:** 10-17 weeks  
**Start Date:** [TBD]  
**Target Completion:** [TBD]

---

## Phase 1: Core Language Parser Development
**Duration:** 2-3 weeks | **Priority:** High | **Dependencies:** None

### Java Parser Enhancement
- [ ] Create `novaguard-backend/app/ckg_builder/parsers/java_parser.py`
- [ ] Implement Java AST parsing using `javalang` or similar library
- [ ] Extract class declarations (regular, abstract, final)
- [ ] Extract interface and enum declarations
- [ ] Parse method signatures with modifiers and return types
- [ ] Extract field declarations with access modifiers
- [ ] Parse inheritance relationships (`extends`, `implements`)
- [ ] Handle generics and type parameters
- [ ] Extract import statements and package declarations
- [ ] Parse annotations and their parameters
- [ ] Handle nested classes and inner classes
- [ ] Add support for lambda expressions and method references
- [ ] Test with sample Java files

### Kotlin Parser Development
- [ ] Create `novaguard-backend/app/ckg_builder/parsers/kotlin_parser.py`
- [ ] Set up Kotlin AST parsing (using `kotlinx.ast` or custom solution)
- [ ] Parse class declarations (class, data class, sealed class)
- [ ] Extract object declarations and companion objects
- [ ] Parse function declarations with Kotlin-specific features
- [ ] Handle extension functions and properties
- [ ] Extract property declarations with getters/setters
- [ ] Parse coroutine functions (`suspend` functions)
- [ ] Handle nullable types and null safety annotations
- [ ] Extract interface implementations and class inheritance
- [ ] Parse enum classes and sealed classes
- [ ] Handle when expressions and pattern matching
- [ ] Test with sample Kotlin files

### Android-Specific Parsers
- [ ] Create `novaguard-backend/app/ckg_builder/parsers/android_manifest_parser.py`
- [ ] Parse AndroidManifest.xml structure
- [ ] Extract application metadata
- [ ] Parse activity declarations and intent filters
- [ ] Extract service, receiver, and provider declarations
- [ ] Parse permission declarations and uses
- [ ] Handle manifest placeholders and build variants
- [ ] Create `novaguard-backend/app/ckg_builder/parsers/gradle_parser.py`
- [ ] Parse build.gradle and build.gradle.kts files
- [ ] Extract dependencies (implementation, api, testImplementation)
- [ ] Parse build variants and product flavors
- [ ] Extract plugin configurations
- [ ] Parse version catalogs and dependency management
- [ ] Create `novaguard-backend/app/ckg_builder/parsers/android_xml_parser.py`
- [ ] Parse Android layout XML files
- [ ] Extract view hierarchies and custom views
- [ ] Parse string resources and other value resources
- [ ] Handle data binding and view binding expressions
- [ ] Extract style and theme definitions

---

## Phase 2: CKG Schema Extension
**Duration:** 1 week | **Priority:** High | **Dependencies:** Phase 1

### New Node Types
- [ ] Add Android component node types to CKG schema:
  - [ ] `AndroidActivity`
  - [ ] `AndroidService` 
  - [ ] `AndroidFragment`
  - [ ] `AndroidReceiver`
  - [ ] `AndroidProvider`
  - [ ] `AndroidPermission`
  - [ ] `GradleDependency`
  - [ ] `AndroidResource`
  - [ ] `KotlinCoroutine`
  - [ ] `JavaAnnotation`
- [ ] Update node creation logic in CKG builder
- [ ] Add node property schemas for each type
- [ ] Test node creation and storage

### New Relationship Types
- [ ] Add Android-specific relationship types:
  - [ ] `DECLARES_PERMISSION`
  - [ ] `USES_RESOURCE`
  - [ ] `LAUNCHES_ACTIVITY`
  - [ ] `BINDS_SERVICE`
  - [ ] `SENDS_BROADCAST`
  - [ ] `IMPLEMENTS_INTERFACE`
  - [ ] `DEPENDS_ON`
  - [ ] `OVERRIDES_METHOD`
  - [ ] `ANNOTATED_WITH`
  - [ ] `CALLS_SUSPEND`
- [ ] Update relationship creation logic
- [ ] Add relationship property schemas
- [ ] Test relationship creation and queries

---

## Phase 3: Android Project Detection & Structure Analysis
**Duration:** 1-2 weeks | **Priority:** High | **Dependencies:** Phase 1-2

### Project Type Detection
- [ ] Create `novaguard-backend/app/project_service/android_detector.py`
- [ ] Implement `detect_android_project()` function
- [ ] Check for Android-specific files (build.gradle, AndroidManifest.xml)
- [ ] Detect project structure (single module vs multi-module)
- [ ] Identify source sets (main, test, androidTest)
- [ ] Update project model to include Android-specific fields
- [ ] Add database migration for Android project fields

### Android Project Structure Parser
- [ ] Create `AndroidProjectStructure` class
- [ ] Implement module discovery logic
- [ ] Parse source set configurations
- [ ] Identify resource directories
- [ ] Map build variants and flavors
- [ ] Extract target/min SDK versions
- [ ] Calculate Kotlin vs Java ratio
- [ ] Test with various Android project structures

---

## Phase 4: Language-Specific Analysis Agents
**Duration:** 2-3 weeks | **Priority:** Medium | **Dependencies:** Phase 1-3

### Java Analysis Agent
- [ ] Create `novaguard-backend/app/analysis_module/java_analysis_agent.py`
- [ ] Implement code smell detection:
  - [ ] God classes (>500 lines)
  - [ ] Long parameter lists (>7 parameters)
  - [ ] Deep inheritance hierarchies (>5 levels)
  - [ ] Unused imports detection
  - [ ] Missing documentation detection
  - [ ] Cyclomatic complexity analysis
- [ ] Implement design pattern detection:
  - [ ] Singleton pattern detection
  - [ ] Factory pattern detection
  - [ ] Observer pattern detection
  - [ ] Builder pattern detection
- [ ] Add performance issue detection
- [ ] Test with sample Java codebases

### Kotlin Analysis Agent
- [ ] Create `novaguard-backend/app/analysis_module/kotlin_analysis_agent.py`
- [ ] Implement Kotlin idiom analysis:
  - [ ] Data class best practices
  - [ ] Extension function usage patterns
  - [ ] Scope function usage (let, run, with, apply, also)
  - [ ] Null safety violations
  - [ ] Immutability recommendations
- [ ] Implement coroutine analysis:
  - [ ] Proper coroutine scope usage
  - [ ] Main thread safety
  - [ ] Resource cleanup in coroutines
  - [ ] Structured concurrency violations
- [ ] Add Kotlin-specific performance analysis
- [ ] Test with sample Kotlin codebases

### Android-Specific Analysis Agent
- [ ] Create `novaguard-backend/app/analysis_module/android_analysis_agent.py`
- [ ] Implement Android-specific issue detection:
  - [ ] Memory leak detection (static context references)
  - [ ] ANR risk analysis (main thread blocking)
  - [ ] Battery optimization issues
  - [ ] Security vulnerability detection
  - [ ] Component lifecycle violations
  - [ ] Fragment transaction issues
  - [ ] Resource management problems
  - [ ] Exported component security
- [ ] Add Android architecture analysis:
  - [ ] MVP/MVVM/MVI pattern detection
  - [ ] Clean Architecture compliance
  - [ ] Dependency injection usage
- [ ] Implement performance optimizations detection
- [ ] Test with sample Android applications

---

## Phase 5: Enhanced LLM Prompts for Android
**Duration:** 1-2 weeks | **Priority:** Medium | **Dependencies:** Phase 4

### Android-Specific Prompt Templates
- [ ] Create `novaguard-backend/app/prompts/android_architecture_analyst.md`
- [ ] Create `novaguard-backend/app/prompts/android_performance_analyst.md`
- [ ] Create `novaguard-backend/app/prompts/android_security_analyst.md`
- [ ] Create `novaguard-backend/app/prompts/kotlin_code_reviewer.md`
- [ ] Create `novaguard-backend/app/prompts/java_code_reviewer.md`
- [ ] Create `novaguard-backend/app/prompts/android_lifecycle_analyst.md`

### Enhanced Context Building
- [ ] Create `create_android_analysis_context()` function
- [ ] Add Android component extraction to context
- [ ] Include Gradle dependency information
- [ ] Add permissions and security context
- [ ] Include target SDK and build variant info
- [ ] Add resource usage statistics
- [ ] Calculate and include Kotlin percentage
- [ ] Add architecture pattern detection context
- [ ] Test context generation with various projects

---

## Phase 6: Integration & Testing
**Duration:** 1-2 weeks | **Priority:** High | **Dependencies:** Phase 1-5

### File Type Detection Updates
- [ ] Update `SUPPORTED_FILE_EXTENSIONS` in ckg_builder
- [ ] Add Android-specific file type mapping:
  - [ ] `.java` → `java`
  - [ ] `.kt` → `kotlin`
  - [ ] `.kts` → `kotlin_script`
  - [ ] `.xml` → `android_xml`
  - [ ] `.gradle` → `gradle`
  - [ ] `.gradle.kts` → `gradle_kotlin`
  - [ ] `.pro` → `proguard`
- [ ] Update file processing logic
- [ ] Test file detection with Android projects

### CKG Builder Updates
- [ ] Update `novaguard-backend/app/ckg_builder/builder.py`
- [ ] Add `build_for_android_project()` method
- [ ] Integrate all Android parsers
- [ ] Add Android component relationship building
- [ ] Update project graph building logic
- [ ] Add Android-specific node creation
- [ ] Test CKG building with Android projects

### Database Schema Updates
- [ ] Create migration script for Android support
- [ ] Add Android-specific columns to projects table:
  - [ ] `android_target_sdk`
  - [ ] `android_min_sdk`
  - [ ] `android_compile_sdk`
  - [ ] `has_kotlin`
  - [ ] `kotlin_percentage`
  - [ ] `android_architecture_pattern`
- [ ] Update project model classes
- [ ] Test database migrations

### API Endpoints Updates
- [ ] Update project creation API to handle Android projects
- [ ] Add Android-specific project metadata endpoints
- [ ] Update graph visualization APIs for Android components
- [ ] Add Android component filtering options
- [ ] Test API endpoints with Android projects

---

## Phase 7: Visualization Enhancements
**Duration:** 1-2 weeks | **Priority:** Low | **Dependencies:** Phase 6

### Android Component Graph Visualization
- [ ] Add new display mode: `android_architecture`
- [ ] Create Android component visualization styles
- [ ] Add component lifecycle visualization
- [ ] Implement permission dependency graph
- [ ] Add module dependency visualization
- [ ] Create resource usage visualization

### Frontend Enhancements
- [ ] Update `novaguard-backend/app/static/js/ckg_graph.js`
- [ ] Add Android node styles and icons:
  - [ ] Activity (📱)
  - [ ] Service (⚙️)
  - [ ] Fragment (🧩)
  - [ ] Receiver (📡)
  - [ ] Coroutine (⚡)
- [ ] Add Android-specific layout algorithms
- [ ] Implement component grouping by module
- [ ] Add filtering by component type
- [ ] Update report templates for Android projects
- [ ] Test visualization with various Android projects

### Report Template Updates
- [ ] Update `full_scan_report.html` for Android projects
- [ ] Add Android-specific findings sections
- [ ] Create Android architecture summary section
- [ ] Add component dependency visualization
- [ ] Include Android-specific metrics display
- [ ] Test report generation

---

## Phase 8: Testing & Validation
**Duration:** 1 week | **Priority:** High | **Dependencies:** All phases

### Test Project Creation
- [ ] Create simple Android app (Java only) for testing
- [ ] Create Kotlin-first Android app for testing
- [ ] Set up multi-module Android project for testing
- [ ] Prepare Android library project for testing
- [ ] Create mixed Java/Kotlin project for testing
- [ ] Document test project structures

### Analysis Validation Tests
- [ ] Create `test_android_memory_leak_detection()`
- [ ] Create `test_kotlin_coroutine_analysis()`
- [ ] Create `test_android_manifest_parsing()`
- [ ] Create `test_gradle_dependency_extraction()`
- [ ] Create `test_android_component_relationships()`
- [ ] Create `test_java_parser_accuracy()`
- [ ] Create `test_kotlin_parser_accuracy()`
- [ ] Run comprehensive test suite
- [ ] Validate analysis results manually
- [ ] Document any issues found

### Performance Testing
- [ ] Test parsing performance with large Android projects
- [ ] Measure CKG building time for Android projects
- [ ] Test visualization rendering performance
- [ ] Optimize any performance bottlenecks
- [ ] Document performance benchmarks

### User Acceptance Testing
- [ ] Test full workflow with real Android projects
- [ ] Validate analysis quality and relevance
- [ ] Test UI/UX for Android project reports
- [ ] Gather feedback from Android developers
- [ ] Make improvements based on feedback

---

## Quick Start Implementation Priority

### Immediate Tasks (Week 1-2)
- [ ] Phase 1: Java parser (basic functionality)
- [ ] Phase 2: Basic node types for Java
- [ ] Phase 3: Android project detection
- [ ] Basic integration test

### Short Term (Week 3-6)
- [ ] Phase 1: Complete Kotlin parser
- [ ] Phase 1: Android manifest parser
- [ ] Phase 4: Basic Java analysis agent
- [ ] Phase 6: CKG builder integration

### Medium Term (Week 7-12)
- [ ] Phase 4: Complete analysis agents
- [ ] Phase 5: LLM prompt templates
- [ ] Phase 6: Complete integration
- [ ] Phase 8: Testing and validation

### Long Term (Week 13-17)
- [ ] Phase 7: Visualization enhancements
- [ ] Phase 8: Performance optimization
- [ ] Documentation and user guides
- [ ] Production deployment

---

## Success Metrics

- [ ] Successfully parse and analyze Java projects
- [ ] Successfully parse and analyze Kotlin projects  
- [ ] Successfully parse and analyze Android projects
- [ ] Generate meaningful findings for Android-specific issues
- [ ] Visualization correctly displays Android architecture
- [ ] Performance meets requirements for large projects
- [ ] User satisfaction with Android project analysis

---

## Notes

- Update this checklist as tasks are completed
- Add specific dates when tasks are started/completed
- Note any blockers or dependencies that arise
- Track time spent vs estimates for future planning

**Last Updated:** [Date]  
**Completed Tasks:** 0 / [Total Tasks]  
**Current Phase:** Not Started 