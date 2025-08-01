import sqlite3

db_paths = ["/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/meeting_ops.db", "/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/backend/meeting_sessions.db", "/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/data/meeting_sessions.db"]
for db_path in db_paths:
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        # Try recording_sessions table first
        c.execute("SELECT session_id FROM recording_sessions ORDER BY created_at DESC LIMIT 1")
        latest = c.fetchone()
        if latest:
            session_id = latest[0]
            print(f"DB: {db_path}")
            print(f"Latest session: {session_id}")
            c.execute("SELECT text FROM transcriptions WHERE session_id = (SELECT id FROM recording_sessions WHERE session_id = ?)", (session_id,))
            trans = c.fetchall()
            print("Transcriptions:")
            for t in trans:
                print(t[0] if t[0] else "Empty")
        conn.close()
    except Exception as e:
        print(f"Error in {db_path}: {e}")
