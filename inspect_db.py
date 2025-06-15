import sqlite3

# Connect to the SQLite database
db = sqlite3.connect("zoral_npc.sqlite")
cursor = db.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:", tables)

# Print schema for each expected table
for table in ['zoral_memories', 'zoral_traits', 'zoral_interactions']:
    cursor.execute(f"PRAGMA table_info({table});")
    schema = cursor.fetchall()
    print(f"Schema for {table}:", schema)

# Close the connection
db.close()
