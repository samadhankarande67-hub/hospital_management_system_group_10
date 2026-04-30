import sqlite3

# Run this script separately to check your database
def check_database():
    try:
        # Update this path to your database file
        conn = sqlite3.connect('health.db')  # Change to your DB name
        cursor = conn.cursor()
        
        # Check if Doctors table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='Doctors'
        """)
        table_exists = cursor.fetchone()
        print(f"✓ Doctors table exists: {table_exists is not None}")
        
        if table_exists:
            # Check table structure
            cursor.execute("PRAGMA table_info(Doctors)")
            columns = cursor.fetchall()
            print(f"\n✓ Doctors table columns:")
            for col in columns:
                print(f"  - {col[1]} ({col[2]})")
            
            # Count doctors
            cursor.execute("SELECT COUNT(*) FROM Doctors")
            count = cursor.fetchone()[0]
            print(f"\n✓ Total doctors in database: {count}")
            
            # Show all doctors
            cursor.execute("SELECT * FROM Doctors")
            doctors = cursor.fetchall()
            print(f"\n✓ Doctor records:")
            for doc in doctors:
                print(f"  {doc}")
        
        conn.close()
        
    except Exception as e:
        print(f" ERROR: {e}")

if __name__ == "__main__":
    check_database()
