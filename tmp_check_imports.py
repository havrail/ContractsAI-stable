import importlib
modules = [
    'src_python.database',
    'src_python.models',
    'src_python.utils',
    'src_python.pipeline',
    'src_python.llm_client'
]
for m in modules:
    try:
        importlib.import_module(m)
        print(f"{m} imported OK")
    except Exception as e:
        print(f"{m} import error: {e}")
