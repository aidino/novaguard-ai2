#!/usr/bin/env python3

from app.ckg_builder.parsers import get_code_parser

def test_c_parser():
    parser = get_code_parser("c")
    print('✅ C parser instantiated successfully:', type(parser).__name__)

    # Test parsing a simple C file
    c_code = '''
#include <stdio.h>
#include "myheader.h"

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    return a + b;
}

void main() {
    struct Point p = {10, 20};
    int result = add(p.x, p.y);
    printf("Result: %d\\n", result);
}
'''

    result = parser.parse(c_code, 'test.c')
    print('✅ Parsing completed')
    print(f'Structs found: {len(result.classes)}')
    for i, cls in enumerate(result.classes):
        print(f'  {i+1}. {cls.name} (decorators: {cls.decorators})')
        print(f'     Fields: {len(cls.attributes)}')
        for j, attr in enumerate(cls.attributes):
            print(f'       {j+1}. {attr.name}: {attr.var_type}')
    
    print(f'Functions found: {len(result.functions)}')
    for i, func in enumerate(result.functions):
        print(f'  {i+1}. {func.name}')
        print(f'     Parameters: {len(func.parameters)}')
        for j, param in enumerate(func.parameters):
            print(f'       {j+1}. {param.name}: {param.var_type}')
    
    print(f'Includes found: {len(result.imports)}')
    for i, imp in enumerate(result.imports):
        print(f'  {i+1}. {imp.module_path}')

if __name__ == "__main__":
    test_c_parser() 