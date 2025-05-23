# novaguard-backend/app/ckg_builder/query_api.py
import logging
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass
from neo4j import AsyncDriver, Record

from app.core.graph_db import get_async_neo4j_driver

logger = logging.getLogger(__name__)

@dataclass
class GraphNode:
    """Represents a node in the CKG."""
    id: str
    labels: List[str]
    properties: Dict[str, Any]

@dataclass
class GraphRelationship:
    """Represents a relationship in the CKG."""
    start_node: GraphNode
    end_node: GraphNode
    type: str
    properties: Dict[str, Any]

@dataclass
class FunctionCallInfo:
    """Information about a function call relationship."""
    caller_name: str
    caller_file: str
    caller_class: Optional[str]
    callee_name: str
    callee_file: str
    callee_class: Optional[str]
    call_line: int

@dataclass
class DependencyInfo:
    """Information about module/file dependencies."""
    from_file: str
    to_file: str
    import_type: str
    imported_names: List[str]

@dataclass
class InheritanceInfo:
    """Information about class inheritance."""
    child_class: str
    child_file: str
    parent_class: str
    parent_file: str

class CKGQueryAPI:
    """High-level API for querying the Code Knowledge Graph."""
    
    def __init__(self, neo4j_driver: Optional[AsyncDriver] = None):
        self._driver = neo4j_driver
    
    async def _get_driver(self) -> AsyncDriver:
        """Get Neo4j driver instance."""
        if self._driver and hasattr(self._driver, '_closed') and not self._driver._closed:
            return self._driver
        driver = await get_async_neo4j_driver()
        if not driver or (hasattr(driver, '_closed') and driver._closed):
            logger.error("CKGQueryAPI: Neo4j driver is not available or closed.")
            raise ConnectionError("Neo4j driver is not available or closed for CKGQueryAPI.")
        self._driver = driver
        return self._driver

    async def _execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Record]:
        """Execute a Cypher query and return results."""
        driver = await self._get_driver()
        db_name = getattr(driver, '_database', 'neo4j')
        params = params or {}
        
        async with driver.session(database=db_name) as session:
            try:
                result = await session.run(query, params)
                records = [record async for record in result]
                await result.consume()
                return records
            except Exception as e:
                logger.error(f"CKGQueryAPI: Error executing query: {e}. Query: {query[:200]}...")
                raise

    # === PROJECT-LEVEL QUERIES ===
    
    async def get_project_overview(self, project_graph_id: str) -> Dict[str, Any]:
        """Get high-level statistics about a project."""
        query = """
        MATCH (p:Project {graph_id: $project_graph_id})
        OPTIONAL MATCH (p)<-[:BELONGS_TO]-(f:File)
        OPTIONAL MATCH (p)<-[:BELONGS_TO]-(cls:Class)
        OPTIONAL MATCH (p)<-[:BELONGS_TO]-(fn:Function)
        OPTIONAL MATCH (p)<-[:BELONGS_TO]-(v:Variable)
        RETURN p.name as project_name,
               p.language as primary_language,
               count(DISTINCT f) as file_count,
               count(DISTINCT cls) as class_count,
               count(DISTINCT fn) as function_count,
               count(DISTINCT v) as variable_count
        """
        records = await self._execute_query(query, {"project_graph_id": project_graph_id})
        if records:
            record = records[0]
            return {
                "project_name": record["project_name"],
                "primary_language": record["primary_language"],
                "file_count": record["file_count"],
                "class_count": record["class_count"],
                "function_count": record["function_count"],
                "variable_count": record["variable_count"]
            }
        return {}

    async def get_files_by_language(self, project_graph_id: str) -> Dict[str, List[str]]:
        """Get files grouped by programming language."""
        query = """
        MATCH (f:File {project_graph_id: $project_graph_id})
        RETURN f.language as language, collect(f.path) as files
        ORDER BY language
        """
        records = await self._execute_query(query, {"project_graph_id": project_graph_id})
        return {record["language"]: record["files"] for record in records}

    # === FUNCTION-RELATED QUERIES ===
    
    async def get_function_calls(self, project_graph_id: str, function_name: Optional[str] = None) -> List[FunctionCallInfo]:
        """Get function call relationships in the project."""
        if function_name:
            query = """
            MATCH (caller:Function)-[r:CALLS]->(callee:Function)
            WHERE caller.project_graph_id = $project_graph_id
            AND (caller.name = $function_name OR callee.name = $function_name)
            RETURN caller.name as caller_name, caller.file_path as caller_file, caller.class_name as caller_class,
                   callee.name as callee_name, callee.file_path as callee_file, callee.class_name as callee_class,
                   r.call_site_line as call_line
            """
            params = {"project_graph_id": project_graph_id, "function_name": function_name}
        else:
            query = """
            MATCH (caller:Function)-[r:CALLS]->(callee:Function)
            WHERE caller.project_graph_id = $project_graph_id
            RETURN caller.name as caller_name, caller.file_path as caller_file, caller.class_name as caller_class,
                   callee.name as callee_name, callee.file_path as callee_file, callee.class_name as callee_class,
                   r.call_site_line as call_line
            """
            params = {"project_graph_id": project_graph_id}
        
        records = await self._execute_query(query, params)
        return [
            FunctionCallInfo(
                caller_name=record["caller_name"],
                caller_file=record["caller_file"],
                caller_class=record["caller_class"],
                callee_name=record["callee_name"],
                callee_file=record["callee_file"],
                callee_class=record["callee_class"],
                call_line=record["call_line"]
            )
            for record in records
        ]

    async def get_functions_calling(self, project_graph_id: str, target_function: str) -> List[str]:
        """Get list of functions that call the target function."""
        query = """
        MATCH (caller:Function)-[:CALLS]->(target:Function {name: $target_function})
        WHERE caller.project_graph_id = $project_graph_id
        RETURN DISTINCT caller.name as caller_name, caller.file_path as caller_file
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "target_function": target_function
        })
        return [f"{record['caller_name']} ({record['caller_file']})" for record in records]

    async def get_functions_called_by(self, project_graph_id: str, source_function: str) -> List[str]:
        """Get list of functions called by the source function."""
        query = """
        MATCH (source:Function {name: $source_function})-[:CALLS]->(callee:Function)
        WHERE source.project_graph_id = $project_graph_id
        RETURN DISTINCT callee.name as callee_name, callee.file_path as callee_file
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "source_function": source_function
        })
        return [f"{record['callee_name']} ({record['callee_file']})" for record in records]

    async def find_circular_function_calls(self, project_graph_id: str, max_depth: int = 10) -> List[List[str]]:
        """Find circular function call dependencies."""
        query = """
        MATCH path = (f:Function)-[:CALLS*1..{max_depth}]->(f)
        WHERE f.project_graph_id = $project_graph_id
        RETURN [n in nodes(path) | n.name] as cycle
        LIMIT 100
        """.format(max_depth=max_depth)
        
        records = await self._execute_query(query, {"project_graph_id": project_graph_id})
        return [record["cycle"] for record in records]

    # === CLASS-RELATED QUERIES ===
    
    async def get_class_hierarchy(self, project_graph_id: str) -> List[InheritanceInfo]:
        """Get class inheritance relationships."""
        query = """
        MATCH (child:Class)-[:INHERITS_FROM]->(parent:Class)
        WHERE child.project_graph_id = $project_graph_id
        RETURN child.name as child_class, child.file_path as child_file,
               parent.name as parent_class, parent.file_path as parent_file
        """
        records = await self._execute_query(query, {"project_graph_id": project_graph_id})
        return [
            InheritanceInfo(
                child_class=record["child_class"],
                child_file=record["child_file"],
                parent_class=record["parent_class"],
                parent_file=record["parent_file"]
            )
            for record in records
        ]

    async def get_class_methods(self, project_graph_id: str, class_name: str) -> List[Dict[str, Any]]:
        """Get all methods of a specific class."""
        query = """
        MATCH (cls:Class {name: $class_name})<-[:DEFINED_IN]-(method:Function)
        WHERE cls.project_graph_id = $project_graph_id
        RETURN method.name as method_name, method.signature as signature,
               method.start_line as start_line, method.end_line as end_line
        ORDER BY method.start_line
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "class_name": class_name
        })
        return [
            {
                "method_name": record["method_name"],
                "signature": record["signature"],
                "start_line": record["start_line"],
                "end_line": record["end_line"]
            }
            for record in records
        ]

    async def find_large_classes(self, project_graph_id: str, min_methods: int = 20) -> List[Dict[str, Any]]:
        """Find classes with many methods (potential God classes)."""
        query = """
        MATCH (cls:Class)
        WHERE cls.project_graph_id = $project_graph_id
        OPTIONAL MATCH (cls)<-[:DEFINED_IN]-(method:Function)
        WITH cls, count(method) as method_count
        WHERE method_count >= $min_methods
        RETURN cls.name as class_name, cls.file_path as file_path, method_count
        ORDER BY method_count DESC
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "min_methods": min_methods
        })
        return [
            {
                "class_name": record["class_name"],
                "file_path": record["file_path"],
                "method_count": record["method_count"]
            }
            for record in records
        ]

    # === DEPENDENCY QUERIES ===
    
    async def get_file_dependencies(self, project_graph_id: str, file_path: Optional[str] = None) -> List[DependencyInfo]:
        """Get import/dependency relationships between files."""
        # This is a simplified version - you may need to enhance based on how imports are stored
        query = """
        MATCH (f:File)-[:IMPORTS]->(imported:File)
        WHERE f.project_graph_id = $project_graph_id
        """ + ("AND f.path = $file_path" if file_path else "") + """
        RETURN f.path as from_file, imported.path as to_file,
               'import' as import_type, [] as imported_names
        """
        params = {"project_graph_id": project_graph_id}
        if file_path:
            params["file_path"] = file_path
            
        records = await self._execute_query(query, params)
        return [
            DependencyInfo(
                from_file=record["from_file"],
                to_file=record["to_file"],
                import_type=record["import_type"],
                imported_names=record["imported_names"]
            )
            for record in records
        ]

    async def find_circular_dependencies(self, project_graph_id: str, max_depth: int = 10) -> List[List[str]]:
        """Find circular file dependencies."""
        query = """
        MATCH path = (f:File)-[:IMPORTS*1..{max_depth}]->(f)
        WHERE f.project_graph_id = $project_graph_id
        RETURN [n in nodes(path) | n.path] as cycle
        LIMIT 100
        """.format(max_depth=max_depth)
        
        records = await self._execute_query(query, {"project_graph_id": project_graph_id})
        return [record["cycle"] for record in records]

    # === VARIABLE/DATA FLOW QUERIES ===
    
    async def get_variable_usage(self, project_graph_id: str, variable_name: str) -> List[Dict[str, Any]]:
        """Get information about where a variable is used."""
        query = """
        MATCH (v:Variable {name: $variable_name})
        WHERE v.project_graph_id = $project_graph_id
        OPTIONAL MATCH (f:Function)-[:USES_VARIABLE]->(v)
        OPTIONAL MATCH (f2:Function)-[:MODIFIES_VARIABLE]->(v)
        RETURN v.name as variable_name, v.file_path as file_path, v.scope_type as scope_type,
               collect(DISTINCT f.name) as used_by_functions,
               collect(DISTINCT f2.name) as modified_by_functions
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "variable_name": variable_name
        })
        return [
            {
                "variable_name": record["variable_name"],
                "file_path": record["file_path"],
                "scope_type": record["scope_type"],
                "used_by_functions": record["used_by_functions"],
                "modified_by_functions": record["modified_by_functions"]
            }
            for record in records
        ]

    # === ANALYSIS HELPERS ===
    
    async def get_functions_in_file(self, project_graph_id: str, file_path: str) -> List[Dict[str, Any]]:
        """Get all functions defined in a specific file."""
        query = """
        MATCH (f:Function {file_path: $file_path})
        WHERE f.project_graph_id = $project_graph_id
        RETURN f.name as function_name, f.class_name as class_name,
               f.start_line as start_line, f.end_line as end_line, f.signature as signature
        ORDER BY f.start_line
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "file_path": file_path
        })
        return [
            {
                "function_name": record["function_name"],
                "class_name": record["class_name"],
                "start_line": record["start_line"],
                "end_line": record["end_line"],
                "signature": record["signature"]
            }
            for record in records
        ]

    async def get_affected_functions_by_file_change(self, project_graph_id: str, changed_files: List[str]) -> Set[str]:
        """Get functions that might be affected by changes to specific files."""
        query = """
        MATCH (changed_file:File)
        WHERE changed_file.project_graph_id = $project_graph_id
        AND changed_file.path IN $changed_files
        MATCH (changed_file)<-[:DEFINED_IN]-(changed_func:Function)
        
        // Functions that call changed functions
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(changed_func)
        
        // Functions that use variables from changed files
        OPTIONAL MATCH (changed_file)<-[:DEFINED_IN_FILE]-(changed_var:Variable)
        OPTIONAL MATCH (user_func:Function)-[:USES_VARIABLE|MODIFIES_VARIABLE]->(changed_var)
        
        RETURN collect(DISTINCT caller.composite_id) + collect(DISTINCT user_func.composite_id) + collect(DISTINCT changed_func.composite_id) as affected_function_ids
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "changed_files": changed_files
        })
        
        affected_ids = set()
        for record in records:
            affected_ids.update(record["affected_function_ids"])
        
        return affected_ids

    async def get_function_complexity_metrics(self, project_graph_id: str) -> List[Dict[str, Any]]:
        """Get complexity metrics for functions (based on call relationships)."""
        query = """
        MATCH (f:Function)
        WHERE f.project_graph_id = $project_graph_id
        OPTIONAL MATCH (f)-[:CALLS]->(called:Function)
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(f)
        WITH f, count(DISTINCT called) as calls_out, count(DISTINCT caller) as calls_in
        RETURN f.name as function_name, f.file_path as file_path, f.class_name as class_name,
               calls_out, calls_in, (calls_out + calls_in) as total_coupling
        ORDER BY total_coupling DESC
        """
        records = await self._execute_query(query, {"project_graph_id": project_graph_id})
        return [
            {
                "function_name": record["function_name"],
                "file_path": record["file_path"],
                "class_name": record["class_name"],
                "calls_out": record["calls_out"],
                "calls_in": record["calls_in"],
                "total_coupling": record["total_coupling"]
            }
            for record in records
        ]

    # === SEARCH AND DISCOVERY ===
    
    async def search_entities(self, project_graph_id: str, search_term: str, entity_types: List[str] = None) -> List[Dict[str, Any]]:
        """Search for entities by name."""
        entity_types = entity_types or ["Function", "Class", "Variable"]
        
        query = """
        MATCH (n)
        WHERE n.project_graph_id = $project_graph_id
        AND any(label in labels(n) WHERE label IN $entity_types)
        AND toLower(n.name) CONTAINS toLower($search_term)
        RETURN n.name as name, labels(n) as labels, n.file_path as file_path,
               CASE 
                 WHEN 'Function' IN labels(n) THEN n.signature
                 WHEN 'Class' IN labels(n) THEN null
                 WHEN 'Variable' IN labels(n) THEN n.scope_type
                 ELSE null
               END as additional_info
        LIMIT 100
        """
        records = await self._execute_query(query, {
            "project_graph_id": project_graph_id,
            "search_term": search_term,
            "entity_types": entity_types
        })
        return [
            {
                "name": record["name"],
                "type": record["labels"],
                "file_path": record["file_path"],
                "additional_info": record["additional_info"]
            }
            for record in records
        ] 