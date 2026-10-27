import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
connection.execute(sys.argv[2])
connection.commit()
connection.close()
