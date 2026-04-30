import sqlite3
import os

DB_NAME = "health.db"

def setup_database():
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print("Old database removed")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON")

    # ================= ADMIN =================
    cursor.execute("""
    CREATE TABLE admin(
        User_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Password TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL COLLATE NOCASE
    )
    """)

    cursor.execute("""
    INSERT INTO admin (Password, name, email)
    VALUES ('admin@123', 'Pranav Kamble', 'admin@hospital.com')
    """)

    # ================= ADMIN LOGS =================
    cursor.execute("""
    CREATE TABLE admin_logs(
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(admin_id) REFERENCES admin(User_ID) ON DELETE CASCADE
    )
    """)

    cursor.executemany("""
    INSERT INTO admin_logs (admin_id, action)
    VALUES (?, ?)
    """, [
    (1, 'Database initialized'),
    (1, 'User created'),
    (1, 'Doctor added')
    ])

    # ================= ROOM =================
    cursor.execute("""
    CREATE TABLE room(
        Room_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Room_Type TEXT,
        Status TEXT CHECK(Status IN ('Available','Occupied')),
        Charges REAL,
        Capacity INTEGER,
        Date_of_admission TEXT,
        Date_of_discharge TEXT
    )
    """)

    cursor.executemany("""
    INSERT INTO room (Room_Type, Status, Charges, Capacity, Date_of_admission, Date_of_discharge)
    VALUES (?, ?, ?, ?, ?, ?)
    """, [
    ('General', 'Available', 1000.00, 4, None, None),
    ('ICU', 'Occupied', 5000.00, 1, '2025-03-01', None),
    ('Private', 'Available', 3000.00, 1, None, None),
    ('Semi-Private', 'Occupied', 2000.00, 2, '2025-03-05', None)
    ])

    # ================= SPECIALTIES =================
    cursor.execute("""
    CREATE TABLE specialties(
        specialty_id INTEGER PRIMARY KEY AUTOINCREMENT,
        specialty_name TEXT UNIQUE,
        description TEXT
    )
    """)

    cursor.executemany("""
    INSERT INTO specialties (specialty_name, description)
    VALUES (?, ?)
    """, [
    ('General Physician (GP)', 'Routine care doctor'),
    ('Otolaryngologist (ENT)', 'Ear, nose, throat specialist'),
    ('Gastroenterologist', 'Digestive system specialist'),
    ('Dermatologist', 'Skin specialist'),
    ('Orthopedic', 'Bone specialist')
    ])

    # ================= PATIENT =================
    cursor.execute("""
    CREATE TABLE patient(
        Patient_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        gender TEXT,
        Phone_no TEXT UNIQUE,
        address TEXT,
        medical_info TEXT,
        Admin_ID INTEGER,
        Room_ID INTEGER,
        email TEXT UNIQUE COLLATE NOCASE,
        password TEXT,
        created_by_admin INTEGER,
        FOREIGN KEY(Admin_ID) REFERENCES admin(User_ID) ON DELETE SET NULL,
        FOREIGN KEY(Room_ID) REFERENCES room(Room_ID) ON DELETE SET NULL,
        FOREIGN KEY(created_by_admin) REFERENCES admin(User_ID)
    )
    """)

    cursor.executemany("""
    INSERT INTO patient (name, age, gender, Phone_no, address, medical_info, Admin_ID, Room_ID, email, password, created_by_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
    ('Cherry Muddamwar', 25, 'Male', '9999999995', 'Pune', 'No major history', 1, 2, 'cherry@gmail.com', 'cherry@123', 1),
    ('Om Navle', 27, 'Male', '8888888822', 'Pune', 'Normal', 1, 4, 'om@gmail.com', 'om@123', 1),
    ('Nilam Devkatte', 29, 'Female', '8888888883', 'Mumbai', 'Allergy', 1, None, 'nilam@gmail.com', 'nilam@123', 1),
    ('Samadhan Karande', 31, 'Male', '8888888884', 'Delhi', 'Healthy', 1, None, 'samadhan@gmail.com', 'samadhan@123', 1),
    ('Janhavi Deshmukh', 33, 'Female', '8888888885', 'Nagpur', 'BP', 1, None, 'janhavi@gmail.com', 'janhavi@123', 1),
    ('Rahul Sharma', 30, 'Male', '9999999992', 'Mumbai', 'Diabetes', 1, None, 'rahul@gmail.com', 'rahul@123', 1),
    ('Priya Patel', 28, 'Female', '9999999993', 'Pune', 'Asthma', 1, None, 'priya@gmail.com', 'priya@123', 1),
    ('Amit Verma', 40, 'Male', '9999999994', 'Delhi', 'High BP', 1, None, 'amit@gmail.com', 'amit@123', 1),
    ('Sneha Joshi', 35, 'Female', '9999999991', 'Nagpur', 'Healthy', 1, None, 'sneha@gmail.com', 'sneha@123', 1),
    ('Vaibhav Murde', 27, 'Male', '8888888882', 'Pune', 'Normal', 1, None, 'Vaibhav@gmail.com', 'vaibhav@123', 1)
    ])

    # ================= DOCTOR =================
    cursor.execute("""
    CREATE TABLE doctor(
        Doctor_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Name TEXT NOT NULL,
        Email TEXT UNIQUE COLLATE NOCASE,
        Contact TEXT UNIQUE,
        Admin_ID INTEGER,
        specialty_id INTEGER,
        rating REAL,
        experience INTEGER,
        location_lat REAL,
        location_lon REAL,
        availability TEXT DEFAULT 'Available',
        password TEXT,
        biography TEXT,
        created_by_admin INTEGER,
        FOREIGN KEY(Admin_ID) REFERENCES admin(User_ID) ON DELETE SET NULL,
        FOREIGN KEY(specialty_id) REFERENCES specialties(specialty_id),
        FOREIGN KEY(created_by_admin) REFERENCES admin(User_ID)
    )
    """)

    cursor.executemany("""
    INSERT INTO doctor (Name, Email, Contact, Admin_ID, specialty_id, rating, experience, location_lat, location_lon, availability, password, biography, created_by_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
    ('Dr. Priya Sharma', 'priya@gmail.com', '1111111111', 1, 1, 4.8, 12, 18.5204, 73.8567, 'Online/10:00-14:00', 'Priya@1234', 'Experienced GP with 12 years', 1),
    ('Dr. Aditya Roy', 'aditya@gmail.com', '2222222222', 1, 2, 4.5, 8, 18.5195, 73.8553, 'Offline/16:00-20:00', 'Aditya@1234', 'ENT specialist with 8 years', 1),
    ('Dr. Sneha Varma', 'sneha@gmail.com', '3333333333', 1, 3, 4.9, 18, 18.522, 73.858, 'Online/11:00-13:00', 'Sneha@1234', 'Senior gastro specialist', 1),
    ('Dr. Rohit Sharma', 'rohit@gmail.com', '4444444444', 1, 1, 4.2, 5, 18.5208, 73.856, 'Offline/17:00-21:00', 'Rohit@1234', 'Young GP', 1),
    ('Dr. Kabir Singh', 'kabir@gmail.com', '5555555555', 1, 2, 4.7, 10, 18.521, 73.857, 'Online/15:00-17:00', 'Kabir@1234', 'ENT expert', 1),
    ('Dr. Preeti Sikka', 'preeti@gmail.com', '6666666666', 1, 5, 4.6, 9, 18.5225, 73.8585, 'Offline/09:00-14:00', 'Preeti@1234', 'Ortho specialist', 1),
    ('Dr. Mahendra Singh Dhoni', 'MSD@gmail.com', '7777777777', 1, 1, 4.8, 12, 18.5204, 73.8567, 'Online/10:00-14:00', 'MSD@1234', 'Experienced GP with 12 years', 1)
    ])

    cursor.execute("CREATE INDEX idx_doctor_specialty ON doctor(specialty_id)")

    # ================= APPOINTMENT =================
    cursor.execute("""
    CREATE TABLE appointment(
        App_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_date TEXT,
        Status TEXT DEFAULT 'Pending',
        Doctor_ID INTEGER NOT NULL,
        Patient_ID INTEGER NOT NULL,
        appointment_time TEXT,
        reason TEXT,
        FOREIGN KEY(Doctor_ID) REFERENCES doctor(Doctor_ID) ON DELETE CASCADE,
        FOREIGN KEY(Patient_ID) REFERENCES patient(Patient_ID) ON DELETE CASCADE
    )
    """)

    cursor.executemany("""
    INSERT INTO appointment (appointment_date, Status, Doctor_ID, Patient_ID, appointment_time, reason)
    VALUES (?, ?, ?, ?, ?, ?)
    """, [
    ('2025-11-15', 'Pending', 1, 1, '11:00:00', 'General Checkup'),
    ('2025-03-02', 'Approved', 2, 2, '11:35:00', ' Dental problem'),
    ('2026-03-29', 'Approved', 1, 6, '11:38:00', 'Chest pain'),
    ('2025-03-01', 'Approved', 1, 1, '11:35:00', 'back pain'),
    ('2025-03-03', 'Approved', 3, 3, '11:35:00', 'severe chest pain')
    ])

    # ================= PRESCRIPTION =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prescription (
        Prescription_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Patient_ID INTEGER NOT NULL,
        Doctor_ID INTEGER NOT NULL,
        Diagnosis TEXT,
        Medicines TEXT,
        Notes TEXT,
        Date_Issued DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (Patient_ID) REFERENCES patient(Patient_ID),
        FOREIGN KEY (Doctor_ID) REFERENCES doctor(Doctor_ID)
    )
    """)

    # ================= BILL =================
    cursor.execute("""
    CREATE TABLE bill(
        Bill_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Bill_date TEXT,
        Total_Amount REAL,
        Payment_Mode TEXT,
        Timings TEXT,
        Patient_ID INTEGER,
        FOREIGN KEY(Patient_ID) REFERENCES patient(Patient_ID) ON DELETE CASCADE
    )
    """)

    cursor.executemany("""
    INSERT INTO bill (Bill_date, Total_Amount, Payment_Mode, Timings, Patient_ID)
    VALUES (?, ?, ?, ?, ?)
    """, [
    ('2025-03-02', 5000.00, 'Cash', '10:30:00', 1),
    ('2025-03-06', 3000.00, 'Card', '14:00:00', 2),
    ('2025-03-10', 2000.00, 'UPI', '11:15:00', 3),
    ('2025-03-12', 4500.00, 'Cash', '09:45:00', 4),
    ('2025-03-15', 3500.00, 'Card', '16:20:00', 5)
    ])

    cursor.execute("CREATE INDEX idx_bill_patient ON bill(Patient_ID)")

    # ================= HEALTH HISTORY =================
    cursor.execute("""
    CREATE TABLE health_history(
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        symptom_name TEXT,
        remedy_suggested TEXT,
        date_recorded TEXT,
        FOREIGN KEY(patient_id) REFERENCES patient(Patient_ID) ON DELETE CASCADE
    )
    """)

    cursor.executemany("""
    INSERT INTO health_history (patient_id, symptom_name, remedy_suggested, date_recorded)
    VALUES (?, ?, ?, ?)
    """, [
    (1, 'headache', 'Rest and hydration', '2025-01-15 00:00:00'),
    (2, 'cough', 'Cough syrup', '2025-01-16 00:00:00'),
    (3, 'fever', 'Paracetamol', '2025-01-17 00:00:00'),
    (4, 'joint pain', 'Rest', '2025-01-18 00:00:00'),
    (5, 'acidity', 'Light diet', '2025-01-19 00:00:00')
    ])

    # ================= PATIENT RECORDS =================
    cursor.execute("""
    CREATE TABLE patient_records(
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        file_name TEXT,
        description TEXT,
        upload_date TEXT,
        FOREIGN KEY(patient_id) REFERENCES patient(Patient_ID) ON DELETE CASCADE
    )
    """)

    cursor.executemany("""
    INSERT INTO patient_records (patient_id, file_name, description, upload_date)
    VALUES (?, ?, ?, ?)
    """, [
    (1, 'scan_2025_01_15.pdf', 'CT Scan report', '2025-01-15 10:00:00'),
    (2, 'blood_test_2025_01_16.pdf', 'Blood test results', '2025-01-16 11:00:00'),
    (3, 'xray_2025_01_17.pdf', 'Chest X-ray report', '2025-01-17 09:30:00'),
    (4, 'ultrasound_2025_01_18.pdf', 'Ultrasound results', '2025-01-18 14:00:00'),
    (5, 'report_2025_01_19.pdf', 'Medical report', '2025-01-19 15:30:00'),
    (6, 'test_2025_01_20.pdf', 'Lab test', '2025-01-20 10:15:00')
    ])

    # ================= SYMPTOMS =================
    cursor.execute("""
    CREATE TABLE symptoms(
        symptom_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symptom_name TEXT,
        description TEXT,
        doctor_advice TEXT,
        priority INTEGER
    )
    """)

    cursor.executemany("""
    INSERT INTO symptoms (symptom_name, description, doctor_advice, priority)
    VALUES (?, ?, ?, ?)
    """, [
    ('headache', 'Pain or discomfort in the head or face.', 'Seek immediate help if headache is sudden and severe, accompanied by a stiff neck, confusion, or loss of consciousness.', 2),
    ('cough', 'A reflex action to clear your airways of mucus and irritants.', 'See a doctor if cough persists for more than 7 days, or is accompanied by blood or difficulty breathing.', 1),
    ('acidity', 'A burning sensation in the chest, also known as heartburn.', 'Consult a doctor if symptoms occur more than twice a week, or if pain spreads to your arm or jaw.', 1),
    ('fever', 'An increase in body temperature above the normal range (98.6°F / 37°C).', 'Seek medical attention if fever exceeds 103°F (39.4°C), or lasts longer than 3 days.', 3),
    ('joint pain', 'Discomfort, aches, and soreness in any of the body''s joints.', 'Consult a doctor if the joint pain is severe, accompanied by swelling or redness.', 2)
    ])

    # ================= RECOMMENDATIONS =================
    cursor.execute("""
    CREATE TABLE recommendations(
        rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rec_name TEXT,
        rec_type TEXT,
        instructions TEXT,
        disclaimer TEXT
    )
    """)

    cursor.executemany("""
    INSERT INTO recommendations (rec_name, rec_type, instructions, disclaimer)
    VALUES (?, ?, ?, ?)
    """, [
    ('Ginger Tea', 'Home Remedy', 'Boil fresh ginger slices in water for 10 minutes. Strain and drink warm.', 'Avoid if you have a bleeding disorder.'),
    ('Stay Hydrated', 'Dietary', 'Drink at least 8-10 glasses of water throughout the day.', None),
    ('Paracetamol', 'Tablet', 'Take one 500mg tablet. Do not exceed 4 tablets in 24 hours.', 'Consult a doctor if symptoms persist.'),
    ('Honey and Lemon', 'Home Remedy', 'Mix one tablespoon of honey and a few drops of lemon juice in warm water and sip slowly.', 'Do not give honey to children under 1 year old.'),
    ('Avipattikar Churna', 'Ayurvedic', 'Take 1-2 teaspoons with lukewarm water before meals.', 'Consult an Ayurvedic practitioner before use.'),
    ('Cold Milk', 'Dietary', 'Drink a glass of cold, plain milk to get instant relief from burning sensation.', 'Avoid if you are lactose intolerant.'),
    ('Tepid Sponge Bath', 'Home Remedy', 'Wipe the body with lukewarm water for cooling.', 'Avoid ice-cold water, as it can cause shivering.'),
    ('Rest and Ice', 'Home Remedy', 'Rest the affected joint and apply a cold pack for 15-20 minutes, 3 times a day.', 'Do not apply ice directly to the skin.'),
    ('Naproxen', 'Tablet', 'Take one 250mg tablet every 8 hours.', 'Consult a doctor if you have stomach problems or heart disease.'),
    ('Turmeric Milk', 'Dietary', 'Mix 1 teaspoon of turmeric powder in warm milk and drink before bed.', 'N/A')
    ])

    # ================= SYMPTOM SPECIALTY MAPPING =================
    cursor.execute("""
    CREATE TABLE symptom_specialty_mapping(
        map_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symptom_id INTEGER,
        specialty_id INTEGER,
        FOREIGN KEY(symptom_id) REFERENCES symptoms(symptom_id),
        FOREIGN KEY(specialty_id) REFERENCES specialties(specialty_id)
    )
    """)

    cursor.executemany("""
    INSERT INTO symptom_specialty_mapping (symptom_id, specialty_id)
    VALUES (?, ?)
    """, [
    (1, 1),
    (2, 2),
    (2, 1),
    (3, 3),
    (4, 1),
    (5, 1),
    (5, 5)
    ])

    # ================= SYMPTOM RECOMMENDATION MAPPING =================
    cursor.execute("""
    CREATE TABLE symptom_recommendation_mapping(
        mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symptom_id INTEGER,
        rec_id INTEGER,
        FOREIGN KEY(symptom_id) REFERENCES symptoms(symptom_id) ON DELETE CASCADE,
        FOREIGN KEY(rec_id) REFERENCES recommendations(rec_id) ON DELETE CASCADE
    )
    """)

    cursor.executemany("""
    INSERT INTO symptom_recommendation_mapping (symptom_id, rec_id)
    VALUES (?, ?)
    """, [
    (1, 1),
    (1, 2),
    (1, 3),
    (2, 1),
    (2, 4),
    (3, 5),
    (3, 6),
    (4, 3),
    (4, 7),
    (4, 10),
    (5, 8),
    (5, 9),
    (5, 10)
    ])

    # ================= PERFORMANCE INDEXES =================
    cursor.execute("CREATE INDEX idx_patient_admin ON patient(Admin_ID)")
    cursor.execute("CREATE INDEX idx_patient_room ON patient(Room_ID)")
    cursor.execute("CREATE INDEX idx_appointment_patient ON appointment(Patient_ID)")
    cursor.execute("CREATE INDEX idx_appointment_doctor ON appointment(Doctor_ID)")
    cursor.execute("CREATE INDEX idx_records_patient ON patient_records(patient_id)")

    conn.commit()
    conn.close()

    print("FULL DATABASE CREATED SUCCESSFULLY")

if __name__ == "__main__":
    setup_database() 