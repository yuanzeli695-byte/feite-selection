import sys

import openpyxl
import PIL

if "--versions" in sys.argv[1:]:
    print(openpyxl.__version__, PIL.__version__, sep="/")
