from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
import sqlite3
import datetime
import requests
import os
import db_setup
import pickle
import pandas as pd
from werkzeug.utils import secure_filename
from functools import wraps
import json

# Initialize database if it doesn't exist
if not os.path.exists("health.db"):
    db_setup.setup_database()

# Initialization

app = Flask(__name__)
app.secret_key = "supersecretkey"  
DB_NAME = "health.db"

UPLOAD_FOLDER = os.path.join(app.root_path, "Uploads")
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Load symptoms globally at startup
symptoms = []
try:
    raw_symptoms = pd.read_csv("symptom_list.csv")["Symptom"].tolist()
    # Normalize: lowercase + strip whitespace
    symptoms = [s.strip().lower() for s in raw_symptoms if s and s.strip()]
    if not symptoms:
        print("WARNING: symptom_list.csv is empty")
        symptoms = []
    else:
        print(f"✓ Symptom list loaded: {len(symptoms)} symptoms")
except Exception as e:
    print(f"Error loading symptom list: {e}")
    symptoms = []

# Gemini API configuration - Using REST API directly
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent"

client = None
gemini_available = False

if GEMINI_API_KEY:
    gemini_available = True
    print("✓ Gemini API (REST) configured successfully with valid key")
else:
    print("⚠ No GEMINI_API_KEY found. Using fallback chat responses.")


#  Utility Functions
def get_connection():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database error: {e}")
        raise

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in as admin.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def log_admin_action(admin_id, action):
    """Log admin actions to admin_logs table"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO admin_logs (admin_id, action)
            VALUES (?, ?)
        """, (admin_id, action))
        conn.commit()
    except Exception as e:
        print(f"Error logging admin action: {e}")
    finally:
        conn.close()

# Makes datetime available in all templates
def utility_processor():
    return dict(datetime=datetime)
app.context_processor(utility_processor)


#  File Upload Routes
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload_record', methods=['POST'])
def upload_record():
    """Handle file upload with metadata"""
    if 'patient_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401

    # Check if file is in request
    if 'document_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
    
    file = request.files['document_file']
    description = request.form.get('document_description', '').strip()
    patient_id = session['patient_id']

    # Validate file
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'status': 'error', 'message': 'Invalid file type. Only PDF, JPG, JPEG, PNG allowed'}), 400

    try:
        
        original_filename = secure_filename(file.filename)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"patient{patient_id}_{timestamp}_{original_filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save file to disk
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        file_size_mb = round(file_size / (1024 * 1024), 2)
        
        # Save metadata to database
        conn = get_connection()
        cursor = conn.cursor()
        upload_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO patient_records (patient_id, file_name, description, upload_date)
            VALUES (?, ?, ?, ?)
        """, (patient_id, filename, description if description else original_filename, upload_date))
        
        conn.commit()
        record_id = cursor.lastrowid
        conn.close()

        # Return success response with record details
        return jsonify({
            'status': 'success',
            'message': 'File uploaded successfully',
            'record': {
                'id': record_id,
                'file_name': filename,
                'description': description if description else original_filename,
                'upload_date': upload_date,
                'file_size': f"{file_size_mb} MB",
                'download_url': url_for('uploaded_file', filename=filename, _external=False)
            }
        })
        
    except Exception as e:
        # Clean up file if database insert fails
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'status': 'error', 'message': f'Upload failed: {str(e)}'}), 500

@app.route('/get_records', methods=['GET'])
def get_records():
    """Fetch all records for the logged-in user"""
    if 'patient_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401

    patient_id = session['patient_id']
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT record_id, file_name, description, upload_date
            FROM patient_records
            WHERE patient_id=?
            ORDER BY upload_date DESC
        """, (patient_id,))
        
        records = cursor.fetchall()
        conn.close()

        # Convert records to list of dictionaries
        records_list = []
        for r in records:
            record_dict = {
                'id': r['record_id'],
                'file_name': r['file_name'],
                'description': r['description'] if r['description'] else 'Medical Document',
                'upload_date': r['upload_date'],
                'download_url': url_for('uploaded_file', filename=r['file_name'], _external=False)
            }
            
            # Add file size if file exists
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], r['file_name'])
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                record_dict['file_size'] = f"{round(file_size / (1024 * 1024), 2)} MB"
            
            records_list.append(record_dict)

        return jsonify({
            'status': 'success',
            'records': records_list,
            'total': len(records_list)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to fetch records: {str(e)}'}), 500

@app.route('/delete_record', methods=['POST'])
def delete_record():
    """Delete a record and its associated file"""
    if 'patient_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401

    data = request.get_json()
    record_id = data.get('record_id')
    patient_id = session['patient_id']

    if not record_id:
        return jsonify({'status': 'error', 'message': 'Record ID required'}), 400

    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # First, get the file name and verify ownership
        cursor.execute("""
            SELECT file_name FROM patient_records 
            WHERE record_id=? AND patient_id=?
        """, (record_id, patient_id))
        
        record = cursor.fetchone()
        
        if not record:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Record not found or access denied'}), 404
        
        file_name = record['file_name']
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
        
        # Delete from database
        cursor.execute("DELETE FROM patient_records WHERE record_id=? AND patient_id=?", (record_id, patient_id))
        conn.commit()
        conn.close()
        
        # Delete physical file if it exists
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Warning: Could not delete file {file_path}: {e}")
        
        return jsonify({
            'status': 'success', 
            'message': 'Record deleted successfully',
            'deleted_id': record_id
        })
        
    except Exception as e:
        conn.close()
        return jsonify({'status': 'error', 'message': f'Delete failed: {str(e)}'}), 500

@app.route('/download_record/<int:record_id>')
def download_record(record_id):
    """Download a specific record file"""
    if 'patient_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    patient_id = session['patient_id']
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_name FROM patient_records 
            WHERE record_id=? AND patient_id=?
        """, (record_id, patient_id))
        
        record = cursor.fetchone()
        conn.close()
        
        if not record:
            return jsonify({
                'status': 'error',
                'message': 'Record not found or access denied'
            }), 404
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], record['file_name'])
        
        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({
                'status': 'error',
                'message': 'File not found on server. It may have been deleted.'
            }), 404
        
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 
            record['file_name'],
            as_attachment=True  # Force download
        )
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error downloading file: {str(e)}'
        }), 500

@app.route('/view_record/<int:record_id>')
def view_record(record_id):
    """View a specific record file in browser"""
    if 'patient_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    patient_id = session['patient_id']
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_name FROM patient_records 
            WHERE record_id=? AND patient_id=?
        """, (record_id, patient_id))
        
        record = cursor.fetchone()
        conn.close()
        
        if not record:
            return jsonify({
                'status': 'error',
                'message': 'Record not found or access denied'
            }), 404
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], record['file_name'])
        
        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({
                'status': 'error',
                'message': 'File not found on server. It may have been deleted.'
            }), 404
        
        # Serve the file for viewing (inline display)
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 
            record['file_name'],
            as_attachment=False  # Display in browser instead of download
        )
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error viewing file: {str(e)}'
        }), 500

    
#  Symptom / Recommendations
def fetch_symptoms(symptom_list):
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join(['?']*len(symptom_list))
    cursor.execute(f"""
        SELECT symptom_id, symptom_name, doctor_advice, priority
        FROM symptoms
        WHERE LOWER(symptom_name) IN ({placeholders})
    """, symptom_list)
    results = cursor.fetchall()
    conn.close()

    symptoms_data = [{'id': r['symptom_id'], 'name': r['symptom_name'], 'advice': r['doctor_advice'], 'priority': r['priority']} for r in results]

    if len(symptoms_data) > 3:
        symptoms_data.sort(key=lambda x: x['priority'], reverse=True)
        symptoms_data = symptoms_data[:3]

    final_symptom_ids = [s['id'] for s in symptoms_data]
    return final_symptom_ids, symptoms_data

def fetch_recommendations(symptom_ids):
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join(['?']*len(symptom_ids))
    cursor.execute(f"""
        SELECT DISTINCT R.rec_name, R.rec_type, R.instructions, R.disclaimer
        FROM symptom_recommendation_mapping M
        JOIN recommendations R ON M.rec_id = R.rec_id
        WHERE M.symptom_id IN ({placeholders})
        ORDER BY R.rec_type, R.rec_name
    """, symptom_ids)
    recommendations_list = cursor.fetchall()
    conn.close()
    return recommendations_list

def fetch_recommendations_by_symptom(symptom_name):
    """Fetch recommendations for a specific symptom by name"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.rec_name, r.instructions
        FROM recommendations r
        JOIN symptom_recommendation_mapping m
        ON r.rec_id = m.rec_id
        JOIN symptoms s
        ON s.symptom_id = m.symptom_id
        WHERE LOWER(s.symptom_name) = LOWER(?)
        ORDER BY r.rec_name
    """, (symptom_name,))
    recommendations = cursor.fetchall()
    conn.close()
    return recommendations

def fetch_doctors(symptom_ids):
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join(['?']*len(symptom_ids))
    cursor.execute(f"""
        SELECT DISTINCT S.specialty_id, S.specialty_name
        FROM symptom_specialty_mapping M
        JOIN specialties S ON M.specialty_id = S.specialty_id
        WHERE M.symptom_id IN ({placeholders})
    """, symptom_ids)
    required_specialties = cursor.fetchall()
    specialty_ids = [s['specialty_id'] for s in required_specialties]

    doctors_found = []
    if specialty_ids:
        spec_placeholders = ','.join(['?']*len(specialty_ids))
        cursor.execute(f"""
            SELECT Doctor_ID, Name, rating, experience, availability, specialty_id, biography
            FROM doctor
            WHERE specialty_id IN ({spec_placeholders})
            ORDER BY rating DESC, experience DESC
        """, specialty_ids)
        doctors_found = cursor.fetchall()
    conn.close()
    return required_specialties, doctors_found

def log_history(user_id, symptom_names, recommendations_count, doctors_count):
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.date.today().strftime('%Y-%m-%d')
    symptom_summary = ", ".join([s.title() for s in symptom_names])
    remedy_summary = f"Remedies: {recommendations_count} | Doctors: {doctors_count}"

    try:
        cursor.execute("""
            INSERT INTO health_history (patient_id, symptom_name, remedy_suggested, date_recorded)
            VALUES (?, ?, ?, ?)
        """, (user_id, symptom_summary, remedy_summary, today))
        conn.commit()
    except Exception as e:
        print(f"Flask History Log Error: {e}")
    finally:
        conn.close()


#  General Routes
@app.route("/")
def homepage():
    return render_template("homepage.html") 

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("homepage"))


#  ADMIN ROUTES
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT User_ID, name FROM admin 
            WHERE email=? AND Password=?
        """, (email, password))
        admin = cursor.fetchone()
        conn.close()

        if admin:
            session["admin_id"] = admin["User_ID"]
            session["admin_name"] = admin["name"]
            flash(f"Welcome Admin {admin['name']}!", "success")
            return redirect(url_for("admin_dashboard"))
        
        flash("Invalid email or password.", "danger")
    
    return render_template("admin_login.html")

@app.route("/admin_logout")
def admin_logout():
    session.clear()
    flash("Admin logged out.", "info")
    return redirect(url_for("homepage"))

@app.route("/admin_dashboard")
@admin_required
def admin_dashboard():
    admin_id = session["admin_id"]
    conn = get_connection()
    cursor = conn.cursor()

    # Fetch total counts
    cursor.execute("SELECT COUNT(*) as count FROM patient")
    total_patients = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM doctor")
    total_doctors = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM room")
    total_rooms = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM appointment")
    total_appointments = cursor.fetchone()["count"]

    # Fetch recent appointments
    cursor.execute("""
        SELECT a.App_ID, p.name AS patient_name, d.Name AS doctor_name,
               a.appointment_date, a.Status
        FROM appointment a
        JOIN patient p ON a.Patient_ID = p.Patient_ID
        JOIN doctor d ON a.Doctor_ID = d.Doctor_ID
        ORDER BY a.App_ID DESC LIMIT 5
    """)
    appointments = cursor.fetchall()
    
    # Fetch patients for bill generation dropdown
    cursor.execute("""
        SELECT Patient_ID, name
        FROM patient
    """)
    patients = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        admin_name=session["admin_name"],
        patient_count=total_patients,
        doctor_count=total_doctors,
        room_count=total_rooms,
        appointment_count=total_appointments,
        recent_appointments=appointments,
        patients=patients
    )

@app.route("/patients")
@admin_required
def patients():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch all patients
    cursor.execute("""
        SELECT Patient_ID, name, email, age, gender, medical_info, Room_ID
        FROM patient
        ORDER BY Patient_ID DESC
    """)
    patients_list = cursor.fetchall()
    
    # Fetch available rooms
    cursor.execute("""
        SELECT Room_ID, Room_Type, Status
        FROM room
        WHERE Status='Available'
    """)
    rooms = cursor.fetchall()
    conn.close()

    return render_template("patients.html", patients=patients_list, rooms=rooms)

@app.route("/doctors")
@admin_required
def doctors():

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Doctor_ID, Name, Email, specialty_id, rating, experience, availability
        FROM doctor
        ORDER BY Doctor_ID DESC
    """)
    doctors_list = cursor.fetchall()
    conn.close()

    return render_template("doctors.html", doctors_list=doctors_list)

@app.route("/add_patient", methods=["GET", "POST"])
@admin_required
def add_patient():

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        age = request.form.get("age", "", type=int)
        gender = request.form.get("gender", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        medical_info = request.form.get("medical_info", "").strip()

        if not name or not email or not password:
            flash("Name, email, and password are required.", "danger")
            return redirect(url_for("add_patient"))

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO patient (name, email, password, age, gender, Phone_no, address, medical_info, Admin_ID, created_by_admin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, email, password, age if age else None, gender, phone if phone else None, address, medical_info, session["admin_id"], session["admin_id"]))
            conn.commit()
            log_admin_action(session["admin_id"], f"Added patient: {name}")
            flash(f"Patient {name} added successfully!", "success")
        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()

        return redirect(url_for("patients"))

    return render_template("add_patient.html")

@app.route("/add_doctor", methods=["GET", "POST"])
@admin_required
def add_doctor():

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        specialty_id = request.form.get("specialty_id", type=int)
        experience = request.form.get("experience", type=int)
        rating = request.form.get("rating", type=float)
        contact = request.form.get("contact", "").strip()
        biography = request.form.get("biography", "").strip()

        if not name or not email or not password:
            flash("Name, email, and password are required.", "danger")
            return redirect(url_for("add_doctor"))

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO doctor (Name, Email, password, specialty_id, experience, rating, Contact, biography, Admin_ID, created_by_admin, availability)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Available')
            """, (name, email, password, specialty_id, experience if experience else 0, rating if rating else 0.0, contact if contact else None, biography, session["admin_id"], session["admin_id"]))
            conn.commit()
            log_admin_action(session["admin_id"], f"Added doctor: {name}")
            flash(f"Doctor {name} added successfully!", "success")
        except sqlite3.IntegrityError:
            flash("Email or contact already exists.", "danger")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()

        return redirect(url_for("doctors"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT specialty_id, specialty_name FROM specialties ORDER BY specialty_name")
    specialties = cursor.fetchall()
    conn.close()

    return render_template("add_doctor.html", specialties=specialties)

@app.route("/delete_patient/<int:patient_id>", methods=["POST"])
@admin_required
def delete_patient(patient_id):
    if "admin_id" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, Room_ID FROM patient WHERE Patient_ID=?", (patient_id,))
        patient = cursor.fetchone()
        
        if patient:
            room_id = patient["Room_ID"]
            cursor.execute("DELETE FROM patient WHERE Patient_ID=?", (patient_id,))
            
            if room_id:
                cursor.execute("SELECT COUNT(*) as cnt FROM patient WHERE Room_ID=?", (room_id,))
                cnt = cursor.fetchone()["cnt"]
                cursor.execute("SELECT Capacity FROM room WHERE Room_ID=?", (room_id,))
                cap = cursor.fetchone()["Capacity"]
                status = 'Occupied' if cnt >= cap else 'Available'
                cursor.execute("UPDATE room SET Status=? WHERE Room_ID=?", (status, room_id))
                
            conn.commit()
            log_admin_action(session["admin_id"], f"Deleted patient: {patient['name']}")
            return jsonify({"status": "success", "message": f"Patient deleted"})
        
        return jsonify({"status": "error", "message": "Patient not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@app.route("/delete_doctor/<int:doctor_id>", methods=["POST"])
@admin_required
def delete_doctor(doctor_id):
    if "admin_id" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT Name FROM doctor WHERE Doctor_ID=?", (doctor_id,))
        doctor = cursor.fetchone()
        
        if doctor:
            cursor.execute("DELETE FROM doctor WHERE Doctor_ID=?", (doctor_id,))
            conn.commit()
            log_admin_action(session["admin_id"], f"Deleted doctor: {doctor['Name']}")
            return jsonify({"status": "success", "message": f"Doctor deleted"})
        
        return jsonify({"status": "error", "message": "Doctor not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@app.route("/rooms")
@admin_required
def rooms():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT R.Room_ID, R.Room_Type, R.Status, R.Charges, R.Capacity,
               P.Patient_ID, P.name as patient_name
        FROM room R
        LEFT JOIN patient P ON R.Room_ID = P.Room_ID
        ORDER BY R.Room_ID
    """)
    rooms_list = cursor.fetchall()
    conn.close()

    if not rooms_list:
        flash("No rooms available", "info")

    return render_template("rooms.html", rooms=rooms_list)

@app.route("/api/available_rooms", methods=["GET"])
@admin_required
def get_available_rooms():
    """API endpoint to fetch available rooms in JSON format"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT Room_ID, Room_Type
            FROM room
            WHERE Status = 'Available'
            ORDER BY Room_ID
        """)
        
        rooms_list = cursor.fetchall()
        conn.close()
        
        rooms_data = [
            {'room_id': r['Room_ID'], 'room_type': r['Room_Type']}
            for r in rooms_list
        ]
        
        return jsonify({
            'status': 'success',
            'rooms': rooms_data,
            'total': len(rooms_data)
        }), 200
    
    except Exception as e:
        print(f"Error fetching available rooms: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error fetching rooms: {str(e)}'
        }), 500

@app.route("/api/available_patients", methods=["GET"])
@admin_required
def get_available_patients():
    """API endpoint to fetch all patients for room assignment"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT Patient_ID, name
            FROM patient
            ORDER BY name
        """)
        
        patients_list = cursor.fetchall()
        conn.close()
        
        patients_data = [
            {'patient_id': p['Patient_ID'], 'name': p['name']}
            for p in patients_list
        ]
        
        return jsonify({
            'status': 'success',
            'patients': patients_data,
            'total': len(patients_data)
        }), 200
    
    except Exception as e:
        print(f"Error fetching patients: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error fetching patients: {str(e)}'
        }), 500

@app.route("/assign_room", methods=["POST"])
@admin_required
def assign_room():
    """Assign a room to a patient"""
    if "admin_id" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    try:
        data = request.get_json() if request.is_json else request.form
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        if request.is_json:
            patient_id = int(data.get('patient_id')) if data.get('patient_id') is not None else None
            room_id = int(data.get('room_id')) if data.get('room_id') is not None else None
        else:
            patient_id = request.form.get('patient_id', type=int)
            room_id = request.form.get('room_id', type=int)
        
        if not patient_id or not room_id:
            return jsonify({"status": "error", "message": "Patient ID and Room ID required"}), 400
        
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT Patient_ID, name FROM patient WHERE Patient_ID=?", (patient_id,))
        patient = cursor.fetchone()
        
        if not patient:
            conn.close()
            return jsonify({"status": "error", "message": "Patient not found"}), 404
        
        cursor.execute("SELECT Room_ID, Room_Type, Status, Capacity FROM room WHERE Room_ID=?", (room_id,))
        room = cursor.fetchone()
        
        if not room:
            conn.close()
            return jsonify({"status": "error", "message": "Room not found"}), 404
            
        cursor.execute("SELECT Room_ID FROM patient WHERE Patient_ID=?", (patient_id,))
        old_room_record = cursor.fetchone()
        old_room_id = old_room_record["Room_ID"] if old_room_record else None
        
        # 1. Count current patients in new room
        cursor.execute("SELECT COUNT(*) as current_patients FROM patient WHERE Room_ID=?", (room_id,))
        current_patients = cursor.fetchone()["current_patients"]
        
        # 2 & 3. Compare with room.Capacity
        if current_patients >= room["Capacity"]:
            conn.close()
            return jsonify({"status": "error", "message": "Room Full"}), 400
        
        cursor.execute("""
            UPDATE patient
            SET Room_ID = ?
            WHERE Patient_ID = ?
        """, (room_id, patient_id))
        
        # Update room.Status correctly
        new_status = 'Occupied' if (current_patients + 1) >= room["Capacity"] else 'Available'
        
        cursor.execute("""
            UPDATE room
            SET Status = ?
            WHERE Room_ID = ?
        """, (new_status, room_id))
        
        if old_room_id and old_room_id != room_id:
            cursor.execute("SELECT COUNT(*) as old_cnt FROM patient WHERE Room_ID=?", (old_room_id,))
            old_cnt = cursor.fetchone()["old_cnt"]
            cursor.execute("SELECT Capacity FROM room WHERE Room_ID=?", (old_room_id,))
            old_cap = cursor.fetchone()["Capacity"]
            old_status = 'Occupied' if old_cnt >= old_cap else 'Available'
            cursor.execute("UPDATE room SET Status=? WHERE Room_ID=?", (old_status, old_room_id))
        
        conn.commit()
        conn.close()
        
        log_admin_action(session["admin_id"], f"Assigned room {room_id} ({room['Room_Type']}) to patient {patient['name']}")
        
        if request.is_json:
            return jsonify({
                "status": "success",
                "message": f"Room {room_id} assigned to {patient['name']}",
                "patient_id": patient_id,
                "room_id": room_id
            }), 200
        else:
            flash("Room assigned successfully", "success")
            return redirect(url_for("patients"))
    
    except Exception as e:
        print(f"Error assigning room: {e}")
        if request.is_json:
            return jsonify({"status": "error", "message": f"Error: {str(e)}"}), 500
        else:
            flash(f"Error assigning room: {str(e)}", "danger")
            return redirect(url_for("patients"))

@app.route("/free_room/<int:patient_id>", methods=["POST"])
@admin_required
def free_room(patient_id):
    if "admin_id" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT Room_ID FROM patient WHERE Patient_ID=?", (patient_id,))
        record = cursor.fetchone()
        
        if not record or not record["Room_ID"]:
            return jsonify({"status": "error", "message": "Patient not in a room"}), 400
            
        room_id = record["Room_ID"]
        
        cursor.execute("UPDATE patient SET Room_ID=NULL WHERE Patient_ID=?", (patient_id,))
        
        cursor.execute("SELECT COUNT(*) as cnt FROM patient WHERE Room_ID=?", (room_id,))
        cnt = cursor.fetchone()["cnt"]
        cursor.execute("SELECT Capacity FROM room WHERE Room_ID=?", (room_id,))
        cap = cursor.fetchone()["Capacity"]
        
        status = 'Occupied' if cnt >= cap else 'Available'
        cursor.execute("UPDATE room SET Status=? WHERE Room_ID=?", (status, room_id))
        
        conn.commit()
        
        log_admin_action(session["admin_id"], f"Freed patient {patient_id} from room {room_id}")
        return jsonify({"status": "success", "message": "Patient removed from room successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@app.route("/view_bills")
@admin_required
def view_bills():

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT B.Bill_ID, P.name as patient_name, B.Total_Amount, B.Payment_Mode, B.Bill_date
        FROM bill B
        JOIN patient P ON B.Patient_ID = P.Patient_ID
        ORDER BY B.Bill_date DESC
    """)
    bills = cursor.fetchall()
    
    cursor.execute("""
        SELECT Patient_ID, name
        FROM patient
        ORDER BY name
    """)
    patients = cursor.fetchall()
    
    conn.close()

    return render_template("view_bills.html", bills=bills, patients=patients)

@app.route("/delete_bill/<int:bill_id>", methods=["POST"])
@admin_required
def delete_bill(bill_id):
    if "admin_id" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM bill WHERE Bill_ID=?", (bill_id,))
        conn.commit()
        log_admin_action(session["admin_id"], f"Deleted bill: {bill_id}")
        return jsonify({"status": "success", "message": "Bill deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@app.route("/generate_bill", methods=["GET", "POST"])
@admin_required
def generate_bill():
    """Show bill form (with patients dropdown) and handle bill creation"""
    
    # Always fetch patients for the dropdown (both GET and POST need it)
    conn = get_connection()
    cursor = conn.cursor()
    
    if request.method == "GET":
        # Fetch patients for dropdown
        cursor.execute("""
            SELECT Patient_ID, name
            FROM patient
            ORDER BY name
        """)
        patients = cursor.fetchall()
        conn.close()
        return render_template("generate_bill.html", patients=patients)

    # POST - create bill
    patient_id = request.form.get("patient_id", type=int)
    total_amount = request.form.get("total_amount", type=float)
    payment_mode = request.form.get("payment_mode", "").strip()

    if not patient_id or not total_amount or not payment_mode:
        cursor.execute("""
            SELECT Patient_ID, name
            FROM patient
            ORDER BY name
        """)
        patients = cursor.fetchall()
        conn.close()
        flash("Patient, amount, and payment mode are required.", "danger")
        return render_template("generate_bill.html", patients=patients)

    try:
        cursor.execute("""
            INSERT INTO bill
            (Bill_date, Total_Amount, Payment_Mode, Timings, Patient_ID)
            VALUES (date('now'), ?, ?, time('now'), ?)
        """, (total_amount, payment_mode, patient_id))
        conn.commit()
        log_admin_action(session["admin_id"], f"Generated bill for patient {patient_id}: Rs. {total_amount}")
        flash(f"Bill generated successfully for Rs. {total_amount}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error generating bill: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("view_bills"))

@app.route("/generate_bill_for/<int:patient_id>", methods=["GET", "POST"])
@admin_required
def generate_bill_for(patient_id):
    """Generate bill for a specific patient"""
    if request.method == "POST":
        amount = request.form.get("total_amount", type=float)
        payment_mode = request.form.get("payment_mode", "").strip()

        if not amount or not payment_mode:
            flash("Amount and payment mode are required.", "danger")
            return redirect(url_for("generate_bill_for", patient_id=patient_id))

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO bill (Patient_ID, Total_Amount, Payment_Mode, Bill_date, Timings)
                VALUES (?, ?, ?, date('now'), time('now'))
            """, (patient_id, amount, payment_mode))
            conn.commit()
            
            log_admin_action(session["admin_id"], f"Generated bill for patient {patient_id}: Rs. {amount}")
            flash(f"Bill generated successfully for Rs. {amount}", "success")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()

        return redirect(url_for("view_bills"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM patient WHERE Patient_ID=?", (patient_id,))
    patient = cursor.fetchone()
    
    cursor.execute("""
        SELECT Patient_ID, name
        FROM patient
        ORDER BY name
    """)
    all_patients = cursor.fetchall()
    conn.close()

    return render_template("generate_bill.html", patient=patient, patient_id=patient_id, patients=all_patients)

@app.route("/add_prescription/<int:appointment_id>", methods=["GET", "POST"])
def add_prescription(appointment_id):
    if "doctor_id" not in session:
        flash("Please log in as doctor.", "warning")
        return redirect(url_for("doctor_login"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Doctor_ID FROM appointment WHERE App_ID=?", (appointment_id,))
    appt = cursor.fetchone()
    
    if not appt or appt["Doctor_ID"] != session["doctor_id"]:
        conn.close()
        flash("Unauthorized access. You can only prescribe for your own appointments.", "danger")
        return redirect(url_for("doctor_panel"))

    if request.method == "POST":
        medicine = request.form.get("medicine", "").strip()
        dose = request.form.get("dose", "").strip()
        quantity = request.form.get("quantity", type=int)
        days = request.form.get("days", type=int)

        if not medicine or not dose or not quantity or not days:
            flash("All fields are required.", "danger")
            return redirect(url_for("add_prescription", appointment_id=appointment_id))

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO prescription (App_ID, Medicine, Dose, Quantity, Days)
                VALUES (?, ?, ?, ?, ?)
            """, (appointment_id, medicine, dose, quantity, days))
            conn.commit()
            flash(f"Prescription added successfully!", "success")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()

        return redirect(url_for("doctor_panel"))

    return render_template("add_prescription.html", appointment_id=appointment_id)

@app.route("/view_prescription/<int:appointment_id>")
def view_prescription(appointment_id):
    if "doctor_id" not in session and "patient_id" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("homepage"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Medicine, Dose, Quantity, Days
        FROM prescription
        WHERE App_ID=?
    """, (appointment_id,))
    prescriptions = cursor.fetchall()
    conn.close()

    return render_template("view_prescription.html", prescriptions=prescriptions, appointment_id=appointment_id)

@app.route("/add_prescription", methods=["POST"])
def add_prescription_new():
    """Add new prescription to prescription table"""
    try:
        data = request.get_json()
        print(f"DEBUG Add Prescription Request: {data}")
        
        patient_id = data.get('patient_id')
        doctor_id = data.get('doctor_id')
        diagnosis = data.get('diagnosis', '').strip()
        medicines = data.get('medicines', '').strip()
        notes = data.get('notes', '').strip()
        
        # Validate required fields
        if not patient_id or not doctor_id or not medicines:
            error_data = {
                "status": "error",
                "message": "Patient ID, Doctor ID, and Medicines are required"
            }
            print(f"DEBUG Add Prescription Validation Error: {error_data}")
            return jsonify(error_data), 400
        
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            # Insert into prescription table
            cursor.execute("""
                INSERT INTO prescription (Patient_ID, Doctor_ID, Diagnosis, Medicines, Notes)
                VALUES (?, ?, ?, ?, ?)
            """, (patient_id, doctor_id, diagnosis if diagnosis else None, medicines, notes if notes else None))
            
            conn.commit()
            prescription_id = cursor.lastrowid
            
            response_data = {
                "status": "success",
                "message": "Prescription added successfully",
                "prescription_id": prescription_id
            }
            print(f"DEBUG Add Prescription Success: {response_data}")
            return jsonify(response_data), 201
            
        except sqlite3.IntegrityError as e:
            print(f"Database integrity error: {e}")
            error_data = {
                "status": "error",
                "message": "Invalid patient or doctor ID"
            }
            return jsonify(error_data), 400
        except Exception as e:
            print(f"Database error: {e}")
            error_data = {
                "status": "error",
                "message": f"Error adding prescription: {str(e)}"
            }
            return jsonify(error_data), 500
        finally:
            conn.close()
    
    except Exception as e:
        print(f"Add Prescription Error: {e}")
        error_data = {
            "status": "error",
            "message": "Failed to add prescription"
        }
        return jsonify(error_data), 500

@app.route("/get_prescriptions/<int:patient_id>", methods=["GET"])
def get_prescriptions(patient_id):
    """Get all prescriptions for a patient"""
    try:
        print(f"DEBUG Get Prescriptions Request for patient {patient_id}")
        
        # Verify patient exists and is accessible
        if "patient_id" in session and session["patient_id"] != patient_id:
            # Patients can only view their own prescriptions
            error_data = {
                "status": "error",
                "message": "Access denied"
            }
            return jsonify(error_data), 403
        
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            # Get all prescriptions for the patient
            cursor.execute("""
                SELECT Prescription_ID, Patient_ID, Doctor_ID, Diagnosis, Medicines, Notes, Date_Issued
                FROM prescription
                WHERE Patient_ID = ?
                ORDER BY Date_Issued DESC
            """, (patient_id,))
            
            prescriptions = cursor.fetchall()
            
            # Convert to list of dictionaries
            prescriptions_list = []
            for p in prescriptions:
                prescriptions_list.append({
                    'prescription_id': p['Prescription_ID'],
                    'patient_id': p['Patient_ID'],
                    'doctor_id': p['Doctor_ID'],
                    'diagnosis': p['Diagnosis'],
                    'medicines': p['Medicines'],
                    'notes': p['Notes'],
                    'date_issued': p['Date_Issued']
                })
            
            response_data = {
                "status": "success",
                "prescriptions": prescriptions_list,
                "total": len(prescriptions_list)
            }
            print(f"DEBUG Get Prescriptions Success: Found {len(prescriptions_list)} prescriptions")
            return jsonify(response_data), 200
            
        except Exception as e:
            print(f"Database error: {e}")
            error_data = {
                "status": "error",
                "message": f"Error retrieving prescriptions: {str(e)}"
            }
            return jsonify(error_data), 500
        finally:
            conn.close()
    
    except Exception as e:
        print(f"Get Prescriptions Error: {e}")
        error_data = {
            "status": "error",
            "message": "Failed to retrieve prescriptions"
        }
        return jsonify(error_data), 500


#  Doctor Routes
@app.route("/doctor_login", methods=["GET", "POST"])
def doctor_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        name = request.form.get("name", "").strip()
        action = request.form.get("action")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("doctor_login.html", email=email, name=name)

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT Doctor_ID, Name, password FROM doctor WHERE Email=?", (email,))
        existing_doctor = cursor.fetchone()

        if action == "login":
            if existing_doctor:
                if existing_doctor["password"] == password:
                    session["doctor_id"] = existing_doctor["Doctor_ID"]
                    session["doctor_name"] = existing_doctor["Name"]
                    conn.close()
                    flash(f"Welcome Dr. {existing_doctor['Name']}!", "success")
                    return redirect(url_for("doctor_dashboard"))
                else:
                    flash("Invalid password.", "danger")
            else:
                flash("No account found with this email. Please register.", "warning")
            
            conn.close()
            return render_template("doctor_login.html", email=email, name=name)

        elif action == "register":
            if existing_doctor:
                conn.close()
                flash("An account with this email already exists. Please login.", "warning")
                return render_template("doctor_login.html", email=email, name=name)
            elif not name:
                conn.close()
                flash("Name is required to register.", "warning")
                return render_template("doctor_login.html", email=email, name=name)
            else:
                try:
                    cursor.execute("""
                        INSERT INTO doctor (Name, Email, password, specialty_id, experience, rating, Admin_ID, created_by_admin, availability)
                        VALUES (?, ?, ?, NULL, 0, 0, 1, 1, 'Available')
                    """, (name.title(), email, password))
                    conn.commit()
                    flash("Account created successfully! Please log in to continue.", "success")
                except Exception as e:
                    flash(f"Registration error: {e}", "danger")
                finally:
                    conn.close()
                return redirect(url_for("doctor_login"))

    return render_template("doctor_login.html")

@app.route("/doctor_panel")
def doctor_panel():
    if "doctor_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("doctor_login"))

    doctor_id = session["doctor_id"]
    conn = get_connection()
    cursor = conn.cursor()
    doctor_data = None
    appointments = []
    try:
        cursor.execute("""
            SELECT d.Doctor_ID, d.Name, d.specialty_id, d.biography, s.specialty_name
            FROM doctor d
            LEFT JOIN specialties s ON d.specialty_id = s.specialty_id
            WHERE d.Doctor_ID=?
        """, (doctor_id,))
        doctor_data = cursor.fetchone()
        
        cursor.execute("""
        SELECT A.App_ID, A.Patient_ID, P.name AS patient_name,
               A.appointment_date, A.appointment_time, A.Status, A.reason
        FROM appointment A
        JOIN patient P ON A.Patient_ID = P.Patient_ID
        WHERE A.Doctor_ID = ?
        ORDER BY A.appointment_date DESC, A.appointment_time DESC
    """, (doctor_id,))
        appointments = cursor.fetchall() or []
    except Exception as e:
        print(f"Error fetching doctor panel data: {e}")
        doctor_data = None
        appointments = []
    finally:
        conn.close()

    if not doctor_data:
        flash("Doctor profile not found.", "warning")
        return redirect(url_for("doctor_dashboard"))

    return render_template(
        "doctor_session.html",
        doctor_name=doctor_data["Name"],
        profile_data=doctor_data,
        appointments=appointments if appointments else [],
        active_section="appointments"
    )

@app.route("/doctor_profile")
def doctor_profile():
    if "doctor_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("doctor_login"))

    doctor_id = session["doctor_id"]
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT d.Doctor_ID, d.Name, d.specialty_id, d.biography, s.specialty_name
            FROM doctor d
            LEFT JOIN specialties s ON d.specialty_id = s.specialty_id
            WHERE d.Doctor_ID=?
        """, (doctor_id,))
        doctor_data = cursor.fetchone()
    except Exception as e:
        print(f"Error fetching doctor profile: {e}")
        doctor_data = None
    finally:
        conn.close()

    if not doctor_data:
        flash("Doctor profile not found.", "warning")
        return redirect(url_for("doctor_dashboard"))

    return render_template(
        "doctor_session.html",
        doctor_name=doctor_data["Name"],
        profile_data=doctor_data,
        appointments=[],
        active_section="profile"
    )

@app.route("/update_profile", methods=["POST"])
def update_profile():
    if "doctor_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("doctor_login"))

    doctor_id = session["doctor_id"]
    name = request.form.get("name", "").strip()
    specialty_name = request.form.get("specialty", "").strip()
    biography = request.form.get("biography", "").strip()

    conn = get_connection()
    cursor = conn.cursor()
    
    specialty_id = None
    if specialty_name:
        cursor.execute("SELECT specialty_id FROM specialties WHERE specialty_name COLLATE NOCASE = ?", (specialty_name,))
        row = cursor.fetchone()
        if row:
            specialty_id = row["specialty_id"]

    cursor.execute("""
        UPDATE doctor 
        SET Name=?, specialty_id=?, biography=? 
        WHERE Doctor_ID=?
    """, (name, specialty_id, biography, doctor_id))
    conn.commit()
    conn.close()

    session["doctor_name"] = name
    flash("Profile updated successfully!", "success")
    return redirect(url_for("doctor_profile"))

@app.route("/update_status/<int:appointment_id>/<string:status>", methods=["POST"])
def update_status(appointment_id, status):
    if "doctor_id" not in session:
        return redirect(url_for("doctor_login"))

    if status not in ['Approved', 'Rejected']:
        flash("Invalid status update.", "danger")
        return redirect(url_for("doctor_panel"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE appointment SET Status=? WHERE App_ID=?", (status, appointment_id))
    conn.commit()
    conn.close()

    flash(f"Appointment {appointment_id} {status.lower()} successfully!", "success")
    return redirect(url_for("doctor_panel"))

#  Patient Routes
@app.route("/patient_login_form", methods=["GET", "POST"])
@app.route("/patient_login", methods=["GET", "POST"])
def patient_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        name = request.form.get("name", "").strip()
        action = request.form.get("action")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("patient_login_form.html", email=email, name=name)

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT Patient_ID, name, password FROM patient WHERE email=?", (email,))
        existing_patient = cursor.fetchone()

        if action == "login":
            if existing_patient:
                if existing_patient["password"] == password:
                    session["patient_id"] = existing_patient["Patient_ID"]
                    session["patient_name"] = existing_patient["name"]
                    conn.close()
                    flash(f"Welcome back, {existing_patient['name']}!", "success")
                    return redirect(url_for("patient_dashboard"))
                else:
                    flash("Invalid password.", "danger")
            else:
                flash("No account found with this email. Please register.", "warning")
            
            conn.close()
            return render_template("patient_login_form.html", email=email, name=name)

        elif action == "register":
            if existing_patient:
                conn.close()
                flash("An account with this email already exists. Please log in.", "warning")
                return render_template("patient_login_form.html", email=email, name=name)
            elif not name:
                conn.close()
                flash("Name is required to register.", "warning")
                return render_template("patient_login_form.html", email=email, name=name)
            else:
                try:
                    cursor.execute(
                        "INSERT INTO patient (name, email, password, Admin_ID, created_by_admin) VALUES (?, ?, ?, 1, 1)",
                        (name.title(), email, password)
                    )
                    conn.commit()
                    new_id = cursor.lastrowid
                    session["patient_id"] = new_id
                    session["patient_name"] = name.title()
                    flash(f"Account created successfully! Welcome, {name.title()}!", "success")
                    conn.close()
                    return redirect(url_for("patient_dashboard"))
                except Exception as e:
                    flash(f"Registration failed: {e}", "danger")
                finally:
                    conn.close()
                return render_template("patient_login_form.html", email=email, name=name)

    return render_template("patient_login_form.html")

@app.route("/symptom_analysis", methods=["POST"])
def symptom_analysis():
    if "patient_id" not in session:
        flash("Session expired.", "warning")
        return redirect(url_for("patient_login"))

    symptoms_text_raw = request.form.get("symptoms_input", "").strip()
    if not symptoms_text_raw:
        flash("Please describe your symptoms.", "danger")
        return redirect(url_for("patient_dashboard"))

    symptom_names_lower = [s.strip().lower() for s in symptoms_text_raw.split(',') if s.strip()]
    if not symptom_names_lower:
        flash("No recognizable symptoms entered.", "warning")
        return redirect(url_for("patient_dashboard"))

    final_symptom_ids, symptoms_data = fetch_symptoms(symptom_names_lower)
    if not final_symptom_ids:
        flash("No matching symptoms found in database.", "warning")
        return redirect(url_for("patient_dashboard"))

    recommendations = fetch_recommendations(final_symptom_ids)
    specialties, doctors = fetch_doctors(final_symptom_ids)
    log_history(session["patient_id"], [s['name'] for s in symptoms_data], len(recommendations), len(doctors))

    session["analysis"] = {
    "symptoms_data": symptoms_data,
    "recommendations": [dict(r) for r in recommendations],
    "specialties": [dict(s) for s in specialties],
    "doctors": [dict(d) for d in doctors],
    "symptoms_text": symptoms_text_raw
    }

    # Build specialty name lookup map
    specialty_name_map = {s['specialty_id']: s['specialty_name'] for s in specialties}

    # Convert raw sqlite3.Row doctors to dicts for template
    all_doctors_list = [
        {
            'doctor_id': row['Doctor_ID'],
            'name': row['Name'],
            'specialty': specialty_name_map.get(row['specialty_id'], 'General')
        }
        for row in doctors
    ]

    return render_template(
        "patient_dashboard.html",
        user_name=session.get("patient_name", "Patient"),
        active_section='results',
        symptoms_data=symptoms_data,
        recommendations=recommendations,
        all_doctors=all_doctors_list,
        user_appointments=[],
        selected_doctor_id=None,
        specialties=specialties,
        symptoms_text=symptoms_text_raw,
        show_booking_section=True if doctors else False
    )

@app.route("/patient_dashboard")
def patient_dashboard():
    if "patient_id" not in session:
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for("patient_login"))
    
    patient_id = session["patient_id"]
    conn = get_connection()
    cursor = conn.cursor()
    patient = None
    appointments = []
    records = []

    try:
        # Fetch patient details
        cursor.execute("SELECT * FROM patient WHERE Patient_ID=?", (patient_id,))
        patient = cursor.fetchone()

        if not patient:
            conn.close()
            session.clear()
            flash("Patient record not found. Please log in again.", "warning")
            return redirect(url_for("patient_login"))

        # Fetch appointments for the patient
        cursor.execute("""
            SELECT a.App_ID as appointment_id, d.Name as doctor_name, a.appointment_date, a.appointment_time, 
                   a.Status as status, a.reason 
            FROM appointment a
            JOIN doctor d ON a.Doctor_ID = d.Doctor_ID
            WHERE a.Patient_ID=? 
            ORDER BY a.appointment_date DESC, a.appointment_time DESC
        """, (patient_id,))
        appointments = cursor.fetchall() or []

        # Fetch patient records
        cursor.execute("SELECT * FROM patient_records WHERE patient_id=? ORDER BY upload_date DESC", (patient_id,))
        records = cursor.fetchall() or []
    except Exception as e:
        print(f"Error fetching patient data: {e}")
        flash("Error loading patient dashboard.", "danger")
        appointments = []
        records = []
    finally:
        conn.close()

    conn2 = get_connection()
    cursor2 = conn2.cursor()
    all_doctors = []
    
    try:
        # Fetch all doctors for dropdown
        cursor2.execute("""
            SELECT D.Doctor_ID, D.Name, S.specialty_name
            FROM doctor D
            LEFT JOIN specialties S ON D.specialty_id = S.specialty_id
            WHERE D.Name IS NOT NULL AND D.Name != ''
            ORDER BY D.Name
        """)
        doctors_rows = cursor2.fetchall() or []
        for row in doctors_rows:
            all_doctors.append({
                'doctor_id': row['Doctor_ID'],
                'name': row['Name'],
                'specialty': row['specialty_name'] if row['specialty_name'] else 'General'
            })
    except Exception as e:
        print(f"Error fetching doctors: {e}")
        all_doctors = []
    finally:
        conn2.close()

    return render_template(
        "patient_dashboard.html",
        user_name=session.get("patient_name", "Patient"),
        patient=patient if patient else {},
        appointments=appointments,
        records=records,
        all_doctors=all_doctors,
        user_appointments=appointments,
        selected_doctor_id=None,
        active_section='dashboard'
    )

@app.route("/patient_records")
def view_patient_records():
    """Display all patient records with details"""
    if "patient_id" not in session:
        flash("Please log in to access your records.", "warning")
        return redirect(url_for("patient_login"))
    
    patient_id = session["patient_id"]
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch patient records with patient details
    cursor.execute("""
        SELECT r.record_id,
               r.patient_id,
               r.file_name,
               r.description,
               r.upload_date,
               p.name
        FROM patient_records r
        JOIN patient p
        ON r.patient_id = p.Patient_ID
        WHERE r.patient_id = ?
        ORDER BY r.upload_date DESC
    """, (patient_id,))
    
    records = cursor.fetchall()
    conn.close()
    
    return render_template(
        "patient_records.html",
        records=records,
        patient_name=session.get("patient_name", "Patient")
    )

@app.route("/doctor_dashboard")
def doctor_dashboard():
    if "doctor_id" not in session:
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for("doctor_login"))
    
    doctor_id = session["doctor_id"]
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch doctor appointments
    cursor.execute("""
        SELECT A.App_ID, A.appointment_date, A.appointment_time, A.Status, A.reason, 
               P.name as patient_name, P.Patient_ID
        FROM appointment A
        JOIN patient P ON A.Patient_ID = P.Patient_ID
        WHERE A.Doctor_ID = ?
        ORDER BY A.appointment_date DESC, A.appointment_time DESC
    """, (doctor_id,))
    appointments = cursor.fetchall()
    
    # Get unique patients for this doctor
    cursor.execute("""
        SELECT DISTINCT P.Patient_ID, P.name, P.age, P.gender, P.medical_info, P.email
        FROM patient P
        JOIN appointment A ON P.Patient_ID = A.Patient_ID
        WHERE A.Doctor_ID = ?
        ORDER BY P.name
    """, (doctor_id,))
    patients = cursor.fetchall()
    
    conn.close()
    
    return render_template(
        "doctor_session.html",
        doctor_name=session.get("doctor_name", "Doctor"),
        appointments=appointments,
        patients=patients,
        profile_data=None,
        active_section="appointments"
    )

# Appointment Routes
@app.route("/book_appointment", methods=["GET", "POST"])
def book_appointment():
    if "patient_id" not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("patient_login"))

    user_id = session["patient_id"]
    
    # Handle POST request (form submission)
    if request.method == "POST":
        doctor_id = request.form.get("doctor_id")
        appointment_date = request.form.get("appointment_date")
        appointment_time = request.form.get("appointment_time")
        reason = request.form.get("reason", "").strip()

        if not doctor_id or not appointment_date or not appointment_time:
            flash("All fields except 'Reason' are required.", "danger")
            return redirect(url_for("book_appointment"))

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO appointment (Patient_ID, Doctor_ID, appointment_date, appointment_time, Status, reason)
                VALUES (?, ?, ?, ?, 'Pending', ?)
            """, (user_id, doctor_id, appointment_date, appointment_time, reason))
            conn.commit()
            flash("Appointment request submitted successfully! Await doctor approval.", "success")
        except Exception as e:
            flash(f"Error booking appointment: {e}", "danger")
        finally:
            conn.close()

        return redirect(url_for("book_appointment"))

    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch all doctors  
    cursor.execute("""
        SELECT D.Doctor_ID, D.Name, S.specialty_name
        FROM doctor D
        LEFT JOIN specialties S ON D.specialty_id = S.specialty_id
        WHERE D.Name IS NOT NULL AND D.Name != ''
        ORDER BY D.Name
    """)
    doctors_rows = cursor.fetchall()
    
    # Convert to list of dicts for easier template access
    all_doctors = []
    for row in doctors_rows:
        all_doctors.append({
            'doctor_id': row['Doctor_ID'],
            'name': row['Name'],
            'specialty': row['specialty_name'] if row['specialty_name'] else 'General'
        })
    
    # Fetch user's appointment history 
    cursor.execute("""
        SELECT A.App_ID, D.Name as doctor_name, A.appointment_date, A.appointment_time, 
               A.Status, A.reason
        FROM appointment A
        JOIN doctor D ON A.Doctor_ID = D.Doctor_ID
        WHERE A.Patient_ID = ?
        ORDER BY A.appointment_date DESC, A.appointment_time DESC
    """, (user_id,))
    appointments_rows = cursor.fetchall()
    
    user_appointments = []
    for row in appointments_rows:
        user_appointments.append({
            'appointment_id': row['App_ID'],
            'doctor_name': row['doctor_name'],
            'appointment_date': row['appointment_date'],
            'appointment_time': row['appointment_time'],
            'status': row['Status'],
            'reason': row['reason'] if row['reason'] else ''
        })
    
    conn.close()

    if not all_doctors:
        flash("No doctors available at the moment.", "info")

    return render_template(
        "patient_dashboard.html",
        user_name=session.get("patient_name", "Patient"),
        all_doctors=all_doctors,
        user_appointments=user_appointments,
        active_section='appointments',
        selected_doctor_id = request.args.get("doctor_id", type=int)
    )

@app.route("/patient_appointments")
def patient_appointments():
    return redirect(url_for("book_appointment"))

#Chatbot
@app.route("/chat", methods=["POST"])
def chat():
    """Chat endpoint using Google Generative AI"""
    # Check if patient is logged in
    if "patient_id" not in session:
        return jsonify({"status": "error", "message": "Please log in to use AI Chat"}), 401
    
    try:
        data = request.get_json()
        print(f"DEBUG Chatbot Request: {data}")
        
        user_message = data.get("message", "") if data else ""
        if not user_message:
            error_data = {"status": "error", "message": "Message cannot be empty"}
            print(f"DEBUG Chatbot Response: {error_data}")
            return jsonify(error_data), 400
        
        # Check if Gemini is available
        if not gemini_available:
            print("Gemini unavailable, providing fallback response")
            # Provide fallback response
            fallback_response = (
                "I'm experiencing temporary connectivity issues. "
                "However, I'm a Health Assistant here to help! "
                "You can ask me about symptoms, diseases, remedies, wellness tips, and health advice. "
                "For emergency situations, please contact emergency services immediately. "
                "For accurate diagnosis, please consult a healthcare professional."
            )
            response_data = {
                "status": "success",
                "reply": fallback_response,
                "user_message": user_message,
                "fallback": True
            }
            print(f"DEBUG Chatbot Fallback Response: {response_data}")
            return jsonify(response_data), 200
        
        # System context for health-focused responses
        system_context = (
            "You are a friendly and knowledgeable AI Health Assistant for a Smart Hospital Management System. "
            "You provide helpful information about symptoms, diseases, first aid, nutrition, mental health, and wellness. "
            "Always provide clear, simple, and supportive answers. "
            "If asked about topics unrelated to health, politely redirect the conversation to health topics. "
            "Important: End health-related responses with this disclaimer: "
            "'Note: I'm not a doctor. Please consult a healthcare professional for an accurate diagnosis.'"
        )
        
        # Combine system context with user message
        full_message = f"{system_context}\n\nUser: {user_message}"
        
        # Try to generate response using Gemini with error handling
        try:
            # Call Gemini API using REST request
            headers = {
                "Content-Type": "application/json",
            }
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": full_message
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 1024,
                }
            }
            
            api_url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("candidates") and len(result["candidates"]) > 0:
                    ai_text = result["candidates"][0]["content"]["parts"][0]["text"]
                    
                    response_data = {
                        "status": "success",
                        "reply": ai_text,
                        "user_message": user_message
                    }
                    print(f"DEBUG Chatbot Success Response: {response_data}")
                    return jsonify(response_data), 200
            
            # If response failed, use fallback
            print(f"Gemini API returned status {response.status_code}: {response.text}")
            raise Exception(f"API returned {response.status_code}")
        
        except Exception as api_error:
            error_msg = str(api_error)
            print(f"❌ Gemini API Error: {error_msg}")
            import traceback
            traceback.print_exc()  # Print full error stack trace
            
            # Provide helpful fallback response
            if "API key" in error_msg or "authentication" in error_msg.lower():
                fallback_response = (
                    "❌ AI Chat is currently unavailable due to API configuration issues. "
                    "The system is working in fallback mode. "
                    "I can suggest: rest, hydration, and consulting a healthcare professional for symptoms. "
                    "For emergencies, please call emergency services immediately. "
                    "Note: I'm not a doctor. Please consult a healthcare professional for an accurate diagnosis."
                )
            elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
                fallback_response = (
                    "⚠️ AI Chat service is temporarily overwhelmed. Please try again in a moment. "
                    "Meanwhile, I can suggest: rest, hydration, and consulting a healthcare professional. "
                    "For health emergencies, please contact emergency services immediately. "
                    "Note: I'm not a doctor. Please consult a healthcare professional for an accurate diagnosis."
                )
            else:
                fallback_response = (
                    "⚠️ AI Chat encountered a temporary issue. "
                    "However, I can help with general health suggestions: rest, hydration, and consulting a healthcare professional. "
                    "For emergencies, please call emergency services immediately. "
                    "Note: I'm not a doctor. Please consult a healthcare professional for an accurate diagnosis."
                )
            
            response_data = {
                "status": "success",
                "reply": fallback_response,
                "user_message": user_message,
                "fallback": True
            }
            print(f"DEBUG Chatbot API Error Fallback: {response_data}")
            return jsonify(response_data), 200
    
    except Exception as e:
        print(f"Chatbot Error: {e}")
        # Ensure valid JSON response even on unexpected error
        fallback_response = (
            "I encountered an error processing your request. "
            "However, I can help with health-related questions like symptoms, remedies, and wellness tips. "
            "For emergencies, please call emergency services. "
            "Note: I'm not a doctor. Please consult a healthcare professional for an accurate diagnosis."
        )
        response_data = {
            "status": "success",
            "reply": fallback_response,
            "user_message": data.get("message", "") if data else "",
            "fallback": True,
            "error_note": str(e)
        }
        print(f"DEBUG Chatbot Error Fallback Response: {response_data}")
        return jsonify(response_data), 200

@app.route("/api_chat", methods=["POST"])
def api_chat():
    """Legacy API chat endpoint - redirects to /chat"""
    return chat()


# ML prediction - Load model
try:
    with open("disease_model.pkl", "rb") as f:
        model = pickle.load(f)
    model_loaded = True
    print("✓ Disease model loaded successfully")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None
    model_loaded = False

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()
        print(f"DEBUG Predict Request: {data}")
        
        selected_symptoms = data.get('symptoms', [])
        if not selected_symptoms:
            error_data = {"status": "error", "message": "No symptoms provided"}
            print(f"DEBUG Predict Response: {error_data}")
            return jsonify(error_data), 400
        
        # Check if model is loaded
        if not model_loaded or model is None:
            error_data = {"status": "error", "message": "Prediction model not available"}
            print(f"DEBUG Predict Response: {error_data}")
            return jsonify(error_data), 500
        
        # Normalize incoming symptoms: lowercase + strip
        selected_symptoms_normalized = [s.strip().lower() for s in selected_symptoms if s and s.strip()]
        
        # Use global symptoms list (already normalized)
        # Filter selected symptoms to only those that exist in the global list
        valid_selected_symptoms = [s for s in selected_symptoms_normalized if s in symptoms]
        
        if not valid_selected_symptoms:
            error_data = {"status": "error", "message": "No valid symptoms provided"}
            print(f"DEBUG Predict Response: {error_data}")
            return jsonify(error_data), 400
        
        # Create input vector using global symptoms list
        input_vector = [1 if sym in valid_selected_symptoms else 0 for sym in symptoms]
        
        # Predict using global model
        prediction = model.predict([input_vector])
        result = prediction[0]
        
        # Get confidence if predict_proba is available
        confidence = None
        if hasattr(model, 'predict_proba'):
            try:
                probabilities = model.predict_proba([input_vector])
                confidence = float(max(probabilities[0]))
            except Exception as e:
                print(f"Error calculating confidence: {e}")
                confidence = None
        
        response_data = {
            "status": "success",
            "disease": str(result),
            "confidence": confidence,
            "symptoms_count": len(valid_selected_symptoms)
        }
        print(f"DEBUG Predict Success Response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Prediction error: {e}")
        error_data = {
            "status": "error",
            "disease": "Error predicting disease",
            "message": str(e),
            "confidence": None,
            "symptoms_count": 0
        }
        print(f"DEBUG Predict Error Response: {error_data}")
        return jsonify(error_data), 500

@app.route("/get_symptoms")
def get_symptoms():
    # Return normalized symptom list
    return jsonify(symptoms if symptoms else [])

@app.route("/predictor")
def predictor():
    """Display disease predictor with symptom list"""
    try:
        if symptoms:
            # Use global normalized symptoms list
            symptoms_list = symptoms
        else:
            try:
                # Fallback: load and normalize from CSV
                raw_symptoms = pd.read_csv("symptom_list.csv")["Symptom"].tolist()
                symptoms_list = [s.strip().lower() for s in raw_symptoms if s and s.strip()]
            except Exception as e:
                print(f"Error loading symptoms in predictor: {e}")
                symptoms_list = []
    except Exception as e:
        print(f"Error in predictor route: {e}")
        symptoms_list = []
    
    if not symptoms_list:
        flash("Symptom list unavailable. Please try again later.", "warning")
    
    return render_template("predictor.html", symptoms=symptoms_list)

@app.route("/get_recommendations", methods=["POST"])
def get_recommendations():
    """Get recommendations for a selected symptom and log to health_history"""
    if "patient_id" not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    data = request.get_json()
    symptom_name = data.get('symptom_name', '').strip()
    
    if not symptom_name:
        return jsonify({'status': 'error', 'message': 'Symptom name required'}), 400
    
    try:
        # Fetch recommendations for the symptom
        recommendations = fetch_recommendations_by_symptom(symptom_name)
        
        if not recommendations or len(recommendations) == 0:
            return jsonify({
                'status': 'error',
                'message': f'No recommendations found for symptom: {symptom_name}'
            }), 404
        
        # Log to health_history
        conn = get_connection()
        cursor = conn.cursor()
        
        # Prepare remedy summary from recommendations
        remedy_summary = " | ".join([r['rec_name'] for r in recommendations])
        
        try:
            # Insert into health_history
            cursor.execute("""
                INSERT INTO health_history
                (patient_id, symptom_name, remedy_suggested, date_recorded)
                VALUES (?, ?, ?, datetime('now'))
            """, (session["patient_id"], symptom_name, remedy_summary))
            
            conn.commit()
        except Exception as db_error:
            print(f"Database insert error: {db_error}")
            conn.rollback()
        finally:
            conn.close()
        
        # Convert recommendations to list of dictionaries
        recommendations_list = [
            {
                'rec_name': r['rec_name'], 
                'instructions': r['instructions'] if r['instructions'] else 'No instructions available'
            }
            for r in recommendations
        ]
        
        return jsonify({
            'status': 'success',
            'symptom_name': symptom_name,
            'recommendations': recommendations_list,
            'total': len(recommendations_list)
        }), 200
        
    except Exception as e:
        print(f"Recommendation fetch error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error fetching recommendations: {str(e)}'
        }), 500


# Verify critical files exist at startup
print("\n" + "="*60)
print("SMART HOSPITAL MANAGEMENT SYSTEM - STARTUP CHECK")
print("="*60)

# Check database
if os.path.exists("health.db"):
    print("✓ Database: health.db exists")
else:
    print("! WARNING: health.db not found - will be created on first run")

# Check ML model
if os.path.exists("disease_model.pkl"):
    print("✓ ML Model: disease_model.pkl exists")
else:
    print("! WARNING: disease_model.pkl not found")

# Check symptom list
if os.path.exists("symptom_list.csv"):
    print("✓ Symptoms: symptom_list.csv exists")
else:
    print("! WARNING: symptom_list.csv not found")

# Check uploads folder
if os.path.exists(app.config['UPLOAD_FOLDER']):
    print("✓ Uploads: Folder exists")
else:
    print("! WARNING: Uploads folder not found - creating...")
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Check model loaded
if model_loaded:
    print("✓ ML Model: Loaded successfully")
else:
    print("! WARNING: ML Model failed to load")

# Check symptoms loaded
if symptoms:
    print(f"✓ Symptoms: {len(symptoms)} symptoms loaded")
else:
    print("! WARNING: Symptom list failed to load")

# Check Gemini
if gemini_available:
    print("✓ Gemini API: Connected")
else:
    print("! WARNING: Gemini API not available - chatbot will use fallback")

print("="*60)
print("SYSTEM READY - Starting Flask server on 0.0.0.0:5000")
print("="*60 + "\n")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
