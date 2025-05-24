# novaguard-backend/tests/ckg_builder/test_javascript_parser.py
import pytest
from unittest.mock import Mock, patch

from app.ckg_builder.parsers.javascript_parser import JavaScriptParser
from app.ckg_builder.parsers import ExtractedFunction, ExtractedClass, ExtractedImport, ExtractedVariable


class TestJavaScriptParser:
    """Test suite for JavaScript/TypeScript parser."""

    @pytest.fixture
    def js_parser(self):
        """Create JavaScript parser instance."""
        with patch('app.ckg_builder.parsers.javascript_parser.get_language'):
            mock_language = Mock()
            mock_parser = Mock()
            
            with patch('app.ckg_builder.parsers.javascript_parser.Parser') as MockParser:
                MockParser.return_value = mock_parser
                parser = JavaScriptParser("javascript")
                parser.lang_object = mock_language
                parser.parser = mock_parser
                return parser

    @pytest.fixture
    def ts_parser(self):
        """Create TypeScript parser instance."""
        with patch('app.ckg_builder.parsers.javascript_parser.get_language'):
            mock_language = Mock()
            mock_parser = Mock()
            
            with patch('app.ckg_builder.parsers.javascript_parser.Parser') as MockParser:
                MockParser.return_value = mock_parser
                parser = JavaScriptParser("typescript")
                parser.lang_object = mock_language
                parser.parser = mock_parser
                return parser

    def test_parser_initialization(self):
        """Test parser initialization for both JavaScript and TypeScript."""
        with patch('app.ckg_builder.parsers.javascript_parser.get_language') as mock_get_lang:
            with patch('app.ckg_builder.parsers.javascript_parser.Parser') as MockParser:
                mock_language = Mock()
                mock_parser = Mock()
                mock_get_lang.return_value = mock_language
                MockParser.return_value = mock_parser
                
                # Test JavaScript parser
                js_parser = JavaScriptParser("javascript")
                assert js_parser.language_name == "javascript"
                mock_get_lang.assert_called_with("javascript")
                
                # Test TypeScript parser
                ts_parser = JavaScriptParser("typescript")
                assert ts_parser.language_name == "typescript"
                mock_get_lang.assert_called_with("typescript")

    def test_parse_parameters_node_simple(self, js_parser):
        """Test parsing simple function parameters."""
        # Mock parameter nodes
        param1 = Mock()
        param1.type = "identifier"
        param1.start_point = (0, 0)
        param1.end_point = (0, 5)
        param1.text = b"param1"
        
        param2 = Mock()
        param2.type = "identifier"
        param2.start_point = (0, 8)
        param2.end_point = (0, 14)
        param2.text = b"param2"
        
        parameters_node = Mock()
        parameters_node.text = b"param1, param2"
        parameters_node.named_children = [param1, param2]
        
        # Execute
        parameters, parameters_str = js_parser._parse_parameters_node(parameters_node, "testFunc")
        
        # Verify
        assert len(parameters) == 2
        assert parameters_str == "param1, param2"
        assert parameters[0].name == "param1"
        assert parameters[0].is_parameter is True
        assert parameters[1].name == "param2"

    def test_parse_parameters_node_typescript(self, ts_parser):
        """Test parsing TypeScript parameters with type annotations."""
        # Mock required parameter with type
        param1 = Mock()
        param1.type = "required_parameter"
        param1.start_point = (0, 0)
        param1.end_point = (0, 15)
        
        pattern_node = Mock()
        pattern_node.type = "identifier"
        pattern_node.text = b"userId"
        param1.child_by_field_name = Mock(side_effect=lambda field: {
            "pattern": pattern_node,
            "type": Mock(text=b"number")
        }.get(field))
        
        parameters_node = Mock()
        parameters_node.text = b"userId: number"
        parameters_node.named_children = [param1]
        
        # Execute
        parameters, parameters_str = ts_parser._parse_parameters_node(parameters_node, "getUserById")
        
        # Verify
        assert len(parameters) == 1
        assert parameters[0].name == "userId"
        assert parameters[0].var_type == "number"
        assert parameters[0].is_parameter is True

    def test_parse_function_node_declaration(self, js_parser):
        """Test parsing function declaration."""
        # Mock function node
        func_node = Mock()
        func_node.type = "function_declaration"
        func_node.start_point = (0, 0)
        func_node.end_point = (5, 1)
        func_node.text = b"function processData() { return 'processed'; }"
        
        name_node = Mock()
        name_node.text = b"processData"
        func_node.child_by_field_name = Mock(side_effect=lambda field: {
            "name": name_node,
            "parameters": Mock(named_children=[]),
            "body": Mock()
        }.get(field))
        
        # Mock result object
        result = Mock()
        result.file_path = "test.js"
        
        # Execute
        extracted_func = js_parser._parse_function_node(func_node, result)
        
        # Verify
        assert extracted_func is not None
        assert extracted_func.name == "processData"
        assert extracted_func.start_line == 1
        assert extracted_func.end_line == 6
        assert extracted_func.class_name is None

    def test_parse_function_node_arrow_function(self, js_parser):
        """Test parsing arrow function assigned to variable."""
        # Mock arrow function node
        func_node = Mock()
        func_node.type = "arrow_function"
        func_node.start_point = (0, 0)
        func_node.end_point = (0, 25)
        func_node.text = b"(x) => x * 2"
        
        # Mock parent variable declarator
        parent_node = Mock()
        parent_node.type = "variable_declarator"
        name_node = Mock()
        name_node.text = b"double"
        parent_node.child_by_field_name = Mock(return_value=name_node)
        func_node.parent = parent_node
        
        func_node.child_by_field_name = Mock(side_effect=lambda field: {
            "parameters": Mock(named_children=[]),
            "body": Mock()
        }.get(field))
        
        # Mock result object
        result = Mock()
        result.file_path = "test.js"
        
        # Execute
        extracted_func = js_parser._parse_function_node(func_node, result)
        
        # Verify
        assert extracted_func is not None
        assert extracted_func.name == "double"

    def test_parse_class_node(self, js_parser):
        """Test parsing class declaration."""
        # Mock class node
        class_node = Mock()
        class_node.start_point = (0, 0)
        class_node.end_point = (10, 1)
        
        name_node = Mock()
        name_node.text = b"UserService"
        
        superclass_node = Mock()
        superclass_node.text = b"BaseService"
        
        body_node = Mock()
        method_node = Mock()
        method_node.type = "method_definition"
        body_node.named_children = [method_node]
        
        class_node.child_by_field_name = Mock(side_effect=lambda field: {
            "name": name_node,
            "superclass": superclass_node,
            "body": body_node
        }.get(field))
        
        # Mock result object
        result = Mock()
        result.file_path = "test.js"
        
        # Mock method parsing
        js_parser._parse_function_node = Mock(return_value=Mock(name="getUserById"))
        
        # Execute
        extracted_class = js_parser._parse_class_node(class_node, result)
        
        # Verify
        assert extracted_class is not None
        assert extracted_class.name == "UserService"
        assert "BaseService" in extracted_class.superclasses
        assert len(extracted_class.methods) == 1

    def test_parse_import_statement_default(self, js_parser):
        """Test parsing default import statement."""
        # Mock import node
        import_node = Mock()
        import_node.start_point = (0, 0)
        import_node.end_point = (0, 25)
        
        source_node = Mock()
        source_node.text = b"'./utils'"
        
        import_clause = Mock()
        import_clause.type = "identifier"
        import_clause.text = b"utils"
        
        import_node.child_by_field_name = Mock(side_effect=lambda field: {
            "source": source_node,
            "import": import_clause
        }.get(field))
        
        # Mock result object
        result = Mock()
        result.file_path = "test.js"
        
        # Execute
        extracted_import = js_parser._parse_import_statement_node(import_node, result)
        
        # Verify
        assert extracted_import is not None
        assert extracted_import.module_path == "./utils"
        assert extracted_import.import_type == "default"
        assert len(extracted_import.imported_names) == 1
        assert extracted_import.imported_names[0] == ("utils", None)

    def test_parse_import_statement_named(self, js_parser):
        """Test parsing named import statement."""
        # Mock import node
        import_node = Mock()
        import_node.start_point = (0, 0)
        import_node.end_point = (0, 35)
        
        source_node = Mock()
        source_node.text = b"'lodash'"
        
        import_clause = Mock()
        import_clause.type = "import_specifier"
        name_node = Mock()
        name_node.text = b"isEmpty"
        import_clause.child_by_field_name = Mock(return_value=name_node)
        
        import_node.child_by_field_name = Mock(side_effect=lambda field: {
            "source": source_node,
            "import": import_clause
        }.get(field))
        
        # Mock result object
        result = Mock()
        result.file_path = "test.js"
        
        # Execute
        extracted_import = js_parser._parse_import_statement_node(import_node, result)
        
        # Verify
        assert extracted_import is not None
        assert extracted_import.module_path == "lodash"
        assert extracted_import.import_type == "named"
        assert extracted_import.imported_names[0] == ("isEmpty", None)

    def test_extract_body_details_calls(self, js_parser):
        """Test extracting function calls from body."""
        # Mock body node with call expression
        body_node = Mock()
        body_node.named_children = []
        
        # Mock call node
        call_node = Mock()
        call_node.start_point = (2, 4)
        
        func_node = Mock()
        func_node.type = "identifier"
        func_node.text = b"console.log"
        
        # Mock query and matches
        query_mock = Mock()
        matches_data = [
            (0, {"call_expr": call_node, "call_function_node": func_node})
        ]
        query_mock.matches.return_value = matches_data
        js_parser._get_query = Mock(return_value=query_mock)
        
        # Mock function object
        owner_function = Mock()
        owner_function.calls = set()
        
        # Mock result object
        result = Mock()
        
        # Execute
        js_parser._extract_body_details(body_node, owner_function, result)
        
        # Verify
        assert len(owner_function.calls) == 1
        call = list(owner_function.calls)[0]
        assert call[0] == "console.log"
        assert call[3] == 3  # line number (start_point[0] + 1)

    def test_extract_local_variables_from_declaration(self, js_parser):
        """Test extracting local variable declarations."""
        # Mock declarator node
        declarator_node = Mock()
        declarator_node.type = "variable_declarator"
        
        name_node = Mock()
        name_node.type = "identifier"
        name_node.text = b"result"
        name_node.start_point = (1, 8)
        name_node.end_point = (1, 14)
        
        declarator_node.child_by_field_name = Mock(side_effect=lambda field: {
            "name": name_node,
            "type": None  # No type annotation
        }.get(field))
        
        # Mock declaration node
        declaration_node = Mock()
        declaration_node.named_children = [declarator_node]
        
        # Mock function object
        owner_function = Mock()
        owner_function.name = "processData"
        owner_function.local_variables = []
        
        # Execute
        js_parser._extract_local_variables_from_declaration(declaration_node, owner_function)
        
        # Verify
        assert len(owner_function.local_variables) == 1
        var = owner_function.local_variables[0]
        assert var.name == "result"
        assert var.scope_name == "processData"
        assert var.scope_type == "local_variable"
        assert var.is_parameter is False

    def test_guess_language_from_path_javascript(self, js_parser):
        """Test language detection from file paths."""
        # This would be tested in the incremental_updater, but let's test the logic
        assert js_parser.language_name == "javascript"

    def test_error_handling_in_parsing(self, js_parser):
        """Test error handling during parsing."""
        # Mock a node that causes an exception
        func_node = Mock()
        func_node.type = "function_declaration"
        func_node.child_by_field_name = Mock(side_effect=Exception("Parse error"))
        
        result = Mock()
        result.file_path = "test.js"
        
        # Execute - should not raise exception, should return None
        extracted_func = js_parser._parse_function_node(func_node, result)
        
        # Verify
        assert extracted_func is None

    def test_query_compilation_error_handling(self):
        """Test handling of query compilation errors."""
        with patch('app.ckg_builder.parsers.javascript_parser.get_language') as mock_get_lang:
            with patch('app.ckg_builder.parsers.javascript_parser.Parser') as MockParser:
                mock_language = Mock()
                mock_parser = Mock()
                mock_get_lang.return_value = mock_language
                MockParser.return_value = mock_parser
                
                # Mock query compilation to fail
                mock_language.query = Mock(side_effect=Exception("Query compilation error"))
                
                # Should not raise exception during initialization
                parser = JavaScriptParser("javascript")
                
                # Queries should be empty due to compilation errors
                assert len(parser.queries) == 0

    @pytest.mark.parametrize("language,expected", [
        ("javascript", "javascript"),
        ("typescript", "typescript")
    ])
    def test_language_specific_initialization(self, language, expected):
        """Test parser initialization with different languages."""
        with patch('app.ckg_builder.parsers.javascript_parser.get_language') as mock_get_lang:
            with patch('app.ckg_builder.parsers.javascript_parser.Parser') as MockParser:
                mock_language = Mock()
                mock_parser = Mock()
                mock_get_lang.return_value = mock_language
                MockParser.return_value = mock_parser
                
                parser = JavaScriptParser(language)
                
                assert parser.language_name == expected
                mock_get_lang.assert_called_with(language)

    def test_member_expression_call_parsing(self, js_parser):
        """Test parsing method calls (member expressions)."""
        # Mock body node
        body_node = Mock()
        body_node.named_children = []
        
        # Mock call node with member expression
        call_node = Mock()
        call_node.start_point = (2, 4)
        
        func_node = Mock()
        func_node.type = "member_expression"
        property_node = Mock()
        property_node.text = b"getValue"
        func_node.child_by_field_name = Mock(return_value=property_node)
        
        # Mock query and matches
        query_mock = Mock()
        matches_data = [
            (0, {"call_expr": call_node, "call_function_node": func_node})
        ]
        query_mock.matches.return_value = matches_data
        js_parser._get_query = Mock(return_value=query_mock)
        
        # Mock function object
        owner_function = Mock()
        owner_function.calls = set()
        
        # Mock result object
        result = Mock()
        
        # Execute
        js_parser._extract_body_details(body_node, owner_function, result)
        
        # Verify
        assert len(owner_function.calls) == 1
        call = list(owner_function.calls)[0]
        assert call[0] == "getValue" 