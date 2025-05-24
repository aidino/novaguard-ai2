// === Android Schema Extension for NovaGuard CKG ===
// This file extends the base CKG schema with Android-specific node types and relationships

// === ANDROID NODE TYPE CONSTRAINTS ===

// AndroidActivity Node
CREATE CONSTRAINT android_activity_composite_id_unique IF NOT EXISTS 
FOR (activity:AndroidActivity) REQUIRE activity.composite_id IS UNIQUE;

// AndroidService Node
CREATE CONSTRAINT android_service_composite_id_unique IF NOT EXISTS 
FOR (service:AndroidService) REQUIRE service.composite_id IS UNIQUE;

// AndroidFragment Node
CREATE CONSTRAINT android_fragment_composite_id_unique IF NOT EXISTS 
FOR (fragment:AndroidFragment) REQUIRE fragment.composite_id IS UNIQUE;

// AndroidReceiver Node
CREATE CONSTRAINT android_receiver_composite_id_unique IF NOT EXISTS 
FOR (receiver:AndroidReceiver) REQUIRE receiver.composite_id IS UNIQUE;

// AndroidProvider Node
CREATE CONSTRAINT android_provider_composite_id_unique IF NOT EXISTS 
FOR (provider:AndroidProvider) REQUIRE provider.composite_id IS UNIQUE;

// AndroidPermission Node
CREATE CONSTRAINT android_permission_name_unique IF NOT EXISTS 
FOR (permission:AndroidPermission) REQUIRE permission.composite_id IS UNIQUE;

// GradleDependency Node
CREATE CONSTRAINT gradle_dependency_composite_id_unique IF NOT EXISTS 
FOR (dep:GradleDependency) REQUIRE dep.composite_id IS UNIQUE;

// AndroidResource Node
CREATE CONSTRAINT android_resource_composite_id_unique IF NOT EXISTS 
FOR (resource:AndroidResource) REQUIRE resource.composite_id IS UNIQUE;

// KotlinCoroutine Node
CREATE CONSTRAINT kotlin_coroutine_composite_id_unique IF NOT EXISTS 
FOR (coroutine:KotlinCoroutine) REQUIRE coroutine.composite_id IS UNIQUE;

// JavaAnnotation Node
CREATE CONSTRAINT java_annotation_composite_id_unique IF NOT EXISTS 
FOR (annotation:JavaAnnotation) REQUIRE annotation.composite_id IS UNIQUE;

// AndroidManifest Node
CREATE CONSTRAINT android_manifest_composite_id_unique IF NOT EXISTS 
FOR (manifest:AndroidManifest) REQUIRE manifest.composite_id IS UNIQUE;

// GradleBuildFile Node
CREATE CONSTRAINT gradle_build_file_composite_id_unique IF NOT EXISTS 
FOR (build:GradleBuildFile) REQUIRE build.composite_id IS UNIQUE;

// === ANDROID NODE INDEXES ===

// AndroidActivity
CREATE INDEX android_activity_name_idx IF NOT EXISTS FOR (activity:AndroidActivity) ON (activity.name);
CREATE INDEX android_activity_project_idx IF NOT EXISTS FOR (activity:AndroidActivity) ON (activity.project_graph_id);
CREATE INDEX android_activity_exported_idx IF NOT EXISTS FOR (activity:AndroidActivity) ON (activity.exported);

// AndroidService
CREATE INDEX android_service_name_idx IF NOT EXISTS FOR (service:AndroidService) ON (service.name);
CREATE INDEX android_service_project_idx IF NOT EXISTS FOR (service:AndroidService) ON (service.project_graph_id);

// AndroidFragment
CREATE INDEX android_fragment_name_idx IF NOT EXISTS FOR (fragment:AndroidFragment) ON (fragment.name);
CREATE INDEX android_fragment_project_idx IF NOT EXISTS FOR (fragment:AndroidFragment) ON (fragment.project_graph_id);

// AndroidReceiver
CREATE INDEX android_receiver_name_idx IF NOT EXISTS FOR (receiver:AndroidReceiver) ON (receiver.name);
CREATE INDEX android_receiver_project_idx IF NOT EXISTS FOR (receiver:AndroidReceiver) ON (receiver.project_graph_id);

// AndroidProvider
CREATE INDEX android_provider_name_idx IF NOT EXISTS FOR (provider:AndroidProvider) ON (provider.name);
CREATE INDEX android_provider_project_idx IF NOT EXISTS FOR (provider:AndroidProvider) ON (provider.project_graph_id);

// AndroidPermission
CREATE INDEX android_permission_name_idx IF NOT EXISTS FOR (permission:AndroidPermission) ON (permission.name);
CREATE INDEX android_permission_project_idx IF NOT EXISTS FOR (permission:AndroidPermission) ON (permission.project_graph_id);
CREATE INDEX android_permission_type_idx IF NOT EXISTS FOR (permission:AndroidPermission) ON (permission.permission_type);

// GradleDependency
CREATE INDEX gradle_dependency_group_idx IF NOT EXISTS FOR (dep:GradleDependency) ON (dep.group);
CREATE INDEX gradle_dependency_name_idx IF NOT EXISTS FOR (dep:GradleDependency) ON (dep.name);
CREATE INDEX gradle_dependency_config_idx IF NOT EXISTS FOR (dep:GradleDependency) ON (dep.configuration);
CREATE INDEX gradle_dependency_project_idx IF NOT EXISTS FOR (dep:GradleDependency) ON (dep.project_graph_id);

// AndroidResource
CREATE INDEX android_resource_type_idx IF NOT EXISTS FOR (resource:AndroidResource) ON (resource.resource_type);
CREATE INDEX android_resource_name_idx IF NOT EXISTS FOR (resource:AndroidResource) ON (resource.name);
CREATE INDEX android_resource_project_idx IF NOT EXISTS FOR (resource:AndroidResource) ON (resource.project_graph_id);

// KotlinCoroutine
CREATE INDEX kotlin_coroutine_type_idx IF NOT EXISTS FOR (coroutine:KotlinCoroutine) ON (coroutine.coroutine_type);
CREATE INDEX kotlin_coroutine_project_idx IF NOT EXISTS FOR (coroutine:KotlinCoroutine) ON (coroutine.project_graph_id);

// JavaAnnotation
CREATE INDEX java_annotation_name_idx IF NOT EXISTS FOR (annotation:JavaAnnotation) ON (annotation.name);
CREATE INDEX java_annotation_project_idx IF NOT EXISTS FOR (annotation:JavaAnnotation) ON (annotation.project_graph_id);

// AndroidManifest
CREATE INDEX android_manifest_package_idx IF NOT EXISTS FOR (manifest:AndroidManifest) ON (manifest.package_name);
CREATE INDEX android_manifest_project_idx IF NOT EXISTS FOR (manifest:AndroidManifest) ON (manifest.project_graph_id);

// GradleBuildFile
CREATE INDEX gradle_build_file_type_idx IF NOT EXISTS FOR (build:GradleBuildFile) ON (build.build_file_type);
CREATE INDEX gradle_build_file_project_idx IF NOT EXISTS FOR (build:GradleBuildFile) ON (build.project_graph_id);

// === ANDROID SCHEMA VERSION TRACKING ===
MERGE (android_schema_version:AndroidSchemaVersion {version: "1.0.0"})
SET android_schema_version.created_at = timestamp(),
    android_schema_version.description = "Android CKG schema with activities, services, permissions, dependencies, and Kotlin/Java features"; 