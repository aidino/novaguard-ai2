#!/usr/bin/env python3

from app.ckg_builder.parsers import get_code_parser

def test_all_parsers():
    """Test all available parsers."""
    
    print("🧪 Testing All Code Parsers")
    print("=" * 50)
    
    # Test Kotlin Parser
    print("\n1. Testing Kotlin Parser...")
    kotlin_parser = get_code_parser("kotlin")
    if kotlin_parser:
        kotlin_code = '''
interface TestInterface {
    fun testMethod()
}

class TestClass : TestInterface {
    override fun testMethod() {
        println("Hello")
    }
}
'''
        result = kotlin_parser.parse(kotlin_code, 'test.kt')
        print(f"   ✅ Kotlin: {len(result.classes)} classes, {len(result.functions)} functions")
    else:
        print("   ❌ Kotlin parser not available")
    
    # Test C Parser
    print("\n2. Testing C Parser...")
    c_parser = get_code_parser("c")
    if c_parser:
        c_code = '''
#include <stdio.h>

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    return a + b;
}
'''
        result = c_parser.parse(c_code, 'test.c')
        print(f"   ✅ C: {len(result.classes)} structs, {len(result.functions)} functions, {len(result.imports)} includes")
    else:
        print("   ❌ C parser not available")
    
    # Test Java Parser
    print("\n3. Testing Java Parser...")
    java_parser = get_code_parser("java")
    if java_parser:
        print("   ✅ Java parser available")
    else:
        print("   ❌ Java parser not available")
    
    # Test Python Parser
    print("\n4. Testing Python Parser...")
    python_parser = get_code_parser("python")
    if python_parser:
        print("   ✅ Python parser available")
    else:
        print("   ⚠️  Python parser not yet implemented in new structure")
    
    print("\n" + "=" * 50)
    print("✅ Parser testing completed!")

if __name__ == "__main__":
    test_all_parsers() 