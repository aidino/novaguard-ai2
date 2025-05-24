#!/usr/bin/env python3

from app.ckg_builder.parsers.kotlin_parser import KotlinParser

def test_kotlin_parser():
    parser = KotlinParser()
    print('✅ Kotlin parser instantiated successfully:', type(parser).__name__)

    # Test parsing a simple Kotlin interface
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

    result = parser.parse(kotlin_code, 'test.kt')
    print('✅ Parsing completed')
    print(f'Classes found: {len(result.classes)}')
    for cls in result.classes:
        print(f'  - {cls.name} (decorators: {cls.decorators})')
    
    print(f'Functions found: {len(result.functions)}')
    for func in result.functions:
        print(f'  - {func.name} (class: {func.class_name})')

if __name__ == "__main__":
    test_kotlin_parser() 