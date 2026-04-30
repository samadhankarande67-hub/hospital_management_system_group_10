# Smart Hospital Management System

A comprehensive Hospital Management System built with Python Flask, featuring patient management, doctor scheduling, bill generation, and AI-powered disease prediction.

## 🚀 Features

- **Patient Management**: Registration, profile management, and medical record tracking.
- **Doctor Portal**: Specialized dashboards for doctors to manage sessions and patient interactions.
- **Admin Dashboard**: Comprehensive control panel for managing patients, doctors, rooms, and appointments.
- **AI Disease Prediction**: 
  - Uses a local machine learning model (`disease_model.pkl`) for initial screening.
  - Integrated with **Google Gemini AI** for advanced medical insights and recommendations.
- **Billing System**: Automated bill generation and tracking for hospital services.
- **Document Management**: Securely upload and manage patient medical records (PDF, JPG, PNG).
- **Room Management**: Track room availability and assignments (Available, Occupied).

## 🛠️ Tech Stack

- **Backend**: Python, Flask
- **Database**: SQLite
- **Data Processing**: Pandas, Scikit-learn
- **AI Integration**: Google Gemini Pro (REST API)
- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap

## 📋 Prerequisites

- Python 3.x
- Pip (Python package installer)

## 🔧 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/samadhankarande67-hub/hospital_management_system_group_10.git
   cd hospital_management_system_group_10
   ```

2. **Install dependencies**:
   ```bash
   pip install flask pandas requests scikit-learn
   ```

3. **Set up the Database**:
   The system will automatically initialize `health.db` on the first run using `db_setup.py`.

4. **Configuration**:
   To enable Gemini AI features, set your API key as an environment variable:
   ```bash
   # Windows (PowerShell)
   $env:GEMINI_API_KEY="your_api_key_here"
   
   # Linux/macOS
   export GEMINI_API_KEY="your_api_key_here"
   ```

5. **Run the Application**:
   ```bash
   python app.py
   ```
   Access the app at `http://127.0.0.1:5000`

## 📂 Project Structure

- `app.py`: Main application logic and routing.
- `db_setup.py`: Database schema and initialization script.
- `train_model.py`: Script to train the disease prediction model.
- `disease_model.pkl`: Pre-trained machine learning model.
- `templates/`: UI templates.
- `Uploads/`: Secure storage for patient documents.

## 👥 Contributors

- **Group 10**

---
*Note: This project is for educational purposes. For real medical diagnostics, always consult a professional healthcare provider.*
