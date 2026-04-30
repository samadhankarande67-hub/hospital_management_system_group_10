# Deep Technical Analysis Report: Smart Hospital Management System

This is a strict structural breakdown and state assessment of the codebase as requested.

---

## 1. ROUTE MAP

| Route | Method | Frontend Attached | Purpose |
| :--- | :--- | :--- | :--- |
| **Authentication Routes** |
| `/` | GET | `homepage.html` | Base landing page |
| `/login_options` | GET | `login.html` | General login nav |
| `/admin_login` | GET/POST | `admin_login.html` | Administrative access |
| `/doctor_login` | GET/POST | `doctor_login.html` | Doctor access & registration |
| `/patient_login_form` | GET/POST| `patient_login_form.html`| Patient access & registration |
| `/logout`, `/admin_logout` | GET | Redirects to `/` | Kills active sessions |
| **Admin Operations** |
| `/admin_dashboard` | GET | `admin_dashboard.html` | Admin statistics view |
| `/patients` | GET | `patients.html` | Lists all patients & rooms |
| `/add_patient` | GET/POST | `add_patient.html` | Form inserting admin patients |
| `/delete_patient/<id>` | POST | API Response | Removes patient record |
| `/doctors` | GET | `doctors.html` | Lists all doctors |
| `/add_doctor` | GET/POST | `add_doctor.html` | Form inserting doctors |
| `/delete_doctor/<id>` | POST | API Response | Removes doctor record |
| `/rooms` | GET | `rooms.html` | Room capacity & mapping |
| `/assign_room` | POST | API Response | Updates patient Room_ID |
| `/free_room/<id>` | POST | API Response | Detaches Room_ID mapping |
| `/view_bills` | GET | `view_bills.html` | Past invoice ledger |
| `/generate_bill` | GET/POST | `generate_bill.html` | Generic invoice generator |
| `/generate_bill_for/<id>` | GET/POST | `generate_bill.html` | Specific user invoice generator |
| **Doctor Operations** |
| `/doctor_dashboard` | GET | `doctor_session.html` | Default broken dashboard route |
| `/doctor_panel` | GET | `doctor_session.html` | Appointment request viewer |
| `/doctor_profile` | GET | `doctor_session.html` | Biography info viewer |
| `/update_profile` | POST | Redirect to `/doctor_profile` | Modifies biography |
| `/update_status/<id>/<status>`| POST | Redirect to `/doctor_panel` | Approves/rejects appointments |
| `/add_prescription/<id>` | GET/POST | `add_prescription.html` | Prescribes medicine to appointment |
| `/view_prescription/<id>` | GET | `view_prescription.html` | View generated prescription list |
| **Patient Operations** |
| `/patient_dashboard` | GET | `patient_dashboard.html` | Patient central hub |
| `/book_appointment` | GET/POST| `patient_dashboard.html` | Requesting new appointments |
| `/patient_appointments` | GET | Redirect to `/book_appointment`| Alias route |
| `/patient_records` | GET | `patient_records.html` | Displays uploads exclusively |
| `/symptom_analysis` | POST | `patient_dashboard.html` | Executes symptom pattern checks |
| **File Management** |
| `/upload_record` | POST | API JSON Response | File ingestion layer |
| `/get_records` | GET | API JSON Response | JSON formatting of records |
| `/download_record/<id>` | GET | File Downloader | Attachment retrieval |
| `/view_record/<id>` | GET | Inline View | Serve static attachment inline |
| `/delete_record` | POST | API JSON Response | Database and disk delete |
| `/uploads/<filename>` | GET | Static Send | File pathway distributor |
| **API / ML Integrations** |
| `/chat`, `/api_chat` | POST | API JSON Response | Gemini Chatbot gateway |
| `/predict` | POST | API JSON Response | SciKit Learn unpickle execution |
| `/predictor` | GET | `predictor.html` | Standalone UI for prediction |
| `/get_symptoms` | GET | API JSON Response | Retreives symptom CSV strings |
| `/get_recommendations` | POST | API JSON Response | SQLite mapping lookup tool |

---

## 2. DATABASE STRUCTURE

*   **`admin`**: Primary key `User_ID`. Stores admin users.
*   **`admin_logs`**: Primary key `log_id`. Retains audit trails.
    *   `admin_id` → FK `admin(User_ID)` [ON DELETE CASCADE]
*   **`room`**: Primary key `Room_ID`. Tracks capacity and current status mapping.
*   **`specialties`**: Primary key `specialty_id`. Dictionary of medical domains.
*   **`patient`**: Primary key `Patient_ID`. Central user entity.
    *   `Admin_ID` & `created_by_admin` → FK `admin(User_ID)` [ON DELETE SET NULL]
    *   `Room_ID` → FK `room(Room_ID)` [ON DELETE SET NULL]
*   **`doctor`**: Primary key `Doctor_ID`. Central doctor provider entity.
    *   `specialty_id` → FK `specialties` [No explicit delete rule]
    *   `Admin_ID` & `created_by_admin` → FK `admin` [ON DELETE SET NULL]
*   **`appointment`**: Primary key `App_ID`. Links schedules and logic.
    *   `Doctor_ID` → FK `doctor(Doctor_ID)` [ON DELETE CASCADE]
    *   `Patient_ID` → FK `patient(Patient_ID)` [ON DELETE CASCADE]
*   **`prescription`**: Primary composite key (`App_ID`, `Medicine`). Links meds.
    *   `App_ID` → FK `appointment(App_ID)` [ON DELETE CASCADE]
*   **`bill`**: Primary key `Bill_ID`. Ledger of charges.
    *   `Patient_ID` → FK `patient` [ON DELETE CASCADE]
*   **`health_history`**: Primary key `history_id`. Logbook of condition inquiries.
    *   `patient_id` → FK `patient` [ON DELETE CASCADE]
*   **`patient_records`**: Primary key `record_id`. Pointer for file attachments.
    *   `patient_id` → FK `patient` [ON DELETE CASCADE]
*   **`symptoms`**: Primary key `symptom_id`.
*   **`recommendations`**: Primary key `rec_id`.
*   **`symptom_specialty_mapping`**: Primary key `map_id`.
    *   `symptom_id` & `specialty_id` → FK mapped respectively [No explicit delete rule]
*   **`symptom_recommendation_mapping`**: Primary key `mapping_id`.
    *   `symptom_id` & `rec_id` → FK mapped respectively [ON DELETE CASCADE]

**(Noted Missing Relationship Checks:)** Deleting a user row (patient) safely cascades down their history/bills but fails to send update commands to modify dependencies logically disconnected through FK mapping constraints (like room thresholds).

---

## 3. MODULE STATUS

| Module | ✔ Working Parts | ❌ Broken Parts | ⚠ Risk Areas |
| :--- | :--- | :--- | :--- |
| **Auth** | DB integration, session setups, safe logging out | None natively broken | Clear text passwords stored in DB. No protection against CSRF tokens. |
| **Patient** | User data fetching, file management routes, login pages | Doesn't clear tied Room records out on patient deletion | Implicit missing UNIQUE constraints because `Phone_no` resolves to NULL automatically during signup. |
| **Doctor** | Profile fetches, Appt. management flow is robust | Doctor dashboard triggers a totally blank UI view bug globally | Bio update allows text overwrite but avoids sanitization. |
| **Room** | Admin allocation tools work for first time placement | `assign_room` leaks old rooms. `free_room` evicts entire wards | Direct database modification lacking a locking mechanism leading to potential collision |
| **Billing** | Display mapping tables and PDF relationships. | None directly broken | Bypasses room charges automatically. Modifies amounts without validation strings. |
| **Prediction** | Vectors unpickle efficiently, JSON parses quickly | None broken | Hardcoded dependency on column ordering from the local csv file strings. |
| **Chatbot** | Fully integrated API connections. Error fallbacks work | None broken | API connection keys are exposed within the scripts plain-text boundaries. |

---

## 4. EXACT BUG ROOT CAUSES

1.  **Room Overwrite Leak**
    *   **File Name**: `app.py`
    *   **Function Name**: `assign_room()`
    *   **Exact Reason**: When migrating an existing patient (`Patient_ID`) to a new `Room_ID`, the database logic strictly checks and increments the target room limit, modifies the patient reference to the target room, but does not identify the patient's existing `Room_ID`. Because the prior room isn't touched, it maintains its previous `Status='Occupied'` perpetually as a ghost room.

2.  **Free Room Nuclear Eviction**
    *   **File Name**: `app.py`
    *   **Function Name**: `free_room(room_id)`
    *   **Exact Reason**: It runs `UPDATE patient SET Room_ID=NULL WHERE Room_ID=?`. While 'Private' single rooms are fine, running this on a 'General' room containing 4 legitimate patients will instantly rip the allocation from all 4 people at the exact same time rather than unassigning a specific targeted ID safely.

3.  **Deleted Patient Room Freeze**
    *   **File Name**: `app.py`
    *   **Function Name**: `delete_patient(patient_id)`
    *   **Exact Reason**: Deleting a patient securely removes their data dependencies (`bill`, `appointment`) using `ON DELETE CASCADE`. However, it leaves `room` structures behind. Because the patient is forcefully omitted, the room capacity never falls back down, and so `Status='Occupied'` becomes permanent architecture lock.

4.  **Blank Doctor Dashboard**
    *   **File Name**: `app.py`
    *   **Function Name**: `doctor_dashboard()`
    *   **Exact Reason**: Upon login redirection, `app.py` passes `active_section="dashboard"`. Inside `doctor_session.html` Javascript layer, it matches state visibility strictly using array mapping for `"appointments"` and `"profile"`. When it gets `"dashboard"`, no mapping is resolved, which natively hides every single DOM element globally, rendering an empty UI block.

---

## 5. FRONTEND ↔ BACKEND MISMATCHES

*   **Mismatch 1**: `templates/doctor_session.html` relies entirely upon matched DOM IDs (`#doctor-appointments-section` and `#doctor-profile-section`). The `app.py` controller pushes a literal string `#doctor-dashboard-section` state execution on login which does not map physically to any created layout.
*   **Mismatch 2**: In `templates/generate_bill.html`, the front end accepts form parameters for `description` (`<textarea class="form-control" name="description"...>`). The `app.py` `/generate_bill` POST endpoint explicitly discards this and doesn't fetch `request.form.get("description")` because the `bill` tracking SQLite table strictly lacks a description column entirely.

---

## 6. DATA FLOW TRACE

**Example 1: Chatbot Flow**
`UI Chat Input (Type message & submit)`
↳ `JavaScript sendChatMessage(userMessage)` [POST data using fetch()]
↳ `Route (/api_chat)` [Inside app.py python space]
↳ `Internal Function (genai.GenerativeModel("gemini-...").generate_content)`
↳ `Receives Response & Validates Context String`
↳ `JSON Response (return jsonify(status='success', reply=response.text))`
↳ `Javascript (appendMessage(result.reply, 'ai'))` [Renders DOM response UI]

**Example 2: Symptom Assessment Logging**
`UI Symptom Input (#symptoms-input Textarea)`
↳ `Route (/symptom_analysis)` [Form Submission as POST]
↳ `Function: fetch_symptoms()` [Extracts substring mappings to array]
↳ `Function: fetch_recommendations()` [Executes DISTINCT joins natively over Mappings]
↳ `Function: log_history()` [DB Write: INSERT INTO health_history using session Patient_ID]
↳ `Session Variables (session["analysis"] = {...})` [Overrides and populates arrays variables]
↳ `UI Response` [Re-Routes into patient_dashboard.html explicitly overriding Jinja2 loops to draw boxes].
