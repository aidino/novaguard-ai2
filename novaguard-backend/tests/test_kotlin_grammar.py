#!/usr/bin/env python3

from tree_sitter_languages import get_language, get_parser
from tree_sitter import Node

# Initialize Kotlin language using tree_sitter_languages
kotlin_lang = get_language('kotlin')
parser = get_parser('kotlin')

# Test Kotlin code with interface
kotlin_code = """
package com.example

interface TestInterface {
    fun testMethod()
    val testProperty: String
}

class TestClass : TestInterface {
    override fun testMethod() {
        println("Hello")
    }
    
    override val testProperty = "test"
}
"""

# Parse the code
tree = parser.parse(kotlin_code.encode('utf8'))
root_node = tree.root_node

def print_tree(node: Node, indent: int = 0):
    """Print tree structure with node types."""
    print("  " * indent + f"{node.type} [{node.start_point[0]}:{node.start_point[1]}-{node.end_point[0]}:{node.end_point[1]}]")
    if node.children:
        for child in node.children:
            print_tree(child, indent + 1)

print("Kotlin AST:")
print_tree(root_node)

# Test specific queries
print("\n" + "="*50)
print("Testing queries:")

# Test 1: Check what interface-related node types exist
print("\n1. All possible interface-related nodes:")
try:
    # Try different interface node types
    possible_interface_types = [
        "interface_declaration",
        "interface_definition", 
        "interface_statement",
        "interface_type",
        "interface",
        "class_declaration"  # Maybe interfaces are parsed as classes?
    ]
    
    for interface_type in possible_interface_types:
        try:
            query = kotlin_lang.query(f"({interface_type}) @interface_node")
            captures = query.captures(root_node)
            if captures:
                print(f"  ✅ {interface_type}: Found {len(captures)} matches")
                for capture in captures:
                    node, capture_name = capture
                    print(f"     - {capture_name}: {node.type} at line {node.start_point[0] + 1}")
            else:
                print(f"  ❌ {interface_type}: No matches")
        except Exception as e:
            print(f"  ❌ {interface_type}: Error - {e}")
            
except Exception as e:
    print(f"Query test failed: {e}")

# Test 2: Get all top-level declarations
print("\n2. All top-level declarations:")
try:
    query = kotlin_lang.query("""
        [
          (class_declaration) @class
          (object_declaration) @object
          (function_declaration) @function
          (property_declaration) @property
        ]
    """)
    captures = query.captures(root_node)
    for capture in captures:
        node, capture_name = capture
        print(f"  {capture_name}: {node.type} at line {node.start_point[0] + 1}")
except Exception as e:
    print(f"Top-level query failed: {e}") 