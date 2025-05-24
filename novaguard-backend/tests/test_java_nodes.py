from tree_sitter_languages import get_language
import tree_sitter

lang = get_language('java')
print('Checking Java node types and fields...')

# Test basic queries without field constraints
basic_tests = [
    '(class_declaration) @class',
    '(interface_declaration) @interface',
    '(type_list) @type_list'
]

for q in basic_tests:
    try:
        query = lang.query(q)
        print(f'✅ {q} - VALID')
    except Exception as e:
        print(f'❌ {q} - ERROR: {e}')

print('\nTesting alternative field names for interface extends...')
interface_extends_tests = [
    '(interface_declaration (type_list) @extended) @interface',
    '(interface_declaration super_interfaces: (type_list) @extended) @interface',
    '(interface_declaration extends: (type_list) @extended) @interface'
]

for q in interface_extends_tests:
    try:
        query = lang.query(q)
        print(f'✅ {q} - VALID')
    except Exception as e:
        print(f'❌ {q} - ERROR: {e}')

# Test inheritance query components
inheritance_tests = [
    '(class_declaration superclass: (type_identifier) @superclass) @class',
    '(class_declaration interfaces: (type_list) @interfaces) @class',
    '(interface_declaration extends_interfaces: (type_list) @extended) @interface',
    '(interface_declaration super_interfaces: (type_list) @extended) @interface',
    '(interface_declaration) @interface'
]

for q in inheritance_tests:
    try:
        query = lang.query(q)
        print(f'✅ {q} - VALID')
    except Exception as e:
        print(f'❌ {q} - ERROR: {e}') 