 # 🏥 Clinic Appointment Scheduling System

## 📌 Overview

A real-world inspired clinic appointment scheduling system designed to manage doctor availability, patient bookings, and treatment flow efficiently.

This system goes beyond simple booking by integrating **queue-based execution**, **emergency handling**, and **dynamic schedule adjustments**, similar to how modern clinics operate.

---

## 🚀 Features

### 👨‍⚕️ Doctor Management

* Define working schedules (day, time range, slot duration)
* View daily appointments
* Mark patients as completed
* Request leave (optional)

### 🧑‍💻 Patient Management

* Register and login
* Book appointments based on available slots
* View appointment status and queue position

### 🏥 Appointment System

* Slot-based booking (30, 45, 60+ minutes)
* Queue-based real execution (not strict time)
* Status tracking (waiting, in-progress, completed)

### 🔄 Dynamic Queue Handling

* Automatic queue progression
* Real-time updates when a patient is completed
* Estimated waiting time adjustments

### 🚨 Emergency Handling

* Admin-controlled emergency priority
* Emergency patients jump the queue
* Automatic shifting of affected appointments

### ⏳ Delay Management

* Handles unpredictable treatment durations
* Updates queue instead of breaking schedule

### 🔁 Carry-over System

* Unfinished patients move to next day
* Treated with priority before new patients

---

## 🧠 System Workflow

1. Doctor sets schedule (time + slots)
2. Patients book appointments
3. System converts bookings into a queue
4. Doctor treats patients one by one
5. Doctor marks a patient as completed
6. System automatically:

   * Moves next patient to "Now Serving"
   * Updates queue positions
   * Notifies the next patient
7. Handles:

   * Delays
   * Emergencies
   * Carry-over patients

---

## 🏗️ Tech Stack

* Backend: Django (Python)
* Database: SQLite (default)
* Frontend: HTML, CSS (or your setup)
* Version Control: Git & GitHub

---

## ⚙️ Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/merawi-hub/Clinic_appointment_scheduling_system.git
cd Clinic_appointment_scheduling_system
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Create superuser

```bash
python manage.py createsuperuser
```

### 5. Run the server

```bash
python manage.py runserver
```

---

## 🔐 Admin Panel

Access Django admin at:

```
http://127.0.0.1:8000/admin/
```

Use your superuser credentials to manage:

* Doctors
* Patients
* Appointments

---

## 💡 Key Concept

> “Patients book by time, but are treated by queue.”

This system reflects real-world clinic behavior where:

* Time slots are estimates
* Queue determines actual treatment order
* System adapts dynamically to real conditions

---

## 📈 Future Improvements

* SMS/Email notifications
* Live queue dashboard
* Doctor shift system
* Online emergency request validation
* Mobile-friendly UI

---

## 👤 Author

**Merawi Kelemework**
GitHub: https://github.com/merawi-hub

---

## ⭐ Contribute

Feel free to fork, improve, and contribute to this project.

---
