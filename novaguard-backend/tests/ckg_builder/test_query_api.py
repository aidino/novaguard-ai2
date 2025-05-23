# novaguard-backend/tests/ckg_builder/test_query_api.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

from app.ckg_builder.query_api import (
    CKGQueryAPI, 
    FunctionCallInfo, 
    DependencyInfo, 
    InheritanceInfo
)


class TestCKGQueryAPI:
    """Test suite for CKG Query API."""

    @pytest.fixture
    def mock_driver(self):
        """Mock Neo4j driver."""
        mock_driver = Mock()
        mock_driver._closed = False
        return mock_driver

    @pytest.fixture
    def query_api(self, mock_driver):
        """Create CKGQueryAPI instance with mocked driver."""
        return CKGQueryAPI(neo4j_driver=mock_driver)

    @pytest.fixture
    def mock_session(self):
        """Mock Neo4j session."""
        session = Mock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.fixture
    def mock_records(self):
        """Sample mock records for testing."""
        return [
            {
                "project_name": "test-project",
                "primary_language": "python",
                "file_count": 10,
                "class_count": 5,
                "function_count": 25,
                "variable_count": 50
            }
        ]

    @pytest.mark.asyncio
    async def test_get_project_overview(self, query_api, mock_driver, mock_session, mock_records):
        """Test project overview retrieval."""
        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(return_value=iter([Mock(data=lambda: mock_records[0])]))
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_project_overview("novaguard_project_1")

            # Verify
            assert result["project_name"] == "test-project"
            assert result["primary_language"] == "python"
            assert result["file_count"] == 10
            assert result["class_count"] == 5
            assert result["function_count"] == 25
            assert result["variable_count"] == 50

    @pytest.mark.asyncio
    async def test_get_function_calls(self, query_api, mock_driver, mock_session):
        """Test function call relationships retrieval."""
        # Setup mock data
        mock_call_records = [
            {
                "caller_name": "process_data",
                "caller_file": "main.py",
                "caller_class": None,
                "callee_name": "validate_input",
                "callee_file": "utils.py",
                "callee_class": None,
                "call_line": 15
            },
            {
                "caller_name": "save_data",
                "caller_file": "database.py",
                "caller_class": "DataManager",
                "callee_name": "connect",
                "callee_file": "database.py",
                "callee_class": "DataManager",
                "call_line": 45
            }
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_call_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_function_calls("novaguard_project_1")

            # Verify
            assert len(result) == 2
            assert isinstance(result[0], FunctionCallInfo)
            assert result[0].caller_name == "process_data"
            assert result[0].callee_name == "validate_input"
            assert result[1].caller_class == "DataManager"

    @pytest.mark.asyncio
    async def test_get_functions_calling_specific_function(self, query_api, mock_driver, mock_session):
        """Test finding functions that call a specific target function."""
        # Setup mock data
        mock_caller_records = [
            {"caller_name": "main", "caller_file": "main.py"},
            {"caller_name": "test_process", "caller_file": "test_main.py"}
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_caller_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_functions_calling("novaguard_project_1", "process_data")

            # Verify
            assert len(result) == 2
            assert "main (main.py)" in result
            assert "test_process (test_main.py)" in result

    @pytest.mark.asyncio
    async def test_get_class_hierarchy(self, query_api, mock_driver, mock_session):
        """Test class inheritance relationships retrieval."""
        # Setup mock data
        mock_inheritance_records = [
            {
                "child_class": "DogService",
                "child_file": "services/dog.py",
                "parent_class": "AnimalService",
                "parent_file": "services/base.py"
            },
            {
                "child_class": "CatService",
                "child_file": "services/cat.py", 
                "parent_class": "AnimalService",
                "parent_file": "services/base.py"
            }
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_inheritance_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_class_hierarchy("novaguard_project_1")

            # Verify
            assert len(result) == 2
            assert isinstance(result[0], InheritanceInfo)
            assert result[0].child_class == "DogService"
            assert result[0].parent_class == "AnimalService"
            assert result[1].child_class == "CatService"

    @pytest.mark.asyncio
    async def test_find_large_classes(self, query_api, mock_driver, mock_session):
        """Test finding classes with many methods (God classes)."""
        # Setup mock data
        mock_large_class_records = [
            {
                "class_name": "UserManager",
                "file_path": "services/user.py",
                "method_count": 25
            },
            {
                "class_name": "DataProcessor",
                "file_path": "core/processor.py",
                "method_count": 22
            }
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_large_class_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.find_large_classes("novaguard_project_1", min_methods=20)

            # Verify
            assert len(result) == 2
            assert result[0]["class_name"] == "UserManager"
            assert result[0]["method_count"] == 25
            assert result[1]["class_name"] == "DataProcessor"
            assert result[1]["method_count"] == 22

    @pytest.mark.asyncio
    async def test_find_circular_function_calls(self, query_api, mock_driver, mock_session):
        """Test finding circular function call dependencies."""
        # Setup mock data
        mock_cycle_records = [
            {"cycle": ["func_a", "func_b", "func_c", "func_a"]},
            {"cycle": ["recursive_func", "recursive_func"]}
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_cycle_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.find_circular_function_calls("novaguard_project_1")

            # Verify
            assert len(result) == 2
            assert result[0] == ["func_a", "func_b", "func_c", "func_a"]
            assert result[1] == ["recursive_func", "recursive_func"]

    @pytest.mark.asyncio
    async def test_get_variable_usage(self, query_api, mock_driver, mock_session):
        """Test variable usage information retrieval."""
        # Setup mock data
        mock_variable_records = [
            {
                "variable_name": "config",
                "file_path": "main.py",
                "scope_type": "global_variable",
                "used_by_functions": ["main", "initialize"],
                "modified_by_functions": ["setup"]
            }
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_variable_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_variable_usage("novaguard_project_1", "config")

            # Verify
            assert len(result) == 1
            assert result[0]["variable_name"] == "config"
            assert result[0]["scope_type"] == "global_variable"
            assert "main" in result[0]["used_by_functions"]
            assert "setup" in result[0]["modified_by_functions"]

    @pytest.mark.asyncio
    async def test_get_function_complexity_metrics(self, query_api, mock_driver, mock_session):
        """Test function complexity metrics retrieval."""
        # Setup mock data
        mock_complexity_records = [
            {
                "function_name": "complex_algorithm",
                "file_path": "algorithms.py",
                "class_name": None,
                "calls_out": 8,
                "calls_in": 3,
                "total_coupling": 11
            },
            {
                "function_name": "process",
                "file_path": "processor.py",
                "class_name": "DataProcessor",
                "calls_out": 5,
                "calls_in": 2,
                "total_coupling": 7
            }
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_complexity_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_function_complexity_metrics("novaguard_project_1")

            # Verify
            assert len(result) == 2
            assert result[0]["function_name"] == "complex_algorithm"
            assert result[0]["total_coupling"] == 11
            assert result[1]["class_name"] == "DataProcessor"

    @pytest.mark.asyncio
    async def test_search_entities(self, query_api, mock_driver, mock_session):
        """Test entity search functionality."""
        # Setup mock data
        mock_search_records = [
            {
                "name": "user_service",
                "labels": ["Function"],
                "file_path": "services/user.py",
                "additional_info": "def user_service(user_id: int) -> User"
            },
            {
                "name": "User",
                "labels": ["Class"],
                "file_path": "models/user.py",
                "additional_info": None
            }
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_search_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.search_entities("novaguard_project_1", "user")

            # Verify
            assert len(result) == 2
            assert result[0]["name"] == "user_service"
            assert result[0]["type"] == ["Function"]
            assert result[1]["name"] == "User"
            assert result[1]["type"] == ["Class"]

    @pytest.mark.asyncio
    async def test_get_affected_functions_by_file_change(self, query_api, mock_driver, mock_session):
        """Test getting functions affected by file changes."""
        # Setup mock data
        mock_affected_records = [
            {"affected_function_ids": ["func1_id", "func2_id", "func3_id"]}
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_affected_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_affected_functions_by_file_change(
                "novaguard_project_1", 
                ["main.py", "utils.py"]
            )

            # Verify
            assert isinstance(result, set)
            assert len(result) == 3
            assert "func1_id" in result
            assert "func2_id" in result
            assert "func3_id" in result

    @pytest.mark.asyncio
    async def test_get_files_by_language(self, query_api, mock_driver, mock_session):
        """Test getting files grouped by language."""
        # Setup mock data
        mock_language_records = [
            {"language": "python", "files": ["main.py", "utils.py", "models.py"]},
            {"language": "javascript", "files": ["frontend.js", "api.js"]}
        ]

        # Setup mocks
        mock_driver.session.return_value = mock_session
        mock_result = AsyncMock()
        mock_result.__aiter__ = AsyncMock(
            return_value=iter([Mock(data=lambda r=record: r) for record in mock_language_records])
        )
        mock_result.consume = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute
            result = await query_api.get_files_by_language("novaguard_project_1")

            # Verify
            assert len(result) == 2
            assert result["python"] == ["main.py", "utils.py", "models.py"]
            assert result["javascript"] == ["frontend.js", "api.js"]

    @pytest.mark.asyncio
    async def test_error_handling(self, query_api, mock_driver, mock_session):
        """Test error handling in query execution."""
        # Setup mocks to raise an exception
        mock_driver.session.return_value = mock_session
        mock_session.run = AsyncMock(side_effect=Exception("Database connection error"))

        with patch.object(query_api, '_get_driver', return_value=mock_driver):
            # Execute and verify exception is raised
            with pytest.raises(Exception) as exc_info:
                await query_api.get_project_overview("novaguard_project_1")
            
            assert "Database connection error" in str(exc_info.value)

    def test_dataclass_creation(self):
        """Test that dataclasses are created correctly."""
        # Test FunctionCallInfo
        call_info = FunctionCallInfo(
            caller_name="func_a",
            caller_file="file_a.py",
            caller_class=None,
            callee_name="func_b",
            callee_file="file_b.py",
            callee_class="ClassB",
            call_line=42
        )
        
        assert call_info.caller_name == "func_a"
        assert call_info.callee_class == "ClassB"
        assert call_info.call_line == 42

        # Test DependencyInfo
        dep_info = DependencyInfo(
            from_file="main.py",
            to_file="utils.py",
            import_type="from",
            imported_names=["helper_func", "CONSTANT"]
        )
        
        assert dep_info.from_file == "main.py"
        assert len(dep_info.imported_names) == 2

        # Test InheritanceInfo
        inherit_info = InheritanceInfo(
            child_class="Dog",
            child_file="animals/dog.py",
            parent_class="Animal",
            parent_file="animals/base.py"
        )
        
        assert inherit_info.child_class == "Dog"
        assert inherit_info.parent_class == "Animal" 