from tree_sitter_languages import get_language
import tree_sitter

lang = get_language('kotlin')
print('Checking Kotlin node types...')

# Test basic node types
test_queries = [
    '(class_declaration) @class',
    '(interface_declaration) @interface', 
    '(object_declaration) @object',
    '(function_declaration) @function',
    '(property_declaration) @property'
]

for q in test_queries:
    try:
        query = lang.query(q)
        print(f'✅ {q} - VALID')
    except Exception as e:
        print(f'❌ {q} - ERROR: {e}')

print('\nTesting alternative interface node types...')
interface_alternatives = [
    '(interface_type) @interface',
    '(interface_body) @interface',  
    '(type_declaration) @interface',
    '(annotation_set) @interface'
]

for q in interface_alternatives:
    try:
        query = lang.query(q)
        print(f'✅ {q} - VALID')
    except Exception as e:
        print(f'❌ {q} - ERROR: {e}')

print('\nTesting modifier fields...')
modifier_tests = [
    '(function_declaration modifiers: (modifiers) @mods) @func',
    '(function_declaration modifiers: (_) @mods) @func',
    '(modifiers) @mods'
]

for q in modifier_tests:
    try:
        query = lang.query(q)
        print(f'✅ {q} - VALID')
    except Exception as e:
        print(f'❌ {q} - ERROR: {e}') 