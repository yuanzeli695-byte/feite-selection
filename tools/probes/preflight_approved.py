import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location(sys.argv[1], sys.argv[2])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({key: value[1] for key, value in module.APPROVED_SCRIPTS.items()}))
