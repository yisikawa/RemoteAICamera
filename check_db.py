import sqlite3
conn = sqlite3.connect('data/events.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM detection_events')
count = cursor.fetchone()[0]
print(f'Total events: {count}')
conn.close()
