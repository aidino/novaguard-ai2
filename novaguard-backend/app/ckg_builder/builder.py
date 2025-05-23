# novaguard-backend/app/ckg_builder/builder.py
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Union
import json

from neo4j import AsyncDriver

from app.core.graph_db import get_async_neo4j_driver
from app.models import Project
from .parsers import get_code_parser, ParsedFileResult, ExtractedFunction, ExtractedClass, ExtractedImport, ExtractedVariable

logger = logging.getLogger(__name__)

class CKGBuilder:
    def __init__(self, project_model: Project, neo4j_driver: Optional[AsyncDriver] = None, project_graph_id: Optional[str] = None):
        self.project = project_model
        self.project_graph_id = project_graph_id or f"novaguard_project_{self.project.id}"
        self._driver = neo4j_driver

    @staticmethod
    def generate_scan_specific_graph_id(project_id: int, scan_type: str, scan_id: int) -> str:
        """
        Generate a unique project_graph_id for a specific scan.
        
        Args:
            project_id: The SQL project ID
            scan_type: Either 'full_scan' or 'pr_analysis'
            scan_id: The ID of the specific scan request
            
        Returns:
            A unique graph ID string
        """
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"novaguard_project_{project_id}_{scan_type}_{scan_id}_{timestamp}"

    async def _get_driver(self) -> AsyncDriver:
        if self._driver and hasattr(self._driver, '_closed') and not self._driver._closed:
            return self._driver
        driver = await get_async_neo4j_driver()
        if not driver or (hasattr(driver, '_closed') and driver._closed):
            logger.error("CKGBuilder: Neo4j driver is not available or closed.")
            raise ConnectionError("Neo4j driver is not available or closed for CKGBuilder.")
        self._driver = driver
        return self._driver

    async def _execute_write_queries(self, queries_with_params: List[Tuple[str, Dict[str, Any]]]):
        if not queries_with_params:
            return
        driver = await self._get_driver()
        db_name = getattr(driver, '_database', 'neo4j')

        async with driver.session(database=db_name) as session:
            tx = None
            current_query_for_log: Optional[str] = None
            current_params_for_log: Optional[Dict[str, Any]] = None
            try:
                tx = await session.begin_transaction()
                for query, params in queries_with_params:
                    current_query_for_log = query
                    current_params_for_log = params
                    if logger.isEnabledFor(logging.DEBUG):
                        try:
                            params_json = json.dumps(params, indent=2, default=str)
                        except TypeError:
                            params_json = str(params)
                        logger.debug(f"CKG Executing Cypher: {query[:300]}... with params: {params_json}")
                    await tx.run(query, params)
                await tx.commit()
                tx = None
            except Exception as e:
                try:
                    params_json_err = json.dumps(current_params_for_log, indent=2, default=str)
                except TypeError:
                    params_json_err = str(current_params_for_log)
                logger.error(
                    f"CKGBuilder: Error running Cypher batch. "
                    f"Failed Query (approx): '{str(current_query_for_log)[:500]}...'. "
                    f"Params for failed query: {params_json_err}. Error: {e}",
                    exc_info=True
                )
                if tx:
                    try:
                        logger.info("CKGBuilder: Attempting to rollback transaction due to error.")
                        await tx.rollback()
                    except Exception as e_rb:
                        logger.error(f"CKGBuilder: Error during transaction rollback: {e_rb}", exc_info=True)
                raise

    async def _execute_write_queries_with_results(self, queries_with_params: List[Tuple[str, Dict[str, Any]]]):
        if not queries_with_params: return []
        driver = await self._get_driver()
        db_name = getattr(driver, '_database', 'neo4j')
        all_results = []
        async with driver.session(database=db_name) as session:
            tx = None
            current_query_for_log: Optional[str] = None
            current_params_for_log: Optional[Dict[str, Any]] = None
            try:
                tx = await session.begin_transaction()
                for query, params in queries_with_params:
                    current_query_for_log = query
                    current_params_for_log = params
                    if logger.isEnabledFor(logging.DEBUG):
                        try:
                            params_json = json.dumps(params, indent=2, default=str)
                        except TypeError:
                            params_json = str(params)
                        logger.debug(f"CKG Executing Cypher (with results): {query[:300]}... with params: {params_json}")
                    result_cursor = await tx.run(query, params)
                    records = [record.data() async for record in result_cursor]
                    await result_cursor.consume()
                    all_results.append(records)
                await tx.commit()
                tx = None
            except Exception as e:
                try:
                    params_json_err = json.dumps(current_params_for_log, indent=2, default=str)
                except TypeError:
                    params_json_err = str(current_params_for_log)
                logger.error(
                    f"CKGBuilder: Error running Cypher batch (with results). "
                    f"Failed Query (approx): '{str(current_query_for_log)[:500]}...'. "
                    f"Params for failed query: {params_json_err}. Error: {e}",
                    exc_info=True
                )
                if tx: await tx.rollback()
                raise
        return all_results


    async def _ensure_project_node(self):
        query = """
        MERGE (p:Project {graph_id: $project_graph_id})
        ON CREATE SET p.name = $repo_name,
                      p.novaguard_id = $novaguard_project_id,
                      p.language = $language,
                      p.created_at = timestamp()
        ON MATCH SET p.name = $repo_name,
                     p.language = $language,
                     p.novaguard_id = $novaguard_project_id,
                     p.updated_at = timestamp()
        """
        params = {
            "project_graph_id": self.project_graph_id,
            "repo_name": self.project.repo_name,
            "novaguard_project_id": str(self.project.id),
            "language": self.project.language
        }
        await self._execute_write_queries([(query, params)])
        logger.info(f"CKGBuilder: Ensured Project node '{self.project_graph_id}' exists/updated.")

    async def _clear_existing_data_for_file(self, file_path_in_repo: str):
        file_composite_id = f"{self.project_graph_id}:{file_path_in_repo}"
        logger.info(f"CKGBuilder: Clearing existing CKG data for file '{file_path_in_repo}' in project '{self.project_graph_id}'")
        query = """
        MATCH (file_node:File {composite_id: $file_composite_id})
        OPTIONAL MATCH (entity)-[:DEFINED_IN]->(file_node)
        WHERE any(label IN labels(entity) WHERE label IN ['Class', 'Function', 'Method'])
        OPTIONAL MATCH (var_global:Variable)-[:DEFINED_IN_FILE]->(file_node)
        OPTIONAL MATCH (entity)-[:HAS_PARAMETER|DECLARES_VARIABLE|DECLARES_ATTRIBUTE]->(var_child:Variable)
        OPTIONAL MATCH (dec:Decorator {file_path: $file_path_prop, project_graph_id: $project_graph_id_prop})
        WITH file_node,
             collect(DISTINCT entity) as entities_in_file,
             collect(DISTINCT var_global) as global_vars_in_file,
             collect(DISTINCT var_child) as child_vars_of_entities,
             collect(DISTINCT dec) as decorators_in_file
        WITH file_node, entities_in_file + global_vars_in_file + child_vars_of_entities + decorators_in_file + [file_node] as all_nodes_to_delete_from_file
        UNWIND all_nodes_to_delete_from_file as ntd
        DETACH DELETE ntd
        RETURN count(DISTINCT ntd) as deleted_nodes_count
        """
        params = {
            "file_composite_id": file_composite_id,
            "file_path_prop": file_path_in_repo,
            "project_graph_id_prop": self.project_graph_id
        }
        try:
            results = await self._execute_write_queries_with_results([(query, params)])
            if results and results[0] and results[0][0]:
                deleted_info = results[0][0]
                logger.info(f"CKGBuilder: Cleared {deleted_info.get('deleted_nodes_count', 0)} nodes related to file '{file_path_in_repo}'.")
            else:
                logger.info(f"CKGBuilder: No specific nodes found/deleted for file '{file_path_in_repo}' during clearing.")
        except Exception as e:
            logger.error(f"CKGBuilder: Error clearing data for file '{file_path_in_repo}': {e}", exc_info=True)

    def _prepare_variable_cypher_tuple(
        self,
        var_data: ExtractedVariable,
        file_path_in_repo: str,
        owner_composite_id: Optional[str],
        owner_node_label: Optional[str],
        relationship_type_from_owner: Optional[str]
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        scope_owner_identifier = var_data.scope_name if var_data.scope_name and var_data.scope_name.strip() else "unknown_scope"
        var_name_safe = var_data.name if var_data.name and var_data.name.strip() else "unknown_variable"

        if var_data.scope_type == "global_variable":
            var_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:GLOBAL:{var_name_safe}:{var_data.start_line}"
        elif var_data.scope_type == "class_attribute" and owner_composite_id:
            var_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{scope_owner_identifier}:{var_name_safe}:{var_data.start_line}"
        elif owner_composite_id:
             var_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{scope_owner_identifier}:{var_name_safe}:{var_data.start_line}"
        else:
            logger.error(f"Cannot determine composite_id for variable {var_name_safe} with scope {var_data.scope_type}")
            return None

        var_props = {
            "name": var_name_safe, "file_path": file_path_in_repo,
            "start_line": var_data.start_line, "end_line": var_data.end_line,
            "scope_name": scope_owner_identifier, "scope_type": var_data.scope_type or "unknown",
            "is_parameter": var_data.is_parameter, "project_graph_id": self.project_graph_id,
            "composite_id": var_composite_id
        }
        if var_data.var_type is not None and var_data.var_type.strip():
            var_props["var_type_hint"] = var_data.var_type.strip()

        on_match_set_parts = ["v.end_line = $var_props.end_line", "v.scope_name = $var_props.scope_name", "v.scope_type = $var_props.scope_type"]
        if "var_type_hint" in var_props:
             on_match_set_parts.append("v.var_type_hint = $var_props.var_type_hint")
        on_match_set_parts.append("v.ckg_updated_at = timestamp()")
        on_match_set_clause = ", ".join(on_match_set_parts)

        cypher = ""
        params = {}
        if owner_composite_id and owner_node_label and relationship_type_from_owner:
            cypher = f"""
            MATCH (owner:{owner_node_label} {{composite_id: $owner_composite_id}})
            MERGE (v:Variable {{composite_id: $var_composite_id}})
            ON CREATE SET v = $var_props, v.ckg_created_at = timestamp()
            ON MATCH SET {on_match_set_clause}
            MERGE (owner)-[:{relationship_type_from_owner}]->(v)
            """
            params = {
                "owner_composite_id": owner_composite_id,
                "var_composite_id": var_composite_id,
                "var_props": var_props
            }
        elif var_data.scope_type == "global_variable":
            file_composite_id_for_global = f"{self.project_graph_id}:{file_path_in_repo}"
            cypher = f"""
            MATCH (f:File {{composite_id: $file_composite_id}})
            MERGE (v:Variable {{composite_id: $var_composite_id}})
            ON CREATE SET v = $var_props, v.ckg_created_at = timestamp()
            ON MATCH SET {on_match_set_clause}
            MERGE (v)-[:DEFINED_IN_FILE]->(f)
            """
            params = {
                "file_composite_id": file_composite_id_for_global,
                "var_composite_id": var_composite_id,
                "var_props": var_props
            }

        if cypher:
            return (cypher, params)
        logger.warning(f"CKGBuilder: Could not determine Cypher for variable: {var_data.name} in scope {var_data.scope_name} (type: {var_data.scope_type})")
        return None


    async def process_file_for_ckg(self, file_path_in_repo: str, file_content: str, language: Optional[str]):
        logger.info(f"CKGBuilder: Starting CKG processing for file '{file_path_in_repo}' (lang: {language}), project: '{self.project_graph_id}'.")
        if not language:
            logger.debug(f"CKGBuilder: Language not specified for file {file_path_in_repo}, skipping CKG.")
            return
        parser = get_code_parser(language)
        if not parser:
            logger.warning(f"CKGBuilder: No parser for lang '{language}' (file: {file_path_in_repo}). Skipping CKG.")
            return
        parsed_data: Optional[ParsedFileResult] = parser.parse(file_content, file_path_in_repo)
        if not parsed_data:
            logger.error(f"CKGBuilder: Failed to parse file {file_path_in_repo} for CKG. Parser returned None.")
            return

        # --- ĐỊNH NGHĨA LẠI CÁC CHUỖI CYPHER CON CHO APOC (DÙNG {} THAY VÌ {{}} BÊN TRONG) ---
        sub_query_attempt1_true_cypher = """
            MATCH (caller_cls:Class {name: $ccn_prop, project_graph_id: $pgid_prop})
            OPTIONAL MATCH (callee_direct:Method {name: $cn_prop, class_name: $ccn_prop, project_graph_id: $pgid_prop})
            WHERE (callee_direct)-[:DEFINED_IN_CLASS]->(caller_cls)
            WITH caller_cls, callee_direct
            OPTIONAL MATCH (caller_cls)-[:INHERITS_FROM*0..5]->(superclass:Class)
            OPTIONAL MATCH (callee_super:Method {name: $cn_prop, project_graph_id: $pgid_prop})
            WHERE (callee_super)-[:DEFINED_IN_CLASS]->(superclass) AND callee_direct IS NULL
            RETURN COALESCE(callee_direct, callee_super) AS found
        """
        sub_query_attempt1_false_cypher = "RETURN null AS found"

        sub_query_attempt1_for_doIt = f"""
            CALL apoc.when(
                $ct_prop STARTS WITH "instance" OR $ct_prop STARTS WITH "class_method_call_on_own_class",
                {json.dumps(sub_query_attempt1_true_cypher)},
                {json.dumps(sub_query_attempt1_false_cypher)},
                {{ccn_prop: $ccn_prop, cn_prop: $cn_prop, pgid_prop: $pgid_prop, ct_prop: $ct_prop}}
            ) YIELD value
            RETURN value.found AS found
        """

        sub_query_attempt2_direct_constructor_cypher = """
            OPTIONAL MATCH (fsf:Function {name: $cn_prop, file_path: $cfile_prop, project_graph_id: $pgid_prop, is_method: false})
            WITH fsf
            OPTIONAL MATCH (faf:Function {name: $cn_prop, project_graph_id: $pgid_prop, is_method: false}) WHERE fsf IS NULL
            RETURN COALESCE(fsf, faf) AS found_func
        """
        sub_query_attempt2_class_method_true_cypher = """
            MATCH (target_cls:Class {name: $bo_prop, project_graph_id: $pgid_prop})
            OPTIONAL MATCH (cmethod:Method {name: $cn_prop, class_name: $bo_prop, project_graph_id: $pgid_prop})
            WHERE (cmethod)-[:DEFINED_IN_CLASS]->(target_cls)
            RETURN cmethod AS found_func
        """
        sub_query_attempt2_class_method_false_cypher = "RETURN null AS found_func"

        sub_query_attempt2_else_for_direct_for_doIt = f"""
            CALL apoc.when(
                $ct_prop ENDS WITH "_on_class" AND $bo_prop IS NOT NULL,
                {json.dumps(sub_query_attempt2_class_method_true_cypher)},
                {json.dumps(sub_query_attempt2_class_method_false_cypher)},
                {{bo_prop: $bo_prop, cn_prop: $cn_prop, pgid_prop: $pgid_prop}}
            ) YIELD value AS class_method_result
            RETURN class_method_result.found_func AS found_func
        """
        sub_query_for_m2_for_doIt = f"""
            CALL apoc.when(
                $ct_prop STARTS WITH "direct" OR $ct_prop STARTS WITH "constructor",
                {json.dumps(sub_query_attempt2_direct_constructor_cypher)},
                {json.dumps(sub_query_attempt2_else_for_direct_for_doIt)},
                {{cn_prop: $cn_prop, cfile_prop: $cfile_prop, pgid_prop: $pgid_prop, ct_prop: $ct_prop, bo_prop: $bo_prop}}
            ) YIELD value
            RETURN value.found_func AS found_func
        """
        sub_query_attempt3_method_on_object_cypher = """
            MATCH (m_other:Method {name: $cn_prop, project_graph_id: $pgid_prop})
            RETURN m_other AS found_other LIMIT 1
        """
        sub_query_attempt3_false_cypher = "RETURN null AS found_other"

        apoc_main_query_string_for_final_call = f"""
            WITH $caller_cid AS caller_cid, $cn_prop AS cn_prop, $pgid_prop AS pgid_prop,
                 $cfile_prop AS cfile_prop, $ct_prop AS ct_prop, $bo_prop AS bo_prop, $ccn_prop AS ccn_prop

            CALL apoc.cypher.doIt({json.dumps(sub_query_attempt1_for_doIt)},
                                  {{ccn_prop: $ccn_prop, cn_prop: $cn_prop, pgid_prop: $pgid_prop, ct_prop: $ct_prop}}) YIELD value AS res1_map
            WITH res1_map.found AS found1, caller_cid, cn_prop, pgid_prop, cfile_prop, ct_prop, bo_prop, ccn_prop

            CALL apoc.cypher.doIt(
                CASE
                  WHEN found1 IS NULL AND $cn_prop IS NOT NULL AND ($ct_prop STARTS WITH "direct" OR $ct_prop STARTS WITH "constructor" OR $ct_prop ENDS WITH "_on_class")
                  THEN {json.dumps(sub_query_for_m2_for_doIt)}
                  ELSE "RETURN null as found_func"
                END,
                {{cn_prop: $cn_prop, cfile_prop: $cfile_prop, pgid_prop: $pgid_prop, ct_prop: $ct_prop, bo_prop: $bo_prop, ccn_prop:$ccn_prop, caller_cid:caller_cid}}
            ) YIELD value AS res2_map
            WITH found1, COALESCE(res2_map.found_func, null) AS found2, caller_cid, cn_prop, pgid_prop, cfile_prop, ct_prop, bo_prop, ccn_prop

            CALL apoc.cypher.doIt(
                CASE
                  WHEN found1 IS NULL AND found2 IS NULL AND $ct_prop = "method_call_on_object" AND $cn_prop IS NOT NULL
                  THEN {json.dumps(sub_query_attempt3_method_on_object_cypher)}
                  ELSE {json.dumps(sub_query_attempt3_false_cypher)}
                END,
                {{cn_prop: $cn_prop, pgid_prop: $pgid_prop}}
            ) YIELD value AS res3_map

            RETURN COALESCE(found1, found2, res3_map.found_other) AS final_callee
        """
        # --- KẾT THÚC ĐỊNH NGHĨA APOC QUERY STRING ---


        await self._clear_existing_data_for_file(file_path_in_repo)
        cypher_batch: List[Tuple[str, Dict[str, Any]]] = []
        file_composite_id = f"{self.project_graph_id}:{file_path_in_repo}"

        # (Phần tạo Node File, Project, Import, Global Variable, Class, Method, Function, Decorator, ExceptionType giữ nguyên)
        # ... (Giữ nguyên các đoạn code tạo thực thể đã có)
        file_node_props = {
            "path": file_path_in_repo, "project_graph_id": self.project_graph_id,
            "language": language or "unknown", "name": Path(file_path_in_repo).name,
            "composite_id": file_composite_id, "line_count": len(file_content.splitlines()),
            "char_count": len(file_content)
        }
        cypher_batch.append((
            """
            MERGE (p:Project {graph_id: $project_graph_id})
            MERGE (f:File {composite_id: $file_composite_id})
            ON CREATE SET f = $props, f.ckg_created_at = timestamp()
            ON MATCH SET f.language = $props.language, f.name = $props.name,
                         f.line_count = $props.line_count, f.char_count = $props.char_count,
                         f.ckg_updated_at = timestamp()
            MERGE (f)-[:PART_OF_PROJECT]->(p)
            """,
            {"project_graph_id": self.project_graph_id, "file_composite_id": file_composite_id, "props": file_node_props}
        ))

        for imp_data in parsed_data.imports:
            if imp_data.module_path and imp_data.module_path.strip():
                actual_module_path = imp_data.module_path.strip()
                if not actual_module_path:
                    logger.warning(f"CKGBuilder: Skipping import with empty module_path in file {file_path_in_repo}, line {imp_data.start_line}")
                    continue
                module_composite_id = f"{self.project_graph_id}:MODULE:{actual_module_path}"
                module_name_from_path = actual_module_path.split('.')[-1] or actual_module_path
                valid_imported_names = []
                if imp_data.imported_names:
                    for name, alias in imp_data.imported_names:
                        if name and name.strip():
                            valid_imported_names.append({"original": name.strip(), "alias": alias.strip() if alias else None})
                        elif alias and alias.strip():
                             valid_imported_names.append({"original": ".", "alias": alias.strip()})
                cypher_batch.append((
                    """
                    MERGE (m:Module {composite_id: $module_composite_id})
                    ON CREATE SET m.path = $module_path, m.name = $module_name,
                                  m.project_graph_id = $project_graph_id, m.is_stub = true,
                                  m.relative_level = $relative_level, m.ckg_created_at = timestamp()
                    ON MATCH SET m.ckg_updated_at = timestamp(), m.relative_level = $relative_level
                    WITH m
                    MATCH (f:File {composite_id: $file_composite_id})
                    MERGE (f)-[r:IMPORTS_MODULE {type: $import_type, line: $import_line}]->(m)
                    ON CREATE SET r.imported_names_json = $imported_names_json, r.timestamp = timestamp()
                    ON MATCH SET  r.imported_names_json = $imported_names_json
                    """, {
                        "module_composite_id": module_composite_id, "module_path": actual_module_path,
                        "module_name": module_name_from_path, "project_graph_id": self.project_graph_id,
                        "relative_level": imp_data.relative_level, "file_composite_id": file_composite_id,
                        "import_type": imp_data.import_type or "unknown",
                        "imported_names_json": json.dumps(valid_imported_names),
                        "import_line": imp_data.start_line
                    }
                ))
            else:
                logger.warning(f"CKGBuilder: Skipping import with empty or None module_path in file {file_path_in_repo}, line {imp_data.start_line if imp_data else 'N/A'}")

        for g_var_data in parsed_data.global_variables:
            if not g_var_data.name or not g_var_data.name.strip():
                logger.warning(f"CKGBuilder: Skipping global variable with empty name in {file_path_in_repo} near line {g_var_data.start_line}")
                continue
            cypher_tuple = self._prepare_variable_cypher_tuple(
                g_var_data, file_path_in_repo,
                owner_composite_id=None, owner_node_label=None, relationship_type_from_owner=None
            )
            if cypher_tuple: cypher_batch.append(cypher_tuple)

        for cls_data in parsed_data.classes:
            class_name_safe = cls_data.name.strip() if cls_data.name else None
            if not class_name_safe:
                logger.warning(f"CKGBuilder: Skipping class with empty name in {file_path_in_repo} at line {cls_data.start_line}")
                continue
            class_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{class_name_safe}:{cls_data.start_line}"
            class_props = {
                "name": class_name_safe, "file_path": file_path_in_repo,
                "start_line": cls_data.start_line, "end_line": cls_data.end_line,
                "project_graph_id": self.project_graph_id, "composite_id": class_composite_id
            }
            cypher_batch.append((
                """
                MATCH (f:File {composite_id: $file_composite_id})
                MERGE (c:Class {composite_id: $class_composite_id})
                ON CREATE SET c = $props, c.ckg_created_at = timestamp()
                ON MATCH SET c.end_line = $props.end_line, c.ckg_updated_at = timestamp()
                MERGE (c)-[:DEFINED_IN]->(f)
                """,
                {"file_composite_id": file_composite_id, "class_composite_id": class_composite_id, "props": class_props}
            ))

            for super_name_raw in cls_data.superclasses:
                super_name = super_name_raw.strip() if isinstance(super_name_raw, str) else None
                if not super_name: continue
                super_class_placeholder_id = f"{self.project_graph_id}:CLASS_PLACEHOLDER:{super_name}"
                cypher_batch.append((
                    """
                    MATCH (this_class:Class {composite_id: $class_composite_id})
                    MERGE (super_class:Class {name: $super_name, project_graph_id: $project_graph_id})
                    ON CREATE SET super_class.placeholder = true, super_class.composite_id = $super_class_comp_id,
                                  super_class.file_path = "UNKNOWN", super_class.start_line = -1,
                                  super_class.ckg_created_at = timestamp()
                    ON MATCH SET super_class.placeholder = COALESCE(super_class.placeholder, false)
                    MERGE (this_class)-[:INHERITS_FROM]->(super_class)
                    """, {
                        "class_composite_id": class_composite_id, "super_name": super_name,
                        "project_graph_id": self.project_graph_id, "super_class_comp_id": super_class_placeholder_id
                    }
                ))

            for attr_var in cls_data.attributes:
                if not attr_var.name or not attr_var.name.strip(): continue
                cypher_tuple = self._prepare_variable_cypher_tuple(attr_var, file_path_in_repo, class_composite_id, "Class", "DECLARES_ATTRIBUTE")
                if cypher_tuple: cypher_batch.append(cypher_tuple)

            for dec_name_raw in cls_data.decorators:
                dec_name = dec_name_raw.strip() if isinstance(dec_name_raw, str) else None
                if not dec_name: continue
                decorator_class_comp_id = f"{self.project_graph_id}:{file_path_in_repo}:DECORATOR:{dec_name}:{cls_data.start_line}"
                cypher_batch.append((
                    """
                    MATCH (owner:Class {composite_id: $owner_id})
                    MERGE (d:Decorator {composite_id: $dec_comp_id})
                    ON CREATE SET d.name = $dec_name, d.project_graph_id = $project_graph_id,
                                  d.file_path = $file_path, d.applied_to_line = $applied_line, 
                                  d.applied_to_type = 'Class', d.ckg_created_at = timestamp()
                    ON MATCH SET d.ckg_updated_at = timestamp()
                    MERGE (owner)-[:HAS_DECORATOR]->(d)
                    """, {
                        "owner_id": class_composite_id, "dec_name": dec_name, 
                        "project_graph_id": self.project_graph_id,
                        "dec_comp_id": decorator_class_comp_id, 
                        "file_path": file_path_in_repo,
                        "applied_line": cls_data.start_line
                    }
                ))

            for method_data in cls_data.methods:
                method_name_safe = method_data.name.strip() if method_data.name else None
                if not method_name_safe:
                    logger.warning(f"CKGBuilder: Skipping method with empty name in class {class_name_safe}, file {file_path_in_repo}")
                    continue
                method_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{class_name_safe}.{method_name_safe}:{method_data.start_line}"
                method_props = {
                    "name": method_name_safe, "file_path": file_path_in_repo,
                    "start_line": method_data.start_line, "end_line": method_data.end_line,
                    "signature": (method_data.signature.strip() if method_data.signature else "") or "",
                    "parameters_str": (method_data.parameters_str.strip() if method_data.parameters_str else "") or "",
                    "class_name": class_name_safe, "project_graph_id": self.project_graph_id,
                    "composite_id": method_composite_id, "is_method": True
                }
                cypher_batch.append((
                    """
                    MATCH (f:File {composite_id: $file_composite_id})
                    MATCH (cls:Class {composite_id: $class_composite_id})
                    MERGE (m:Method:Function {composite_id: $method_composite_id})
                    ON CREATE SET m = $props, m.ckg_created_at = timestamp()
                    ON MATCH SET m.end_line = $props.end_line, m.signature = $props.signature,
                                 m.parameters_str = $props.parameters_str, m.class_name = $props.class_name,
                                 m.ckg_updated_at = timestamp()
                    MERGE (m)-[:DEFINED_IN]->(f)
                    MERGE (m)-[:DEFINED_IN_CLASS]->(cls)
                    """, {
                        "file_composite_id": file_composite_id, "class_composite_id": class_composite_id,
                        "method_composite_id": method_composite_id, "props": method_props
                    }
                ))
                for param_var in method_data.parameters:
                    if not param_var.name or not param_var.name.strip(): continue
                    cypher_tuple = self._prepare_variable_cypher_tuple(param_var, file_path_in_repo, method_composite_id, "Method", "HAS_PARAMETER")
                    if cypher_tuple: cypher_batch.append(cypher_tuple)
                for local_var in method_data.local_variables:
                    if not local_var.name or not local_var.name.strip(): continue
                    cypher_tuple = self._prepare_variable_cypher_tuple(local_var, file_path_in_repo, method_composite_id, "Method", "DECLARES_VARIABLE")
                    if cypher_tuple: cypher_batch.append(cypher_tuple)
                for dec_name_raw in method_data.decorators:
                    dec_name = dec_name_raw.strip() if isinstance(dec_name_raw, str) else None
                    if not dec_name: continue
                    decorator_method_comp_id = f"{self.project_graph_id}:{file_path_in_repo}:DECORATOR:{dec_name}:{method_data.start_line}"
                    cypher_batch.append((
                        """
                        MATCH (owner:Method {composite_id: $owner_id})
                        MERGE (d:Decorator {composite_id: $dec_comp_id})
                        ON CREATE SET d.name = $dec_name, d.project_graph_id = $project_graph_id,
                                      d.file_path = $file_path, d.applied_to_line = $applied_line,
                                      d.applied_to_type = 'Method', d.ckg_created_at = timestamp()
                        ON MATCH SET d.ckg_updated_at = timestamp()
                        MERGE (owner)-[:HAS_DECORATOR]->(d)
                        """, {
                            "owner_id": method_composite_id, "dec_name": dec_name,
                            "project_graph_id": self.project_graph_id,
                            "dec_comp_id": decorator_method_comp_id, 
                            "file_path": file_path_in_repo,
                            "applied_line": method_data.start_line
                        }
                    ))
                for ex_name_raw in method_data.raised_exceptions:
                    ex_name = ex_name_raw.strip() if isinstance(ex_name_raw, str) else None
                    if not ex_name: continue
                    ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                    cypher_batch.append((
                        """
                        MATCH (owner:Method {composite_id: $owner_id})
                        MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                        ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                        ON MATCH SET ex.ckg_updated_at = timestamp()
                        MERGE (owner)-[:RAISES_EXCEPTION]->(ex)
                        """, {"owner_id": method_composite_id, "ex_name": ex_name,
                              "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id}
                    ))
                for ex_name_raw in method_data.handled_exceptions:
                    ex_name = ex_name_raw.strip() if isinstance(ex_name_raw, str) else None
                    if not ex_name: continue
                    ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                    cypher_batch.append((
                        """
                        MATCH (owner:Method {composite_id: $owner_id})
                        MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                        ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                        ON MATCH SET ex.ckg_updated_at = timestamp()
                        MERGE (owner)-[:HANDLES_EXCEPTION]->(ex)
                        """, {"owner_id": method_composite_id, "ex_name": ex_name,
                              "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id}
                    ))

        for func_data in parsed_data.functions: # Global functions
            func_name_safe = func_data.name.strip() if func_data.name else None
            if not func_name_safe:
                logger.warning(f"CKGBuilder: Skipping global function with empty name in file {file_path_in_repo} at line {func_data.start_line}")
                continue
            func_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{func_name_safe}:{func_data.start_line}"
            func_props = {
                "name": func_name_safe, "file_path": file_path_in_repo,
                "start_line": func_data.start_line, "end_line": func_data.end_line,
                "signature": (func_data.signature.strip() if func_data.signature else "") or "",
                "parameters_str": (func_data.parameters_str.strip() if func_data.parameters_str else "") or "",
                "project_graph_id": self.project_graph_id, "composite_id": func_composite_id,
                "is_method": False
            }
            cypher_batch.append((
                """
                MATCH (f:File {composite_id: $file_composite_id})
                MERGE (fn:Function {composite_id: $func_composite_id})
                ON CREATE SET fn = $props, fn.ckg_created_at = timestamp()
                ON MATCH SET fn.end_line = $props.end_line, fn.signature = $props.signature,
                             fn.parameters_str = $props.parameters_str, fn.ckg_updated_at = timestamp()
                MERGE (fn)-[:DEFINED_IN]->(f)
                """,
                {"file_composite_id": file_composite_id, "func_composite_id": func_composite_id, "props": func_props}
            ))
            for param_var in func_data.parameters:
                 if not param_var.name or not param_var.name.strip(): continue
                 cypher_tuple = self._prepare_variable_cypher_tuple(param_var, file_path_in_repo, func_composite_id, "Function", "HAS_PARAMETER")
                 if cypher_tuple: cypher_batch.append(cypher_tuple)
            for local_var in func_data.local_variables:
                if not local_var.name or not local_var.name.strip(): continue
                cypher_tuple = self._prepare_variable_cypher_tuple(local_var, file_path_in_repo, func_composite_id, "Function", "DECLARES_VARIABLE")
                if cypher_tuple: cypher_batch.append(cypher_tuple)
            for dec_name_raw in func_data.decorators:
                dec_name = dec_name_raw.strip() if isinstance(dec_name_raw, str) else None
                if not dec_name: continue
                decorator_func_comp_id = f"{self.project_graph_id}:{file_path_in_repo}:DECORATOR:{dec_name}:{func_data.start_line}"
                cypher_batch.append((
                    """
                    MATCH (owner:Function {composite_id: $owner_id})
                    MERGE (d:Decorator {composite_id: $dec_comp_id})
                    ON CREATE SET d.name = $dec_name, d.project_graph_id = $project_graph_id,
                                  d.file_path = $file_path, d.applied_to_line = $applied_line,
                                  d.applied_to_type = 'Function', d.ckg_created_at = timestamp()
                    ON MATCH SET d.ckg_updated_at = timestamp()
                    MERGE (owner)-[:HAS_DECORATOR]->(d)
                    """, {
                        "owner_id": func_composite_id, "dec_name": dec_name,
                        "project_graph_id": self.project_graph_id,
                        "dec_comp_id": decorator_func_comp_id, 
                        "file_path": file_path_in_repo,
                        "applied_line": func_data.start_line
                    }
                ))
            for ex_name_raw in func_data.raised_exceptions:
                ex_name = ex_name_raw.strip() if isinstance(ex_name_raw, str) else None
                if not ex_name: continue
                ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                cypher_batch.append((
                    """
                    MATCH (owner:Function {composite_id: $owner_id})
                    MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                    ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                    ON MATCH SET ex.ckg_updated_at = timestamp()
                    MERGE (owner)-[:RAISES_EXCEPTION]->(ex)
                    """, {"owner_id": func_composite_id, "ex_name": ex_name,
                          "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id }
                ))
            for ex_name_raw in func_data.handled_exceptions:
                ex_name = ex_name_raw.strip() if isinstance(ex_name_raw, str) else None
                if not ex_name: continue
                ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                cypher_batch.append((
                    """
                    MATCH (owner:Function {composite_id: $owner_id})
                    MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                    ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                    ON MATCH SET ex.ckg_updated_at = timestamp()
                    MERGE (owner)-[:HANDLES_EXCEPTION]->(ex)
                    """, {"owner_id": func_composite_id, "ex_name": ex_name,
                           "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id}
                ))

        if cypher_batch:
            logger.debug(f"CKGBuilder: Executing main entity batch of {len(cypher_batch)} Cypher queries for file {file_path_in_repo}.")
            try:
                await self._execute_write_queries(cypher_batch)
            except Exception as e_main_batch:
                logger.error(f"CKGBuilder: Error executing main entity batch for {file_path_in_repo}. Error: {e_main_batch}", exc_info=True)
        
        usage_modification_creation_batch: List[Tuple[str, Dict[str, Any]]] = []
        all_functions_and_methods_in_file = parsed_data.functions + [
            method for cls in parsed_data.classes for method in cls.methods
        ]

        for func_or_method_item in all_functions_and_methods_in_file:
            owner_name_for_id_calc = func_or_method_item.name
            if func_or_method_item.class_name:
                owner_name_for_id_calc = f"{func_or_method_item.class_name}.{func_or_method_item.name}"
            
            owner_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{owner_name_for_id_calc}:{func_or_method_item.start_line}"
            owner_node_label = ":Method:Function" if func_or_method_item.class_name else ":Function"

            for var_name_used, line_num_usage in func_or_method_item.uses_variables:
                if '.' in var_name_used and var_name_used.startswith("self.") and func_or_method_item.class_name:
                    attr_name_only = var_name_used.split('.', 1)[1]
                    find_var_query = f"""
                        MATCH (owner_func{owner_node_label} {{composite_id: $owner_func_id}})
                        MATCH (v:Variable {{name: $attr_name, scope_name: $class_name, scope_type: 'class_attribute', project_graph_id: $pgid, file_path: $fpath}})
                        MERGE (owner_func)-[r:USES_VARIABLE {{line: $line, context: 'attribute_access'}}]->(v)
                        RETURN r.line
                    """
                    usage_modification_creation_batch.append((
                        find_var_query, {
                            "owner_func_id": owner_composite_id, "attr_name": attr_name_only,
                            "class_name": func_or_method_item.class_name, "pgid": self.project_graph_id,
                            "fpath": file_path_in_repo, "line": line_num_usage
                        } ))
                else:
                    find_and_link_var_query = f"""
                        MATCH (owner_func{owner_node_label} {{composite_id: $owner_func_id}})
                        OPTIONAL MATCH (v_local_param:Variable {{name: $var_name, scope_name: $func_scope_name, project_graph_id: $pgid, file_path: $fpath}})
                        OPTIONAL MATCH (v_global:Variable {{name: $var_name, scope_type: 'global_variable', project_graph_id: $pgid, file_path: $fpath}})
                        WITH owner_func, COALESCE(v_local_param, v_global) as final_used_var
                        WHERE final_used_var IS NOT NULL
                        MERGE (owner_func)-[r:USES_VARIABLE {{line: $line}}]->(final_used_var)
                        RETURN r.line
                    """
                    usage_modification_creation_batch.append((
                        find_and_link_var_query, {
                            "owner_func_id": owner_composite_id,
                            "var_name": var_name_used,
                            "func_scope_name": owner_name_for_id_calc,
                            "pgid": self.project_graph_id,
                            "fpath": file_path_in_repo,
                            "line": line_num_usage
                        }
                    ))

            for var_name_modified, line_num_modification, mod_context in func_or_method_item.modifies_variables:
                if '.' in var_name_modified and var_name_modified.startswith("self.") and func_or_method_item.class_name:
                    attr_name_mod_only = var_name_modified.split('.', 1)[1]
                    find_mod_var_query = f"""
                        MATCH (owner_func{owner_node_label} {{composite_id: $owner_func_id}})
                        MATCH (v:Variable {{name: $attr_name, scope_name: $class_name, scope_type: 'class_attribute', project_graph_id: $pgid, file_path: $fpath}})
                        MERGE (owner_func)-[r:MODIFIES_VARIABLE {{line: $line, context: $mod_context}}]->(v)
                        RETURN r.line
                    """
                    usage_modification_creation_batch.append((
                        find_mod_var_query, {
                            "owner_func_id": owner_composite_id, "attr_name": attr_name_mod_only,
                            "class_name": func_or_method_item.class_name, "pgid": self.project_graph_id,
                            "fpath": file_path_in_repo, "line": line_num_modification,
                            "mod_context": mod_context
                        } ))
                else: 
                    find_and_link_mod_var_query = f"""
                        MATCH (owner_func{owner_node_label} {{composite_id: $owner_func_id}})
                        OPTIONAL MATCH (v_local_param:Variable {{name: $var_name, scope_name: $func_scope_name, project_graph_id: $pgid, file_path: $fpath}})
                        OPTIONAL MATCH (v_global:Variable {{name: $var_name, scope_type: 'global_variable', project_graph_id: $pgid, file_path: $fpath}})
                        WITH owner_func, COALESCE(v_local_param, v_global) as final_mod_var
                        WHERE final_mod_var IS NOT NULL
                        MERGE (owner_func)-[r:MODIFIES_VARIABLE {{line: $line, context: $mod_context}}]->(final_mod_var)
                        RETURN r.line
                    """
                    usage_modification_creation_batch.append((
                        find_and_link_mod_var_query, {
                            "owner_func_id": owner_composite_id,
                            "var_name": var_name_modified,
                            "func_scope_name": owner_name_for_id_calc,
                            "pgid": self.project_graph_id,
                            "fpath": file_path_in_repo,
                            "line": line_num_modification,
                            "mod_context": mod_context
                        }
                    ))

            for class_name_created, line_num_creation in func_or_method_item.created_objects:
                link_creates_object_query = f"""
                    MATCH (creator_func{owner_node_label} {{composite_id: $creator_func_id}})
                    MATCH (created_class:Class {{name: $class_name_to_find, project_graph_id: $pgid}})
                    MERGE (creator_func)-[r:CREATES_OBJECT {{line: $line}}]->(created_class)
                    ON CREATE SET r.timestamp = timestamp()
                    RETURN r.line
                """
                usage_modification_creation_batch.append((
                    link_creates_object_query, {
                        "creator_func_id": owner_composite_id,
                        "class_name_to_find": class_name_created,
                        "pgid": self.project_graph_id,
                        "line": line_num_creation
                    }
                ))
        
        if usage_modification_creation_batch:
            logger.debug(f"CKGBuilder: Executing USES/MODIFIES/CREATES batch of {len(usage_modification_creation_batch)} queries for file {file_path_in_repo}.")
            try:
                await self._execute_write_queries(usage_modification_creation_batch)
            except Exception as e_usage_mod_create:
                logger.error(f"CKGBuilder: Error executing USES/MODIFIES/CREATES batch for {file_path_in_repo}. Error: {e_usage_mod_create}", exc_info=True)

        call_link_queries_batch: List[Tuple[str, Dict[str, Any]]] = []
        for defined_entity in all_functions_and_methods_in_file:
            defined_entity_name_safe = defined_entity.name.strip() if defined_entity.name else None
            if not defined_entity_name_safe: continue
            if not defined_entity.calls: continue

            caller_class_name_safe = defined_entity.class_name.strip() if defined_entity.class_name else None
            caller_name_for_id = defined_entity_name_safe
            if caller_class_name_safe:
                caller_name_for_id = f"{caller_class_name_safe}.{defined_entity_name_safe}"

            caller_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{caller_name_for_id}:{defined_entity.start_line}"
            caller_node_label_for_match = ":Method:Function" if caller_class_name_safe else ":Function"

            for called_name, base_object_name, call_type, call_site_line in defined_entity.calls:
                final_callee_name = called_name.strip() if isinstance(called_name, str) and called_name.strip() else None
                final_base_object_name = base_object_name.strip() if isinstance(base_object_name, str) and base_object_name.strip() else None
                final_caller_class_name = caller_class_name_safe
                final_call_type = call_type.strip() if isinstance(call_type, str) and call_type.strip() else "unknown_call_type"

                if not final_callee_name:
                    logger.warning(f"CKGBuilder: Skipping CALLS link due to empty callee_name. Caller: '{defined_entity_name_safe}' in {file_path_in_repo} at L{call_site_line}.")
                    continue

                apoc_subquery_params = {
                    "caller_cid": caller_composite_id, "cn_prop": final_callee_name,
                    "pgid_prop": self.project_graph_id, "cfile_prop": file_path_in_repo,
                    "ct_prop": final_call_type, "bo_prop": final_base_object_name,
                    "ccn_prop": final_caller_class_name
                }
                params_for_apoc_call_query = {
                    "caller_composite_id": caller_composite_id, 
                    "call_params": apoc_subquery_params,
                    "call_type_prop": final_call_type, 
                    "base_object_prop": final_base_object_name,
                    "call_site_line_prop": call_site_line
                }
                if logger.isEnabledFor(logging.DEBUG):
                     logger.debug(f"Preparing APOC CALLS query. Params: {json.dumps(params_for_apoc_call_query, indent=2, default=str)}")
                
                resolve_and_link_query_apoc = f"""
                MATCH (caller{caller_node_label_for_match} {{composite_id: $caller_composite_id}})
                CALL apoc.cypher.doIt({json.dumps(apoc_main_query_string_for_final_call)}, $call_params) YIELD value AS callee_map
                WITH caller, callee_map.final_callee AS actual_callee
                WHERE actual_callee IS NOT NULL
                MERGE (caller)-[r:CALLS]->(actual_callee)
                ON CREATE SET r.type = $call_type_prop,
                              r.base_object_name = $base_object_prop,
                              r.call_site_line = $call_site_line_prop,
                              r.call_count = 1,
                              r.first_seen_at = timestamp()
                ON MATCH SET  r.call_count = coalesce(r.call_count, 0) + 1,
                              r.last_seen_at = timestamp()
                """
                call_link_queries_batch.append((resolve_and_link_query_apoc, params_for_apoc_call_query))


        if call_link_queries_batch:
            logger.debug(f"CKGBuilder: Executing batch of {len(call_link_queries_batch)} CALLS link queries for file {file_path_in_repo}.")
            try:
                await self._execute_write_queries(call_link_queries_batch)
            except Exception as e_calls:
                logger.error(f"CKGBuilder: Error executing CALLS link batch for {file_path_in_repo}. Some call links might be missing. Error: {e_calls}", exc_info=True)

        logger.info(f"CKGBuilder: Finished CKG processing for file '{file_path_in_repo}'.")


    async def build_for_project_from_path(self, repo_local_path: str):
        # (Giữ nguyên logic)
        logger.info(f"CKGBuilder: Starting CKG build for project '{self.project_graph_id}' from path: {repo_local_path}")
        await self._ensure_project_node()
        source_path_obj = Path(repo_local_path); files_processed_count = 0; files_to_process: List[Tuple[Path, Optional[str]]] = []
        project_main_language = self.project.language.lower().strip() if self.project.language else None
        logger.info(f"CKGBuilder: Project main language hint: {project_main_language}")
        common_code_extensions = {'.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript', '.java': 'java', '.go': 'go', '.rb': 'ruby', '.php': 'php', '.cs': 'c_sharp', '.c': 'c', '.h': 'c', '.cpp': 'cpp', '.hpp': 'cpp', '.cxx': 'cpp', '.hxx': 'cpp'}
        ignored_parts = {'.git', 'node_modules', '__pycache__', 'venv', 'target', 'build', 'dist', '.idea', '.vscode', '.settings', 'bin', 'obj', 'lib', 'docs', 'examples', '.DS_Store', 'coverage', '.pytest_cache', '.mypy_cache', '.tox', '.nox', 'site-packages', 'dist-packages', 'vendor', 'third_party', 'external_libs'}
        ignored_extensions = {'.log', '.tmp', '.swp', '.map', '.min.js', '.min.css', '.lock', '.cfg', '.ini', '.txt', '.md', '.json', '.xml', '.yaml', '.yml', '.csv', '.tsv', '.bak', '.old', '.orig', '.zip', '.tar.gz', '.rar', '.7z', '.exe', '.dll', '.so', '.o', '.a', '.lib', '.jar', '.class', '.pyc', '.pyd', '.egg-info', '.hypothesis', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.mp3', '.mp4', '.avi', '.mov', '.db', '.sqlite', '.sqlite3', '.DS_Store'}
        min_file_size_for_ckg = 5; max_file_size_for_ckg = 5 * 1024 * 1024
        for file_p in source_path_obj.rglob('*'):
            if not file_p.is_file(): continue
            relative_path_str = str(file_p.relative_to(source_path_obj))
            if any(part.lower() in ignored_parts for part in file_p.relative_to(source_path_obj).parts) or \
               any(file_p.name.lower().endswith(ext) for ext in ignored_parts if not ext.startswith('.')) or \
               (file_p.name.startswith('.') and file_p.name.lower() not in ['.env', '.flaskenv', '.babelrc', '.eslintrc.js']):
                logger.debug(f"CKGBuilder: Skipping ignored file/path: {relative_path_str}"); continue
            if file_p.suffix.lower() in ignored_extensions: logger.debug(f"CKGBuilder: Skipping file with ignored extension: {relative_path_str}"); continue
            try:
                file_size = file_p.stat().st_size
                if file_size < min_file_size_for_ckg: logger.debug(f"CKGBuilder: Skipping too small file: {relative_path_str} ({file_size} bytes)"); continue
                if file_size > max_file_size_for_ckg: logger.warning(f"CKGBuilder: Skipping too large file: {relative_path_str} ({file_size} bytes). Max size: {max_file_size_for_ckg} bytes."); continue
            except OSError as e_stat: logger.warning(f"CKGBuilder: Could not stat file: {relative_path_str}. Error: {e_stat}. Skipping."); continue
            file_lang = common_code_extensions.get(file_p.suffix.lower())
            if file_lang: files_to_process.append((file_p, file_lang))
            else: logger.debug(f"CKGBuilder: Skipping file with unsupported code extension: {relative_path_str}")
        logger.info(f"CKGBuilder: Found {len(files_to_process)} files to process for CKG.")
        for file_p, lang_to_use in files_to_process:
            file_path_in_repo_str = str(file_p.relative_to(source_path_obj))
            try:
                try: content = file_p.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"CKGBuilder: UTF-8 decode error for {file_path_in_repo_str}. Trying 'latin-1'.")
                    try: content = file_p.read_text(encoding='latin-1')
                    except Exception as e_enc: logger.error(f"CKGBuilder: Could not read file {file_path_in_repo_str} due to encoding: {e_enc}. Skipping."); continue
                except OSError as e_os_read: logger.error(f"CKGBuilder: OS error reading file {file_path_in_repo_str}: {e_os_read}. Skipping."); continue
                await self.process_file_for_ckg(file_path_in_repo_str, content, lang_to_use)
                files_processed_count += 1
            except Exception as e: logger.error(f"CKGBuilder: Critical error processing file {file_path_in_repo_str} for CKG. Skipping this file. Error: {e}", exc_info=True)
        logger.info(f"CKGBuilder: Finished CKG build for project '{self.project_graph_id}'. Processed {files_processed_count} files for CKG out of {len(files_to_process)} identified files.")
        return files_processed_count