# Addis Clinic — Appointment Management System

A full-featured clinic management web application built with **Django** and **MySQL**. Designed for real-world clinic operations with three distinct roles: **Patient**, **Doctor**, and **Admin/Receptionist**.

---

## Features

### Patient
- Register and wait for admin approval
- Search doctors by name, specialty, or available day
- Book appointments from available time slots (unique ref ID per booking)
- Request reschedule (doctor approves/rejects)
- Cancel appointments
- View medical history and visit notes
- Receive email + in-app notifications for every status change

### Doctor
- Manage weekly availability schedule (day, start/end time, slot duration)
- Confirm, reject, or reschedule patient appointments
- Add visit notes after appointments
- Schedule follow-up appointments
- Request time off (vacation, sick leave, training, etc.) with admin approval
- Handle patient reschedule requests
- View pending reschedule requests with approve/reject

### Admin / Receptionist
- Approve/reject new patient registrations
- Manage doctors (add, edit, delete, toggle availability)
- View doctor schedule status (who has a schedule, who doesn't, hours/week)
- Today's Appointments dashboard with overdue detection
- Mark appointments as completed (auto-notifies doctor and patient)
- Admin reschedule appointments (date + time)
- Trigger emergency priority flow — shifts all affected appointments forward
- Manage doctor time-off requests (approve/reject with notes)
- Medical records search by ref ID, patient name, doctor, date, status
- Appointment filtering by month, year, status
- Generate reports for any date range
- Manage specializations and replacement queue

### System-Wide
- Unique appointment reference IDs (e.g. `AC-20260418-0042`)
- Lunch break auto-excluded from slots for schedules > 8 hours
- Double-booking prevention (same specialization, time conflict checks)
- Emergency walk-in flow with automatic schedule shift and patient delay notifications
- Background email sending (non-blocking)
- Bootstrap 5 responsive UI with animated components
- Role-based access control on every view

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, Django 6.0 |
| Database | MySQL |
| Frontend | Bootstrap 5, Chart.js, Font Awesome 6 |
| Email | Gmail SMTP (background thread) |
| Auth | Django AbstractUser (custom) |

---

## Project Structure

```
clinic_app/
├── clinic_app/          # Django project config
│   ├── settings.py      # All configuration
│   ├── urls.py          # Root URL dispatcher
│   └── wsgi.py          # Production deployment
├── core/                # Main application
│   ├── models.py        # All database models
│   ├── views.py         # All request handlers (~3300 lines)
│   ├── urls.py          # URL patterns
│   ├── forms.py         # Registration & doctor forms
│   ├── admin.py         # Django admin registrations
│   ├── context_processors.py  # Global template context
│   ├── utils.py         # Slot generation, notifications, email
│   ├── validators.py    # Password validation
│   └── migrations/      # Database migration history
├── templates/           # HTML templates
│   ├── base.html        # Patient/doctor base layout
│   ├── base_admin.html  # Admin sidebar layout
│   ├── base_auth.html   # Login/register layout
│   └── core/            # All page templates
├── manage.py
└── requirements.txt
```

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- MySQL server running
- Git

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO/clinic_app

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create MySQL database
# In MySQL: CREATE DATABASE clinic_app_system_db CHARACTER SET utf8mb4;

# 5. Configure settings
# Edit clinic_app/settings.py — update DATABASES with your MySQL credentials
# Update EMAIL_HOST_USER and EMAIL_HOST_PASSWORD for Gmail

# 6. Run migrations
python manage.py migrate

# 7. Create superuser (admin account)
python manage.py createsuperuser

# 8. Start the server
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

---

## Environment Variables (Recommended for Production)

Move these out of `settings.py` into environment variables:
- `SECRET_KEY`
- `DATABASE_PASSWORD`
- `EMAIL_HOST_PASSWORD`
- `DEBUG` (set to `False` in production)

---

## Database Models

| Model | Description |
|---|---|
| `User` | Custom user with role (admin/doctor/patient) |
| `DoctorProfile` | Doctor details, specialization, availability flag |
| `DoctorAvailability` | Weekly schedule per doctor |
| `Appointment` | Core booking record with unique ref ID |
| `Notification` | In-app notifications |
| `LeaveRequest` | Doctor time-off requests |
| `RescheduleRequest` | Patient reschedule requests |
| `EmergencyCase` | Walk-in emergency tracking |
| `DoctorReplacementQueue` | Patients waiting for replacement doctor |
| `Specialization` | Medical specialties |

---

## License

MIT License — free to use and modify.
