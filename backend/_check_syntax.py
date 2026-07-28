import ast
files = [
    'routers/auth.py',
    'routers/schedules.py',
    'schemas.py',
    'models.py',
    'main.py',
]
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print(f'{f} OK')
    except SyntaxError as e:
        print(f'{f} ERROR: {e}')