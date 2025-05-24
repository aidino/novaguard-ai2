// === Enhanced Neo4j Schema for NovaGuard CKG ===
// This file extends the base schema with additional node types and relationships
// for more comprehensive code knowledge representation.

// === NEW NODE TYPE CONSTRAINTS ===

// Interface Node (for interfaces, protocols, traits)
CREATE CONSTRAINT interface_composite_id_unique IF NOT EXISTS FOR (i:Interface) REQUIRE i.composite_id IS UNIQUE;

// Enum Node
CREATE CONSTRAINT enum_composite_id_unique IF NOT EXISTS FOR (e:Enum) REQUIRE e.composite_id IS UNIQUE;

// Constant Node
CREATE CONSTRAINT constant_composite_id_unique IF NOT EXISTS FOR (c:Constant) REQUIRE c.composite_id IS UNIQUE;

// APIEndpoint Node
CREATE CONSTRAINT api_endpoint_composite_id_unique IF NOT EXISTS FOR (api:APIEndpoint) REQUIRE api.composite_id IS UNIQUE;

// DatabaseTable Node
CREATE CONSTRAINT db_table_composite_id_unique IF NOT EXISTS FOR (table:DatabaseTable) REQUIRE table.composite_id IS UNIQUE;

// ConfigurationFile Node
CREATE CONSTRAINT config_file_composite_id_unique IF NOT EXISTS FOR (cfg:ConfigurationFile) REQUIRE cfg.composite_id IS UNIQUE;

// Import Node (for tracking import relationships with metadata)
CREATE CONSTRAINT import_composite_id_unique IF NOT EXISTS FOR (imp:Import) REQUIRE imp.composite_id IS UNIQUE;

// CodeMetrics Node (for storing computed metrics)
CREATE CONSTRAINT code_metrics_composite_id_unique IF NOT EXISTS FOR (metrics:CodeMetrics) REQUIRE metrics.composite_id IS UNIQUE;

// === NEW INDEXES FOR ENHANCED NODES ===

// Interface Node
CREATE INDEX interface_name_idx IF NOT EXISTS FOR (i:Interface) ON (i.name);
CREATE INDEX interface_file_path_idx IF NOT EXISTS FOR (i:Interface) ON (i.file_path);
CREATE INDEX interface_project_graph_id_idx IF NOT EXISTS FOR (i:Interface) ON (i.project_graph_id);

// Enum Node
CREATE INDEX enum_name_idx IF NOT EXISTS FOR (e:Enum) ON (e.name);
CREATE INDEX enum_file_path_idx IF NOT EXISTS FOR (e:Enum) ON (e.file_path);
CREATE INDEX enum_project_graph_id_idx IF NOT EXISTS FOR (e:Enum) ON (e.project_graph_id);

// Constant Node
CREATE INDEX constant_name_idx IF NOT EXISTS FOR (c:Constant) ON (c.name);
CREATE INDEX constant_file_path_idx IF NOT EXISTS FOR (c:Constant) ON (c.file_path);
CREATE INDEX constant_project_graph_id_idx IF NOT EXISTS FOR (c:Constant) ON (c.project_graph_id);

// APIEndpoint Node
CREATE INDEX api_endpoint_path_idx IF NOT EXISTS FOR (api:APIEndpoint) ON (api.path);
CREATE INDEX api_endpoint_method_idx IF NOT EXISTS FOR (api:APIEndpoint) ON (api.http_method);
CREATE INDEX api_endpoint_project_graph_id_idx IF NOT EXISTS FOR (api:APIEndpoint) ON (api.project_graph_id);

// DatabaseTable Node
CREATE INDEX db_table_name_idx IF NOT EXISTS FOR (table:DatabaseTable) ON (table.name);
CREATE INDEX db_table_schema_idx IF NOT EXISTS FOR (table:DatabaseTable) ON (table.schema_name);
CREATE INDEX db_table_project_graph_id_idx IF NOT EXISTS FOR (table:DatabaseTable) ON (table.project_graph_id);

// ConfigurationFile Node
CREATE INDEX config_file_path_idx IF NOT EXISTS FOR (cfg:ConfigurationFile) ON (cfg.path);
CREATE INDEX config_file_type_idx IF NOT EXISTS FOR (cfg:ConfigurationFile) ON (cfg.config_type);
CREATE INDEX config_file_project_graph_id_idx IF NOT EXISTS FOR (cfg:ConfigurationFile) ON (cfg.project_graph_id);

// Import Node
CREATE INDEX import_module_path_idx IF NOT EXISTS FOR (imp:Import) ON (imp.module_path);
CREATE INDEX import_file_path_idx IF NOT EXISTS FOR (imp:Import) ON (imp.file_path);
CREATE INDEX import_project_graph_id_idx IF NOT EXISTS FOR (imp:Import) ON (imp.project_graph_id);

// CodeMetrics Node
CREATE INDEX code_metrics_entity_type_idx IF NOT EXISTS FOR (metrics:CodeMetrics) ON (metrics.entity_type);
CREATE INDEX code_metrics_complexity_idx IF NOT EXISTS FOR (metrics:CodeMetrics) ON (metrics.cyclomatic_complexity);
CREATE INDEX code_metrics_project_graph_id_idx IF NOT EXISTS FOR (metrics:CodeMetrics) ON (metrics.project_graph_id);

// === ENHANCED EXISTING INDEXES ===

// Add content hash index for files (for incremental updates)
CREATE INDEX file_content_hash_idx IF NOT EXISTS FOR (f:File) ON (f.content_hash);

// Add last updated timestamp indexes for change tracking
CREATE INDEX file_updated_at_idx IF NOT EXISTS FOR (f:File) ON (f.updated_at);
CREATE INDEX class_updated_at_idx IF NOT EXISTS FOR (c:Class) ON (c.updated_at);
CREATE INDEX function_updated_at_idx IF NOT EXISTS FOR (fn:Function) ON (fn.updated_at);

// === SCHEMA VERSION TRACKING ===
MERGE (schema_version:SchemaVersion {version: "2.0.0"})
SET schema_version.created_at = timestamp(),
    schema_version.description = "Enhanced CKG schema with interfaces, enums, API endpoints, and metrics"; 