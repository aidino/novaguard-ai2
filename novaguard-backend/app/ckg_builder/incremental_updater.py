# novaguard-backend/app/ckg_builder/incremental_updater.py
import logging
import hashlib
from typing import List, Dict, Set, Optional, Tuple
from pathlib import Path

from neo4j import AsyncDriver
from app.core.graph_db import get_async_neo4j_driver
from app.models import Project
from .builder import CKGBuilder
from .query_api import CKGQueryAPI

logger = logging.getLogger(__name__)

class IncrementalCKGUpdater:
    """Handles incremental updates to the Code Knowledge Graph."""
    
    def __init__(self, project_model: Project, neo4j_driver: Optional[AsyncDriver] = None):
        self.project = project_model
        self.project_graph_id = f"novaguard_project_{self.project.id}"
        self._driver = neo4j_driver
        self.ckg_builder = CKGBuilder(project_model, neo4j_driver)
        self.query_api = CKGQueryAPI(neo4j_driver)
    
    async def _get_driver(self) -> AsyncDriver:
        """Get Neo4j driver instance."""
        if self._driver and hasattr(self._driver, '_closed') and not self._driver._closed:
            return self._driver
        driver = await get_async_neo4j_driver()
        if not driver or (hasattr(driver, '_closed') and driver._closed):
            logger.error("IncrementalCKGUpdater: Neo4j driver is not available or closed.")
            raise ConnectionError("Neo4j driver is not available or closed for IncrementalCKGUpdater.")
        self._driver = driver
        return self._driver

    def _calculate_file_hash(self, file_content: str) -> str:
        """Calculate SHA256 hash of file content."""
        return hashlib.sha256(file_content.encode('utf-8')).hexdigest()

    async def _get_stored_file_hashes(self) -> Dict[str, str]:
        """Get stored file hashes from the graph database."""
        query = """
        MATCH (f:File {project_graph_id: $project_graph_id})
        WHERE EXISTS(f.content_hash)
        RETURN f.path as file_path, f.content_hash as content_hash
        """
        driver = await self._get_driver()
        db_name = getattr(driver, '_database', 'neo4j')
        
        async with driver.session(database=db_name) as session:
            result = await session.run(query, {"project_graph_id": self.project_graph_id})
            records = [record async for record in result]
            await result.consume()
            
        return {record["file_path"]: record["content_hash"] for record in records}

    async def _update_file_hash(self, file_path: str, content_hash: str):
        """Update or set the content hash for a file in the graph."""
        query = """
        MATCH (f:File {composite_id: $composite_id})
        SET f.content_hash = $content_hash, f.updated_at = timestamp()
        """
        file_composite_id = f"{self.project_graph_id}:{file_path}"
        
        driver = await self._get_driver()
        db_name = getattr(driver, '_database', 'neo4j')
        
        async with driver.session(database=db_name) as session:
            await session.run(query, {
                "composite_id": file_composite_id,
                "content_hash": content_hash
            })

    async def _get_files_dependent_on(self, changed_files: List[str]) -> Set[str]:
        """Get files that might be affected by changes to the given files."""
        # This could be enhanced to include import relationships
        dependent_files = set()
        
        for changed_file in changed_files:
            # Get functions that are defined in the changed file
            functions_in_file = await self.query_api.get_functions_in_file(
                self.project_graph_id, changed_file
            )
            
            # For each function, find what calls it
            for func_info in functions_in_file:
                callers = await self.query_api.get_functions_calling(
                    self.project_graph_id, func_info["function_name"]
                )
                
                # Extract file paths from caller information
                for caller_info in callers:
                    # caller_info format: "function_name (file_path)"
                    if " (" in caller_info and caller_info.endswith(")"):
                        file_path = caller_info.split(" (")[-1][:-1]
                        dependent_files.add(file_path)
        
        return dependent_files

    async def identify_changed_files(self, current_files: Dict[str, str]) -> Tuple[List[str], List[str], List[str]]:
        """
        Identify which files have changed, been added, or been deleted.
        
        Args:
            current_files: Dict mapping file paths to their content
            
        Returns:
            Tuple of (changed_files, added_files, deleted_files)
        """
        stored_hashes = await self._get_stored_file_hashes()
        current_hashes = {
            path: self._calculate_file_hash(content) 
            for path, content in current_files.items()
        }
        
        changed_files = []
        added_files = []
        deleted_files = []
        
        # Find changed and added files
        for file_path, current_hash in current_hashes.items():
            if file_path in stored_hashes:
                if stored_hashes[file_path] != current_hash:
                    changed_files.append(file_path)
            else:
                added_files.append(file_path)
        
        # Find deleted files
        for file_path in stored_hashes:
            if file_path not in current_hashes:
                deleted_files.append(file_path)
        
        logger.info(
            f"IncrementalCKGUpdater: Identified {len(changed_files)} changed, "
            f"{len(added_files)} added, {len(deleted_files)} deleted files."
        )
        
        return changed_files, added_files, deleted_files

    async def _remove_file_from_graph(self, file_path: str):
        """Remove a file and all its related entities from the graph."""
        logger.info(f"IncrementalCKGUpdater: Removing file '{file_path}' from graph.")
        
        # Use the existing clear method from CKGBuilder
        await self.ckg_builder._clear_existing_data_for_file(file_path)
        
        # Also remove the file node itself
        query = """
        MATCH (f:File {composite_id: $composite_id})
        DETACH DELETE f
        """
        file_composite_id = f"{self.project_graph_id}:{file_path}"
        
        driver = await self._get_driver()
        db_name = getattr(driver, '_database', 'neo4j')
        
        async with driver.session(database=db_name) as session:
            await session.run(query, {"composite_id": file_composite_id})

    async def update_incremental(
        self, 
        changed_files: Dict[str, str], 
        include_dependents: bool = True
    ) -> Dict[str, Any]:
        """
        Perform incremental update of the CKG for specific files.
        
        Args:
            changed_files: Dict mapping file paths to their content
            include_dependents: Whether to also update files that depend on changed files
            
        Returns:
            Dict with update statistics
        """
        logger.info(f"IncrementalCKGUpdater: Starting incremental update for {len(changed_files)} files.")
        
        # Ensure project node exists
        await self.ckg_builder._ensure_project_node()
        
        files_to_update = set(changed_files.keys())
        
        if include_dependents:
            # Find files that might be affected by the changes
            dependent_files = await self._get_files_dependent_on(list(changed_files.keys()))
            files_to_update.update(dependent_files)
            logger.info(f"IncrementalCKGUpdater: Including {len(dependent_files)} dependent files in update.")
        
        # Clear existing data for files that will be updated
        for file_path in files_to_update:
            if file_path in changed_files:
                await self.ckg_builder._clear_existing_data_for_file(file_path)
        
        # Process each changed file
        processed_files = 0
        skipped_files = 0
        
        for file_path, content in changed_files.items():
            try:
                # Determine language from file extension
                language = self._guess_language_from_path(file_path)
                if not language:
                    logger.warning(f"IncrementalCKGUpdater: Could not determine language for {file_path}, skipping.")
                    skipped_files += 1
                    continue
                
                # Process the file
                await self.ckg_builder.process_file_for_ckg(file_path, content, language)
                
                # Update the file hash
                content_hash = self._calculate_file_hash(content)
                await self._update_file_hash(file_path, content_hash)
                
                processed_files += 1
                logger.debug(f"IncrementalCKGUpdater: Successfully processed {file_path}")
                
            except Exception as e:
                logger.error(f"IncrementalCKGUpdater: Error processing file {file_path}: {e}", exc_info=True)
                skipped_files += 1
        
        stats = {
            "total_files_to_update": len(files_to_update),
            "processed_files": processed_files,
            "skipped_files": skipped_files,
            "included_dependents": include_dependents,
            "dependent_files_count": len(files_to_update) - len(changed_files) if include_dependents else 0
        }
        
        logger.info(f"IncrementalCKGUpdater: Update completed. Stats: {stats}")
        return stats

    async def update_from_file_changes(
        self, 
        all_current_files: Dict[str, str],
        include_dependents: bool = True
    ) -> Dict[str, Any]:
        """
        Update the CKG based on file changes detected automatically.
        
        Args:
            all_current_files: Dict mapping all current file paths to their content
            include_dependents: Whether to also update files that depend on changed files
            
        Returns:
            Dict with update statistics
        """
        changed_files, added_files, deleted_files = await self.identify_changed_files(all_current_files)
        
        # Handle deleted files
        for deleted_file in deleted_files:
            await self._remove_file_from_graph(deleted_file)
        
        # Combine changed and added files for processing
        files_to_process = {}
        for file_path in changed_files + added_files:
            if file_path in all_current_files:
                files_to_process[file_path] = all_current_files[file_path]
        
        # Perform incremental update
        update_stats = await self.update_incremental(files_to_process, include_dependents)
        
        # Add information about deleted files
        update_stats.update({
            "deleted_files": len(deleted_files),
            "added_files": len(added_files),
            "changed_files": len(changed_files)
        })
        
        return update_stats

    def _guess_language_from_path(self, file_path: str) -> Optional[str]:
        """Guess programming language from file path."""
        path = Path(file_path)
        extension = path.suffix.lower()
        
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.go': 'go',
            '.cpp': 'cpp',
            '.cxx': 'cpp',
            '.cc': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.hpp': 'cpp',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.cs': 'csharp',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala'
        }
        
        return language_map.get(extension)

    async def get_update_impact_analysis(self, changed_files: List[str]) -> Dict[str, Any]:
        """
        Analyze the potential impact of updating specific files.
        
        Args:
            changed_files: List of file paths that will be changed
            
        Returns:
            Dict with impact analysis
        """
        logger.info(f"IncrementalCKGUpdater: Analyzing update impact for {len(changed_files)} files.")
        
        affected_functions = await self.query_api.get_affected_functions_by_file_change(
            self.project_graph_id, changed_files
        )
        
        dependent_files = await self._get_files_dependent_on(changed_files)
        
        impact_analysis = {
            "changed_files": changed_files,
            "affected_function_count": len(affected_functions),
            "dependent_files": list(dependent_files),
            "dependent_file_count": len(dependent_files),
            "total_files_to_update": len(changed_files) + len(dependent_files)
        }
        
        # Get some example affected functions for display
        if affected_functions:
            # Convert composite IDs back to readable format (this is simplified)
            impact_analysis["sample_affected_functions"] = list(affected_functions)[:10]
        
        logger.info(f"IncrementalCKGUpdater: Impact analysis completed: {impact_analysis}")
        return impact_analysis

    async def validate_graph_consistency(self) -> Dict[str, Any]:
        """
        Validate the consistency of the graph after updates.
        
        Returns:
            Dict with validation results
        """
        logger.info("IncrementalCKGUpdater: Validating graph consistency.")
        
        validation_results = {
            "orphaned_nodes": 0,
            "missing_relationships": 0,
            "duplicate_nodes": 0,
            "issues": []
        }
        
        driver = await self._get_driver()
        db_name = getattr(driver, '_database', 'neo4j')
        
        async with driver.session(database=db_name) as session:
            # Check for orphaned function nodes (functions without file relationships)
            orphan_query = """
            MATCH (f:Function {project_graph_id: $project_graph_id})
            WHERE NOT EXISTS((f)-[:DEFINED_IN]->(:File))
            RETURN count(f) as orphaned_functions
            """
            result = await session.run(orphan_query, {"project_graph_id": self.project_graph_id})
            record = await result.single()
            if record and record["orphaned_functions"] > 0:
                validation_results["orphaned_nodes"] += record["orphaned_functions"]
                validation_results["issues"].append(f"Found {record['orphaned_functions']} orphaned function nodes")
            
            # Check for duplicate composite IDs
            duplicate_query = """
            MATCH (n {project_graph_id: $project_graph_id})
            WHERE EXISTS(n.composite_id)
            WITH n.composite_id as composite_id, count(n) as node_count
            WHERE node_count > 1
            RETURN count(*) as duplicate_composite_ids
            """
            result = await session.run(duplicate_query, {"project_graph_id": self.project_graph_id})
            record = await result.single()
            if record and record["duplicate_composite_ids"] > 0:
                validation_results["duplicate_nodes"] = record["duplicate_composite_ids"]
                validation_results["issues"].append(f"Found {record['duplicate_composite_ids']} duplicate composite IDs")
        
        validation_results["is_valid"] = len(validation_results["issues"]) == 0
        
        logger.info(f"IncrementalCKGUpdater: Graph validation completed: {validation_results}")
        return validation_results 