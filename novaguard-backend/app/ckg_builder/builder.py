# novaguard-backend/app/ckg_builder/builder.py
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Union

from neo4j import AsyncDriver # Đảm bảo AsyncDriver được import

from app.core.graph_db import get_async_neo4j_driver
from app.models import Project
# Cập nhật import từ parsers để có ExtractedVariable
from .parsers import get_code_parser, ParsedFileResult, ExtractedFunction, ExtractedClass, ExtractedImport, ExtractedVariable

logger = logging.getLogger(__name__)

class CKGBuilder:
    def __init__(self, project_model: Project, neo4j_driver: Optional[AsyncDriver] = None):
        self.project = project_model
        # Tạo project_graph_id duy nhất cho mỗi project trong NovaGuard
        self.project_graph_id = f"novaguard_project_{self.project.id}"
        self._driver = neo4j_driver

    async def _get_driver(self) -> AsyncDriver:
        if self._driver and hasattr(self._driver, '_closed') and not self._driver._closed:
            return self._driver
        # Đảm bảo hàm get_async_neo4j_driver() trả về driver hợp lệ hoặc raise lỗi
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
        db_name = getattr(driver, 'database', None) or getattr(driver, '_database', 'neo4j')
        
        async with driver.session(database=db_name) as session:
            tx = None # Khởi tạo tx để có thể rollback trong khối finally nếu cần
            try:
                tx = await session.begin_transaction()
                for query, params in queries_with_params:
                    # logger.debug(f"CKG Executing Cypher: {query} with params: {params}")
                    await tx.run(query, params)
                await tx.commit()
                tx = None # Reset tx sau khi commit thành công
            except Exception as e:
                logger.error(f"CKGBuilder: Error running Cypher batch. Error: {e}", exc_info=True)
                if tx: # Nếu transaction đã bắt đầu và chưa commit/rollback
                    try:
                        logger.info("CKGBuilder: Attempting to rollback transaction due to error.")
                        await tx.rollback()
                    except Exception as e_rb:
                        logger.error(f"CKGBuilder: Error during transaction rollback: {e_rb}", exc_info=True)
                raise # Re-raise lỗi để hàm gọi bên ngoài xử lý

    async def _execute_write_queries_with_results(self, queries_with_params: List[Tuple[str, Dict[str, Any]]]):
        # ... (Giữ nguyên logic hàm này từ các phản hồi trước, đảm bảo xử lý lỗi và transaction tương tự _execute_write_queries) ...
        if not queries_with_params: return []
        driver = await self._get_driver()
        db_name = getattr(driver, 'database', None) or getattr(driver, '_database', 'neo4j')
        all_results = []
        async with driver.session(database=db_name) as session:
            tx = None
            try:
                tx = await session.begin_transaction()
                for query, params in queries_with_params:
                    result_cursor = await tx.run(query, params)
                    records = [record.data() async for record in result_cursor]
                    summary = await result_cursor.consume() # Quan trọng: consume result
                    all_results.append(records)
                await tx.commit()
                tx = None
            except Exception as e:
                logger.error(f"CKGBuilder: Error running Cypher batch (with results). Error: {e}", exc_info=True)
                if tx: await tx.rollback()
                raise
        return all_results


    async def _ensure_project_node(self):
        # Đã được cung cấp ở các phản hồi trước, đảm bảo nó tạo Node :Project
        # với graph_id, name, novaguard_id, language và các timestamp.
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
            "novaguard_project_id": str(self.project.id), # Neo4j có thể xử lý int, nhưng string an toàn hơn
            "language": self.project.language
        }
        await self._execute_write_queries([(query, params)])
        logger.info(f"CKGBuilder: Ensured Project node '{self.project_graph_id}' exists/updated.")

    async def _clear_existing_data_for_file(self, file_path_in_repo: str):
        file_composite_id = f"{self.project_graph_id}:{file_path_in_repo}"
        logger.info(f"CKGBuilder: Clearing existing CKG data for file '{file_path_in_repo}' in project '{self.project_graph_id}'")
        
        # Query này cần xóa tất cả các node được "ancored" hoặc "defined in" file này
        # và các relationships của chúng.
        # Các node có thể là: Class, Function, Method, Variable, Decorator, ExceptionType (nếu được coi là defined in file)
        # Variable nodes có composite_id bao gồm file_path, nên chúng sẽ dễ tìm hơn.
        query = """
        MATCH (file_node:File {composite_id: $file_composite_id})
        // Tìm Entities (Class, Function/Method) được định nghĩa TRỰC TIẾP trong file này
        OPTIONAL MATCH (entity)-[:DEFINED_IN]->(file_node)
        WHERE any(label IN labels(entity) WHERE label IN ['Class', 'Function']) // Function bao gồm Method
        
        // Tìm Variables được định nghĩa TRỰC TIẾP trong file này (global vars)
        // hoặc các Variable là con của các Entities trên (params, local vars, attributes)
        OPTIONAL MATCH (var_global:Variable)-[:DEFINED_IN_FILE]->(file_node)
        OPTIONAL MATCH (entity)-[:HAS_PARAMETER|DECLARES_VARIABLE|DECLARES_ATTRIBUTE]->(var_child:Variable)

        // Tìm Decorators được định nghĩa/áp dụng trong file này (giả sử decorator node có file_path)
        OPTIONAL MATCH (dec:Decorator {file_path: $file_path_prop, project_graph_id: $project_graph_id_prop})
        
        // Thu thập tất cả các node cần xóa (file, entities, vars, decorators liên quan đến file này)
        // Cần cẩn thận để không xóa các ExceptionType dùng chung nếu chúng không "thuộc" file này
        WITH file_node, 
             collect(DISTINCT entity) as entities_in_file, 
             collect(DISTINCT var_global) as global_vars_in_file,
             collect(DISTINCT var_child) as child_vars_of_entities,
             collect(DISTINCT dec) as decorators_in_file
        
        // Gộp tất cả các node cần xóa vào một danh sách
        WITH file_node, entities_in_file + global_vars_in_file + child_vars_of_entities + decorators_in_file + [file_node] as all_nodes_to_delete_from_file
        UNWIND all_nodes_to_delete_from_file as ntd
        DETACH DELETE ntd // Xóa node và tất cả relationships của nó
        RETURN count(DISTINCT ntd) as deleted_nodes_count
        """
        params = {
            "file_composite_id": file_composite_id,
            "file_path_prop": file_path_in_repo, # Để tìm decorator theo file_path
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
        file_path_in_repo: str, # File nơi biến này được trích xuất
        owner_composite_id: Optional[str], 
        owner_node_label: Optional[str],
        relationship_type_from_owner: Optional[str]
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        
        scope_owner_identifier = var_data.scope_name # Tên của function/class hoặc tên file cho global
        
        # Tạo composite_id cho Variable
        # <project_id>:<file_path_defined>:<owner_scope_name>:<var_name>:<line_defined>
        var_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{scope_owner_identifier}:{var_data.name}:{var_data.start_line}"

        var_props = {
            "name": var_data.name,
            "file_path": file_path_in_repo, 
            "start_line": var_data.start_line,
            "end_line": var_data.end_line,
            "scope_name": var_data.scope_name, 
            "scope_type": var_data.scope_type, 
            "var_type_hint": var_data.var_type, 
            "is_parameter": var_data.is_parameter,
            "project_graph_id": self.project_graph_id,
            "composite_id": var_composite_id
        }
        cypher = ""
        params = {}

        if owner_composite_id and owner_node_label and relationship_type_from_owner:
            cypher = f"""
            MATCH (owner:{owner_node_label} {{composite_id: $owner_composite_id}})
            MERGE (v:Variable {{composite_id: $var_composite_id}})
            ON CREATE SET v = $var_props, v.ckg_created_at = timestamp()
            ON MATCH SET v.end_line = $var_props.end_line, 
                         v.var_type_hint = $var_props.var_type_hint, 
                         v.ckg_updated_at = timestamp()
            MERGE (owner)-[:{relationship_type_from_owner}]->(v)
            """
            params = {
                "owner_composite_id": owner_composite_id,
                "var_composite_id": var_composite_id,
                "var_props": var_props
            }
        elif var_data.scope_type == "global_variable": # scope_type "file" được đổi thành "global_variable"
            file_composite_id_for_global = f"{self.project_graph_id}:{file_path_in_repo}"
            cypher = """
            MATCH (f:File {composite_id: $file_composite_id})
            MERGE (v:Variable {composite_id: $var_composite_id})
            ON CREATE SET v = $var_props, v.ckg_created_at = timestamp()
            ON MATCH SET v.end_line = $var_props.end_line, 
                         v.var_type_hint = $var_props.var_type_hint, 
                         v.ckg_updated_at = timestamp()
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

        await self._clear_existing_data_for_file(file_path_in_repo)

        cypher_batch: List[Tuple[str, Dict[str, Any]]] = []
        file_composite_id = f"{self.project_graph_id}:{file_path_in_repo}"

        # 1. File Node
        file_node_props = {
            "path": file_path_in_repo, "project_graph_id": self.project_graph_id,
            "language": language, "name": Path(file_path_in_repo).name,
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

        # 2. Import Nodes and Relationships
        for imp_data in parsed_data.imports:
            if imp_data.module_path:
                module_composite_id = f"{self.project_graph_id}:MODULE:{imp_data.module_path}"
                module_name_from_path = imp_data.module_path.split('.')[-1]
                if imp_data.relative_level > 0 and not imp_data.module_path.startswith('.'): # Đảm bảo module_path cho relative import bắt đầu bằng "."
                    actual_module_path = "." * imp_data.relative_level + imp_data.module_path
                    module_composite_id = f"{self.project_graph_id}:MODULE:{actual_module_path}"
                else:
                    actual_module_path = imp_data.module_path

                cypher_batch.append((
                    """
                    MERGE (m:Module {composite_id: $module_composite_id})
                    ON CREATE SET m.path = $module_path, m.name = $module_name, 
                                  m.project_graph_id = $project_graph_id, m.is_stub = true, 
                                  m.relative_level = $relative_level, m.ckg_created_at = timestamp()
                    ON MATCH SET m.ckg_updated_at = timestamp() // Có thể cập nhật is_stub nếu module được parse sau
                    WITH m
                    MATCH (f:File {composite_id: $file_composite_id})
                    MERGE (f)-[r:IMPORTS_MODULE {type: $import_type, line: $import_line}]->(m) // Đưa type, line vào key của MERGE
                    ON CREATE SET r.imported_names = [item IN $imported_names_list WHERE item.original IS NOT NULL | item.original], 
                                  r.aliases = [item IN $imported_names_list WHERE item.alias IS NOT NULL | item.alias],
                                  r.timestamp = timestamp()
                    ON MATCH SET  r.imported_names = [item IN $imported_names_list WHERE item.original IS NOT NULL | item.original], 
                                  r.aliases = [item IN $imported_names_list WHERE item.alias IS NOT NULL | item.alias]
                    """, {
                        "module_composite_id": module_composite_id, "module_path": actual_module_path,
                        "module_name": module_name_from_path, "project_graph_id": self.project_graph_id,
                        "relative_level": imp_data.relative_level, "file_composite_id": file_composite_id,
                        "import_type": imp_data.import_type,
                        "imported_names_list": [{"original": name, "alias": alias} for name, alias in imp_data.imported_names],
                        "import_line": imp_data.start_line
                    }
                ))
        
        # Xử lý Global Variables được parse từ file
        for g_var_data in parsed_data.global_variables:
            cypher_tuple = self._prepare_variable_cypher_tuple(
                g_var_data, file_path_in_repo, 
                owner_composite_id=None, # Global vars không có owner là function/class trực tiếp
                owner_node_label=None, 
                relationship_type_from_owner=None
            )
            if cypher_tuple: cypher_batch.append(cypher_tuple)

        # 3. Class Nodes & related (Methods, Attributes, Decorators, Superclasses, Exceptions)
        for cls_data in parsed_data.classes:
            class_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{cls_data.name}:{cls_data.start_line}"
            class_props = {
                "name": cls_data.name, "file_path": file_path_in_repo,
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

            for super_name in cls_data.superclasses:
                super_class_placeholder_id = f"{self.project_graph_id}:CLASS_PLACEHOLDER:{super_name}" # ID cho placeholder
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
            
            for attr_var in cls_data.attributes: # Class attributes
                cypher_tuple = self._prepare_variable_cypher_tuple(attr_var, file_path_in_repo, class_composite_id, "Class", "DECLARES_ATTRIBUTE")
                if cypher_tuple: cypher_batch.append(cypher_tuple)

            for dec_name in cls_data.decorators: # Class decorators
                decorator_class_comp_id = f"{self.project_graph_id}:{file_path_in_repo}:DECORATOR:{dec_name}:{cls_data.start_line}"
                cypher_batch.append((
                    """
                    MATCH (owner:Class {composite_id: $owner_id})
                    MERGE (d:Decorator {composite_id: $dec_comp_id})
                    ON CREATE SET d.name = $dec_name, d.project_graph_id = $project_graph_id, 
                                  d.file_path = $file_path, d.applied_to_type = 'Class', d.ckg_created_at = timestamp()
                    MERGE (owner)-[:HAS_DECORATOR]->(d)
                    """, {
                        "owner_id": class_composite_id, "dec_name": dec_name, "project_graph_id": self.project_graph_id,
                        "dec_comp_id": decorator_class_comp_id, "file_path": file_path_in_repo
                    }
                ))

            for method_data in cls_data.methods:
                method_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{method_data.name}:{method_data.start_line}"
                method_props = {
                    "name": method_data.name, "file_path": file_path_in_repo,
                    "start_line": method_data.start_line, "end_line": method_data.end_line,
                    "signature": method_data.signature, "parameters_str": method_data.parameters_str,
                    "class_name": cls_data.name, "project_graph_id": self.project_graph_id,
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
                    cypher_tuple = self._prepare_variable_cypher_tuple(param_var, file_path_in_repo, method_composite_id, "Method", "HAS_PARAMETER")
                    if cypher_tuple: cypher_batch.append(cypher_tuple)
                for local_var in method_data.local_variables:
                    cypher_tuple = self._prepare_variable_cypher_tuple(local_var, file_path_in_repo, method_composite_id, "Method", "DECLARES_VARIABLE")
                    if cypher_tuple: cypher_batch.append(cypher_tuple)
                for dec_name in method_data.decorators:
                    decorator_method_comp_id = f"{self.project_graph_id}:{file_path_in_repo}:DECORATOR:{dec_name}:{method_data.start_line}"
                    cypher_batch.append((
                        """
                        MATCH (owner:Method {composite_id: $owner_id})
                        MERGE (d:Decorator {composite_id: $dec_comp_id})
                        ON CREATE SET d.name = $dec_name, d.project_graph_id = $project_graph_id,
                                      d.file_path = $file_path, d.applied_to_type = 'Method', d.ckg_created_at = timestamp()
                        MERGE (owner)-[:HAS_DECORATOR]->(d)
                        """, {
                            "owner_id": method_composite_id, "dec_name": dec_name, "project_graph_id": self.project_graph_id,
                            "dec_comp_id": decorator_method_comp_id, "file_path": file_path_in_repo
                        }
                    ))
                for ex_name in method_data.raised_exceptions:
                    ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                    cypher_batch.append((
                        """
                        MATCH (owner:Method {composite_id: $owner_id})
                        MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                        ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                        MERGE (owner)-[:RAISES_EXCEPTION]->(ex)
                        """, {"owner_id": method_composite_id, "ex_name": ex_name, 
                              "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id}
                    ))
                for ex_name in method_data.handled_exceptions:
                    ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                    cypher_batch.append((
                        """
                        MATCH (owner:Method {composite_id: $owner_id})
                        MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                        ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                        MERGE (owner)-[:HANDLES_EXCEPTION]->(ex)
                        """, {"owner_id": method_composite_id, "ex_name": ex_name, 
                              "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id}
                    ))

        # 4. Global Function Nodes & related
        for func_data in parsed_data.functions: # Chỉ global functions
            func_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{func_data.name}:{func_data.start_line}"
            func_props = {
                "name": func_data.name, "file_path": file_path_in_repo,
                "start_line": func_data.start_line, "end_line": func_data.end_line,
                "signature": func_data.signature, "parameters_str": func_data.parameters_str,
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
            # Parameters, Local Vars, Decorators, Exceptions cho global functions
            for param_var in func_data.parameters:
                cypher_tuple = self._prepare_variable_cypher_tuple(param_var, file_path_in_repo, func_composite_id, "Function", "HAS_PARAMETER")
                if cypher_tuple: cypher_batch.append(cypher_tuple)
            for local_var in func_data.local_variables:
                cypher_tuple = self._prepare_variable_cypher_tuple(local_var, file_path_in_repo, func_composite_id, "Function", "DECLARES_VARIABLE")
                if cypher_tuple: cypher_batch.append(cypher_tuple)
            for dec_name in func_data.decorators:
                decorator_func_comp_id = f"{self.project_graph_id}:{file_path_in_repo}:DECORATOR:{dec_name}:{func_data.start_line}"
                cypher_batch.append((
                    """
                    MATCH (owner:Function {composite_id: $owner_id})
                    MERGE (d:Decorator {composite_id: $dec_comp_id})
                    ON CREATE SET d.name = $dec_name, d.project_graph_id = $project_graph_id,
                                  d.file_path = $file_path, d.applied_to_type = 'Function', d.ckg_created_at = timestamp()
                    MERGE (owner)-[:HAS_DECORATOR]->(d)
                    """, {
                        "owner_id": func_composite_id, "dec_name": dec_name, "project_graph_id": self.project_graph_id,
                        "dec_comp_id": decorator_func_comp_id, "file_path": file_path_in_repo
                    }
                ))
            for ex_name in func_data.raised_exceptions:
                ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                cypher_batch.append((
                    """
                    MATCH (owner:Function {composite_id: $owner_id})
                    MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                    ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                    MERGE (owner)-[:RAISES_EXCEPTION]->(ex)
                    """, {"owner_id": func_composite_id, "ex_name": ex_name, 
                          "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id }
                ))
            for ex_name in func_data.handled_exceptions:
                ex_type_comp_id = f"{self.project_graph_id}:EXCEPTION_TYPE:{ex_name}"
                cypher_batch.append((
                    """
                    MATCH (owner:Function {composite_id: $owner_id})
                    MERGE (ex:ExceptionType {composite_id: $ex_type_comp_id})
                    ON CREATE SET ex.name = $ex_name, ex.project_graph_id = $project_graph_id, ex.ckg_created_at = timestamp()
                    MERGE (owner)-[:HANDLES_EXCEPTION]->(ex)
                    """, {"owner_id": func_composite_id, "ex_name": ex_name, 
                           "project_graph_id": self.project_graph_id, "ex_type_comp_id": ex_type_comp_id}
                ))
        
        # Commit batch đầu tiên chứa các node và relationships cơ bản
        if cypher_batch:
            logger.debug(f"CKGBuilder: Executing main entity batch of {len(cypher_batch)} Cypher queries for file {file_path_in_repo}.")
            await self._execute_write_queries(cypher_batch)
        
        # --- Link CALLS (Sử dụng Query Cypher Nâng Cao với APOC) ---
        call_link_queries_batch: List[Tuple[str, Dict[str, Any]]] = []
        all_callable_entities_in_file = parsed_data.functions + [
            method for cls_data in parsed_data.classes for method in cls_data.methods
        ]

        for defined_entity in all_callable_entities_in_file:
            if not defined_entity.calls:
                continue

            caller_composite_id = f"{self.project_graph_id}:{file_path_in_repo}:{defined_entity.name}:{defined_entity.start_line}"
            caller_node_label_for_match = ":Method:Function" if defined_entity.class_name else ":Function"

            for called_name, base_object_name, call_type, call_site_line in defined_entity.calls:
                call_params = {
                    "caller_composite_id": caller_composite_id,
                    "callee_name_prop": called_name, # Tên hàm/method được gọi
                    "project_graph_id_prop": self.project_graph_id,
                    "caller_file_path_prop": file_path_in_repo,
                    "call_type_prop": call_type, # Loại lời gọi từ parser
                    "base_object_prop": base_object_name, # 'self', tên class, hoặc tên biến
                    "call_site_line_prop": call_site_line,
                    "caller_class_name_prop": defined_entity.class_name # Tên class của caller (nếu là method)
                }
                
                # Query Cypher để tìm callee và tạo CALLS relationship.
                # Query này cần APOC plugin.
                resolve_and_link_query_apoc = f"""
                MATCH (caller{caller_node_label_for_match} {{composite_id: $caller_composite_id}})
                
                CALL apoc.cypher.doIt('
                    // Subquery để tìm callee, truyền các tham số cần thiết
                    WITH $caller_composite_id AS caller_cid, 
                         $callee_name_prop AS cn_prop, $project_graph_id_prop AS pgid_prop,
                         $caller_file_path_prop AS cfile_prop, $call_type_prop AS ct_prop,
                         $base_object_prop AS bo_prop, $caller_class_name_prop AS ccn_prop

                    // Attempt 1: Instance method call (self.method())
                    CALL apoc.when(ct_prop = "instance_method_call" AND ccn_prop IS NOT NULL,
                        \\"
                        MATCH (caller_cls:Class {{name: ccn_prop, project_graph_id: pgid_prop}})
                        // Tìm method trong class này hoặc superclasses
                        OPTIONAL MATCH (callee_direct:Method {{name: cn_prop, class_name: ccn_prop, project_graph_id: pgid_prop}})
                        WHERE (callee_direct)-[:DEFINED_IN_CLASS]->(caller_cls)
                        WITH caller_cls, callee_direct
                        OPTIONAL MATCH (caller_cls)-[:INHERITS_FROM*0..5]->(superclass:Class)
                        OPTIONAL MATCH (callee_super:Method {{name: cn_prop, project_graph_id: pgid_prop}})
                        WHERE (callee_super)-[:DEFINED_IN_CLASS]->(superclass) AND callee_direct IS NULL
                        RETURN COALESCE(callee_direct, callee_super) AS found
                        \\",
                        \\"RETURN null AS found\\",
                        {{ccn_prop:ccn_prop, cn_prop:cn_prop, pgid_prop:pgid_prop}}
                    ) YIELD value AS m1

                    // Attempt 2: Direct function call or class method call
                    CALL apoc.when(m1.found IS NULL,
                        \\"
                        CALL apoc.when(ct_prop STARTS WITH \\"direct\\" OR ct_prop STARTS WITH \\"constructor\\", // direct_function_call, constructor_call
                            // Tìm Function (không phải method) trong cùng file hoặc toàn project
                            \'\'\'
                            OPTIONAL MATCH (fsf:Function {{name: cn_prop, file_path: cfile_prop, project_graph_id: pgid_prop, is_method: false}})
                            WITH fsf
                            OPTIONAL MATCH (faf:Function {{name: cn_prop, project_graph_id: pgid_prop, is_method: false}}) WHERE fsf IS NULL
                            RETURN COALESCE(fsf, faf) AS found_func
                            \'\'\',
                            // Else (không phải direct call, có thể là class method call on class name)
                            \'\'\' 
                            CALL apoc.when(ct_prop ENDS WITH \\"_on_class\\" AND bo_prop IS NOT NULL,
                                \\\'
                                MATCH (target_cls:Class {{name: bo_prop, project_graph_id: pgid_prop}})
                                OPTIONAL MATCH (cmethod:Method {{name: cn_prop, class_name: bo_prop, project_graph_id: pgid_prop}})
                                WHERE (cmethod)-[:DEFINED_IN_CLASS]->(target_cls)
                                RETURN cmethod AS found_func
                                \\\',
                                \\\'RETURN NULL AS found_func\\\', // Not a class method call on class name
                                {{bo_prop:bo_prop, cn_prop:cn_prop, pgid_prop:pgid_prop}}
                            ) YIELD value AS class_method_result RETURN class_method_result.found_func AS found_func
                            \'\'\',
                            {{cn_prop:cn_prop, cfile_prop:cfile_prop, pgid_prop:pgid_prop, ct_prop:ct_prop, bo_prop:bo_prop}}
                        ) YIELD value AS m2_func
                        
                        // Attempt 3: Method call on other object (khó nhất)
                        CALL apoc.when(m1.found IS NULL AND m2_func.found_func IS NULL AND ct_prop = \\"method_call_on_object\\",
                           \'\'\' MATCH (m_other:Method {{name: cn_prop, project_graph_id: pgid_prop}}) RETURN m_other AS found_other LIMIT 1 \'\'\', // Lấy 1 match nếu có nhiều
                           \'\'\' RETURN null AS found_other \'\'\',
                           {{cn_prop:cn_prop, pgid_prop:pgid_prop}}
                        ) YIELD value AS m3_other
                        RETURN COALESCE(m1.found, m2_func.found_func, m3_other.found_other) AS final_callee
                        \\",
                        \\"RETURN m1.found AS final_callee\\", // Nếu m1 đã tìm thấy
                        {{caller_cid:caller_composite_id, cn_prop:$callee_name_prop, pgid_prop:$project_graph_id_prop,
                          cfile_prop:$caller_file_path_prop, ct_prop:$call_type_prop,
                          bo_prop:$base_object_prop, ccn_prop:$caller_class_name_prop}}
                    ) YIELD value
                    WITH value.final_callee AS final_callee
                    WHERE final_callee IS NOT NULL
                    RETURN final_callee
                ', // End of apoc.cypher.doIt string
                $call_params // Params cho apoc.cypher.doIt
                ) YIELD value AS callee_map // Kết quả từ apoc.cypher.doIt
                
                WITH caller, callee_map.final_callee AS actual_callee
                WHERE actual_callee IS NOT NULL // Chỉ tạo relationship nếu tìm thấy callee
                MERGE (caller)-[r:CALLS]->(actual_callee)
                ON CREATE SET r.type = $call_type_prop,
                              r.base_object_name = $base_object_prop,
                              r.call_site_line = $call_site_line_prop,
                              r.call_count = 1, 
                              r.first_seen_at = timestamp()
                ON MATCH SET  r.call_count = coalesce(r.call_count, 0) + 1,
                              r.last_seen_at = timestamp()
                // Thêm log để debug nếu không tạo được relationship
                // WITH caller, actual_callee, r
                // RETURN caller.name as c_name, actual_callee.name as ac_name, r.call_count as count
                """
                call_link_queries_batch.append((resolve_and_link_query_apoc, call_params))

        if call_link_queries_batch:
            logger.debug(f"CKGBuilder: Executing batch of {len(call_link_queries_batch)} CALLS link queries for file {file_path_in_repo}.")
            try:
                await self._execute_write_queries(call_link_queries_batch)
            except Exception as e_calls:
                logger.error(f"CKGBuilder: Error executing CALLS link batch for {file_path_in_repo}: {e_calls}", exc_info=True)
                # Ghi log params để debug
                for q_idx, (q_str, q_params) in enumerate(call_link_queries_batch):
                    logger.debug(f"CALLS query {q_idx} params: {q_params}")


        logger.info(f"CKGBuilder: Finished CKG processing for file '{file_path_in_repo}'.")


    async def build_for_project_from_path(self, repo_local_path: str):
        # ... (Giữ nguyên logic hàm này từ các phản hồi trước) ...
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