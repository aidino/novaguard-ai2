// === Constraints (Ensure Uniqueness) ===

// Project Node
CREATE CONSTRAINT project_graph_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.graph_id IS UNIQUE;

// File Node
CREATE CONSTRAINT file_composite_id_unique IF NOT EXISTS FOR (f:File) REQUIRE f.composite_id IS UNIQUE;

// Module Node (assuming module_path within a project is unique)
CREATE CONSTRAINT module_composite_id_unique IF NOT EXISTS FOR (m:Module) REQUIRE m.composite_id IS UNIQUE;

// Class Node
CREATE CONSTRAINT class_composite_id_unique IF NOT EXISTS FOR (c:Class) REQUIRE c.composite_id IS UNIQUE;

// Function Node (includes Methods as they also have :Function label)
CREATE CONSTRAINT function_composite_id_unique IF NOT EXISTS FOR (fn:Function) REQUIRE fn.composite_id IS UNIQUE;

// Variable Node (includes Parameters, Local Variables, Attributes)
CREATE CONSTRAINT variable_composite_id_unique IF NOT EXISTS FOR (v:Variable) REQUIRE v.composite_id IS UNIQUE;

// Decorator Node (composite_id based on project, file, name, line)
CREATE CONSTRAINT decorator_composite_id_unique IF NOT EXISTS FOR (d:Decorator) REQUIRE d.composite_id IS UNIQUE;
// Alternative: If decorator name is considered unique per project (less precise)
// CREATE CONSTRAINT decorator_name_project_unique IF NOT EXISTS FOR (d:Decorator) REQUIRE (d.name, d.project_graph_id) IS UNIQUE;

// ExceptionType Node (name unique per project)
CREATE CONSTRAINT exception_type_name_project_unique IF NOT EXISTS FOR (et:ExceptionType) REQUIRE (et.name, et.project_graph_id) IS UNIQUE;


// === Indexes (Improve Query Performance) ===

// Project Node
CREATE INDEX project_novaguard_id_idx IF NOT EXISTS FOR (p:Project) ON (p.novaguard_id);
CREATE INDEX project_name_idx IF NOT EXISTS FOR (p:Project) ON (p.name);

// File Node
CREATE INDEX file_path_idx IF NOT EXISTS FOR (f:File) ON (f.path);
CREATE INDEX file_project_graph_id_idx IF NOT EXISTS FOR (f:File) ON (f.project_graph_id);
CREATE INDEX file_language_idx IF NOT EXISTS FOR (f:File) ON (f.language);

// Module Node
CREATE INDEX module_path_idx IF NOT EXISTS FOR (m:Module) ON (m.path);
CREATE INDEX module_project_graph_id_idx IF NOT EXISTS FOR (m:Module) ON (m.project_graph_id);
CREATE INDEX module_name_idx IF NOT EXISTS FOR (m:Module) ON (m.name);

// Class Node
CREATE INDEX class_name_idx IF NOT EXISTS FOR (c:Class) ON (c.name);
CREATE INDEX class_file_path_idx IF NOT EXISTS FOR (c:Class) ON (c.file_path); // If querying classes by file
CREATE INDEX class_project_graph_id_idx IF NOT EXISTS FOR (c:Class) ON (c.project_graph_id);
CREATE INDEX class_placeholder_idx IF NOT EXISTS FOR (c:Class) ON (c.placeholder); // If you query for placeholders

// Function Node (includes Methods)
CREATE INDEX function_name_idx IF NOT EXISTS FOR (fn:Function) ON (fn.name);
CREATE INDEX function_file_path_idx IF NOT EXISTS FOR (fn:Function) ON (fn.file_path);
CREATE INDEX function_class_name_idx IF NOT EXISTS FOR (fn:Function) ON (fn.class_name) WHERE fn.class_name IS NOT NULL;
CREATE INDEX function_project_graph_id_idx IF NOT EXISTS FOR (fn:Function) ON (fn.project_graph_id);
CREATE INDEX function_is_method_idx IF NOT EXISTS FOR (fn:Function) ON (fn.is_method);


// Variable Node
CREATE INDEX variable_name_idx IF NOT EXISTS FOR (v:Variable) ON (v.name);
CREATE INDEX variable_scope_name_idx IF NOT EXISTS FOR (v:Variable) ON (v.scope_name);
CREATE INDEX variable_scope_type_idx IF NOT EXISTS FOR (v:Variable) ON (v.scope_type);
CREATE INDEX variable_file_path_idx IF NOT EXISTS FOR (v:Variable) ON (v.file_path);
CREATE INDEX variable_project_graph_id_idx IF NOT EXISTS FOR (v:Variable) ON (v.project_graph_id);
CREATE INDEX variable_is_parameter_idx IF NOT EXISTS FOR (v:Variable) ON (v.is_parameter);

// Decorator Node
CREATE INDEX decorator_name_idx IF NOT EXISTS FOR (d:Decorator) ON (d.name);
CREATE INDEX decorator_project_graph_id_idx IF NOT EXISTS FOR (d:Decorator) ON (d.project_graph_id);

// ExceptionType Node
// (Constraint on (name, project_graph_id) already acts like an index for these two)

// Optional: Full-text indexes if you plan to search text content (Neo4j Enterprise or specific versions)
// Ví dụ cho Function/Method signatures hoặc Variable names nếu cần tìm kiếm phức tạp
// CREATE FULLTEXT INDEX function_signature_fulltext_idx IF NOT EXISTS FOR (fn:Function) ON EACH [fn.signature, fn.name];

// --- Indexes on Relationship Properties (Less common, but can be useful for specific queries) ---
// Ví dụ: nếu bạn thường xuyên query relationship CALLS dựa trên thuộc tính 'type' hoặc 'call_site_line'
// CREATE INDEX call_type_idx IF NOT EXISTS FOR ()-[r:CALLS]-() ON (r.type);
// CREATE INDEX call_site_line_idx IF NOT EXISTS FOR ()-[r:CALLS]-() ON (r.call_site_line);

// --- Ghi chú quan trọng ---
// 1. `IF NOT EXISTS`: Đảm bảo các lệnh này có thể chạy lại nhiều lần mà không gây lỗi nếu constraint/index đã tồn tại.
// 2. `composite_id`: Các constraint UNIQUE trên `composite_id` rất quan trọng để `MERGE` hoạt động hiệu quả và tránh tạo node trùng lặp.
// 3. Chọn lọc Indexes: Chỉ tạo index cho các thuộc tính bạn sẽ thường xuyên sử dụng trong mệnh đề `WHERE` của các query Cypher. Quá nhiều index có thể làm chậm việc ghi dữ liệu.
// 4. Label `Method`: Nếu Node `Method` của bạn cũng có label `Function` (ví dụ `(m:Method:Function)`), thì các index trên `Function(property)` cũng sẽ áp dụng cho `Method`.