from datetime import date as today_date, datetime, timedelta
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm, DoctorForm
from .models import DoctorProfile, Specialization, Appointment, RescheduleRequest, EmergencyCase
from .utils import get_available_slots, notify, send_email_notification


def role_required(*roles):
    """Decorator to restrict views to specific roles."""
    def decorator(view_func):
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser or request.user.role in roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to access that page.')
            return redirect('login')
        return wrapped
    return decorator


# ---------- Auth ----------

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    from django.db.models import Count, Prefetch

    # Group doctors by specialization
    specializations_with_doctors = Specialization.objects.prefetch_related(
        Prefetch(
            'doctorprofile_set',
            queryset=DoctorProfile.objects.filter(is_available=True).select_related('user'),
            to_attr='doctors'
        )
    ).annotate(doc_count=Count('doctorprofile')).filter(doc_count__gt=0).order_by('name')

    stats = {
        'doctors': DoctorProfile.objects.count(),
        'patients': Appointment.objects.values('patient').distinct().count(),
        'appointments': Appointment.objects.count(),
        'specializations': Specialization.objects.count(),
    }
    features = [
        ('fas fa-calendar-check', '#2563eb', '#eff6ff', 'Smart Appointment Booking', 'Book appointments with your preferred doctor. The system prevents double-booking and checks doctor availability automatically.'),
        ('fas fa-user-md', '#7c3aed', '#f3e8ff', 'Expert Doctors', 'Access qualified specialists across multiple medical fields. Doctors manage their own schedules and availability.'),
        ('fas fa-bell', '#d97706', '#fef9c3', 'Instant Notifications', 'Get real-time email and in-app notifications for every appointment update, reschedule, or delay.'),
        ('fas fa-ambulance', '#dc2626', '#fee2e2', 'Emergency Priority Flow', 'Walk-in emergencies are handled instantly. The system shifts affected appointments and notifies all patients automatically.'),
        ('fas fa-calendar-minus', '#0891b2', '#e0f2fe', 'Doctor Time Off Management', 'Doctors request time off with admin approval. Annual leave, sick leave, and extensions are all managed systematically.'),
        ('fas fa-id-card', '#16a34a', '#dcfce7', 'Unique Appointment IDs', 'Every appointment gets a unique reference ID. Patients present it at the clinic for fast check-in and medical record lookup.'),
        ('fas fa-notes-medical', '#7c3aed', '#f3e8ff', 'Complete Medical Records', 'Full appointment history with visit notes, follow-ups, and medical records accessible anytime by ref ID.'),
        ('fas fa-chart-bar', '#1e3a5f', '#eff6ff', 'Admin Analytics & Reports', 'Comprehensive dashboard with doctor availability stats, appointment analytics, and exportable reports.'),
    ]
    return render(request, 'core/landing.html', {
        'specializations_with_doctors': specializations_with_doctors,
        'stats': stats,
        'features': features,
    })


# ---------- Auth ----------

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            form.save_m2m()
            if user.role == 'doctor':
                DoctorProfile.objects.create(user=user)
            from .models import User as UserModel
            admins = UserModel.objects.filter(is_active=True).filter(
                Q(role='admin') | Q(is_superuser=True)
            )
            for admin in admins:
                notify(admin, f'New registration pending approval: {user.get_full_name() or user.username} ({user.role})')
            messages.success(request, 'Registration submitted. Please wait for admin approval before logging in.')
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'core/register.html', {'form': form})


    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Pending admin approval
            user.save()
            form.save_m2m()
            if user.role == 'doctor':
                DoctorProfile.objects.create(user=user)
            # Notify all admins
            from .models import User as UserModel
            admins = UserModel.objects.filter(is_active=True).filter(
                Q(role='admin') | Q(is_superuser=True)
            )
            for admin in admins:
                notify(admin, f'New registration pending approval: {user.get_full_name() or user.username} ({user.role})')
            messages.success(request, 'Registration submitted. Please wait for admin approval before logging in.')
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'core/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            # Check if account exists but is inactive (pending approval)
            from .models import User as UserModel
            try:
                u = UserModel.objects.get(username=username)
                if not u.is_active:
                    # Distinguish between pending (never approved) and blocked (was active)
                    if u.date_joined and not hasattr(u, '_was_active'):
                        # Check if they were ever active by seeing if they have appointments
                        was_active = u.appointments.exists() or u.notifications.exists()
                        if was_active:
                            messages.error(request,
                                'Your account has been blocked. Please contact the clinic administrator.')
                        else:
                            messages.error(request,
                                'Your account is pending admin approval. Please wait.')
                    else:
                        messages.error(request, 'Your account is pending admin approval. Please wait.')
                else:
                    messages.error(request, 'Invalid username or password.')
            except UserModel.DoesNotExist:
                messages.error(request, 'Invalid username or password.')
    return render(request, 'core/login.html')


def logout_view(request):
    logout(request)
    return redirect('landing')


@login_required
def dashboard_view(request):
    # Auto-fix: if superuser has no role set, assign admin
    if request.user.is_superuser and not request.user.role:
        request.user.role = 'admin'
        request.user.save(update_fields=['role'])

    role = request.user.role
    if role == 'admin' or request.user.is_superuser:
        return redirect('admin_dashboard')
    elif role == 'doctor':
        # Guard: if doctor profile was deleted, log out gracefully
        if not DoctorProfile.objects.filter(user=request.user).exists():
            logout(request)
            messages.error(request, 'Your doctor profile no longer exists. Please contact the administrator.')
            return redirect('login')
        return redirect('doctor_dashboard')
    else:
        return redirect('patient_dashboard')


# ---------- Patient ----------

@role_required('patient')
def patient_dashboard(request):
    appointments = Appointment.objects.filter(
        patient=request.user
    ).select_related('doctor__user', 'doctor__specialization').order_by('-date', '-start_time')

    upcoming = appointments.filter(date__gte=today_date.today(), status__in=['pending', 'confirmed', 'rescheduled'])
    past = appointments.filter(date__lt=today_date.today())
    medical_count = appointments.filter(status='completed').count()

    return render(request, 'core/patient_dashboard.html', {
        'upcoming': upcoming,
        'past': past,
        'medical_count': medical_count,
    })


@role_required('patient')
def search_doctors(request):
    query = request.GET.get('q', '')
    specialty_id = request.GET.get('specialty', '')
    day_filter = request.GET.get('day', '')
    specializations = Specialization.objects.all()

    # Only search when the user has actually submitted the form
    searched = any([query, specialty_id, day_filter])
    doctors = None

    if searched:
        doctors = DoctorProfile.objects.filter(is_available=True).select_related('user', 'specialization')

        if query:
            doctors = doctors.filter(
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(user__username__icontains=query)
            )

        if specialty_id:
            doctors = doctors.filter(specialization_id=specialty_id)

        if day_filter != '':
            from .models import DoctorAvailability
            available_doctor_ids = DoctorAvailability.objects.filter(
                day_of_week=day_filter
            ).values_list('doctor_id', flat=True)
            doctors = doctors.filter(id__in=available_doctor_ids)

    day_choices = [(str(i), d) for i, d in enumerate(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])]

    return render(request, 'core/search_doctors.html', {
        'doctors': doctors,
        'specializations': specializations,
        'query': query,
        'selected_specialty': specialty_id,
        'selected_day': day_filter,
        'day_choices': day_choices,
        'searched': searched,
    })


@role_required('patient')
def book_appointment(request, doctor_id):
    from .models import DoctorAvailability, LeaveRequest
    import json
    doctor = get_object_or_404(DoctorProfile, id=doctor_id)

    # Build next 14 days grouped by available day
    availabilities = DoctorAvailability.objects.filter(doctor=doctor).order_by('day_of_week')
    available_day_nums = list(availabilities.values_list('day_of_week', flat=True))

    # Get approved leave date ranges for this doctor
    approved_leaves = LeaveRequest.objects.filter(doctor=doctor, status='approved')
    leave_dates = set()
    active_leave_on_date = {}  # date -> leave object for display
    for leave in approved_leaves:
        d = leave.start_date
        while d <= leave.end_date:
            leave_dates.add(d)
            active_leave_on_date[d] = leave
            d += timedelta(days=1)

    # Check for pending or approved annual leave — block ALL new bookings
    blocking_annual = LeaveRequest.objects.filter(
        doctor=doctor, leave_type='vacation', status__in=['pending', 'approved']
    ).first()
    annual_return_date = None
    if blocking_annual:
        annual_return_date = blocking_annual.end_date + timedelta(days=1)

    # Find the nearest upcoming date for each available day of week — one date per day
    upcoming_dates = []
    if not blocking_annual:
        for dow in sorted(set(available_day_nums)):
            # Find the next occurrence of this day of week from today
            for i in range(0, 8):  # search within next 7 days
                d = today_date.today() + timedelta(days=i)
                if d.weekday() == dow and d not in leave_dates:
                    if i == 0:
                        # Today — only include if future slots remain
                        future_slots = get_available_slots(doctor, d)
                        now_plus_10 = (datetime.now() + timedelta(minutes=10)).time()
                        future_slots = [s for s in future_slots if s >= now_plus_10]
                        if future_slots:
                            upcoming_dates.append(d)
                    else:
                        upcoming_dates.append(d)
                    break  # only the nearest occurrence per day of week
        upcoming_dates.sort()

    selected_date = request.GET.get('date') or request.POST.get('date')
    slots = []
    parsed_date = None
    on_leave = False
    leave_on_selected = None

    if selected_date:
        try:
            parsed_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
            if parsed_date in leave_dates:
                on_leave = True
                leave_on_selected = active_leave_on_date.get(parsed_date)
                slots = []
            elif parsed_date >= today_date.today() and parsed_date.weekday() in available_day_nums:
                slots = get_available_slots(doctor, parsed_date)
                # For today, filter out slots that are less than 10 minutes from now
                if parsed_date == today_date.today():
                    now_plus_10 = (datetime.now() + timedelta(minutes=10)).time()
                    slots = [s for s in slots if s >= now_plus_10]
        except ValueError:
            parsed_date = None

    if request.method == 'POST':
        slot_time = request.POST.get('slot')
        confirmed_warning = request.POST.get('confirmed_warning') == '1'
        if slot_time and parsed_date:
            # Block booking if annual leave is pending or approved
            if blocking_annual:
                messages.error(request, f'This doctor is on annual leave. Booking not available until {annual_return_date}.')
                return redirect(request.path)
            # Block booking on leave dates
            if parsed_date in leave_dates:
                messages.error(request, 'This doctor is on approved leave on the selected date.')
                return redirect(request.path + f'?date={selected_date}')

            try:
                start = datetime.strptime(slot_time, '%H:%M').time()
            except ValueError:
                try:
                    start = datetime.strptime(slot_time, '%H:%M:%S').time()
                except ValueError:
                    messages.error(request, 'Invalid time slot.')
                    return redirect(request.path + f'?date={selected_date}')

            # ── Rule 1: Block same-specialization double booking ──
            if doctor.specialization:
                same_spec_active = Appointment.objects.filter(
                    patient=request.user,
                    doctor__specialization=doctor.specialization,
                    status__in=['pending', 'confirmed', 'rescheduled']
                ).exclude(doctor=doctor).first()
                # Also check same doctor
                same_doc_active = Appointment.objects.filter(
                    patient=request.user,
                    doctor=doctor,
                    status__in=['pending', 'confirmed', 'rescheduled']
                ).first()
                blocking = same_spec_active or same_doc_active
                if blocking:
                    messages.error(request,
                        f'You already have an incomplete appointment with '
                        f'{blocking.doctor} ({blocking.doctor.specialization}) '
                        f'on {blocking.date} at {blocking.start_time.strftime("%I:%M %p")}. '
                        f'Please complete or cancel it before booking another appointment '
                        f'in the same specialization.')
                    return redirect(request.path + f'?date={selected_date}')

            # ── Rule 2: Different specialization — check time conflict (1hr gap) ──
            new_start_dt = datetime.combine(parsed_date, start)
            conflicting = Appointment.objects.filter(
                patient=request.user,
                date=parsed_date,
                status__in=['pending', 'confirmed', 'rescheduled']
            )
            for existing in conflicting:
                existing_dt = datetime.combine(existing.date, existing.start_time)
                gap = abs((new_start_dt - existing_dt).total_seconds()) / 60
                if gap < 60:
                    messages.error(request,
                        f'This appointment conflicts with your existing appointment '
                        f'with {existing.doctor} at {existing.start_time.strftime("%I:%M %p")} '
                        f'on {existing.date}. Appointments must be at least 1 hour apart.')
                    return redirect(request.path + f'?date={selected_date}')

            # ── Rule 2b: Warn about other incomplete appointments (different spec) ──
            other_incomplete = Appointment.objects.filter(
                patient=request.user,
                status__in=['pending', 'confirmed', 'rescheduled']
            ).exclude(date=parsed_date).select_related('doctor__specialization')

            if other_incomplete.exists() and not confirmed_warning:
                # Pass warning info to template for confirmation
                return render(request, 'core/book_appointment.html', {
                    'doctor': doctor,
                    'availabilities': availabilities,
                    'upcoming_dates': upcoming_dates,
                    'selected_date': selected_date,
                    'parsed_date': parsed_date,
                    'slots': slots,
                    'on_leave': on_leave,
                    'leave_on_selected': leave_on_selected,
                    'blocking_annual': blocking_annual,
                    'annual_return_date': annual_return_date,
                    'slot_time': slot_time,
                    'other_incomplete': other_incomplete,
                    'show_warning': True,
                })

            avail = DoctorAvailability.objects.filter(
                doctor=doctor, day_of_week=parsed_date.weekday()
            ).order_by('start_time').first()
            if avail:
                end_dt = datetime.combine(parsed_date, start) + timedelta(minutes=avail.slot_duration)
                end = end_dt.time()
            else:
                end = start

            Appointment.objects.create(
                patient=request.user, doctor=doctor,
                date=parsed_date, start_time=start, end_time=end, status='pending',
                patient_email=request.user.email or '',
                patient_phone=request.user.phone or '',
            )
            # Get the created appointment to include ref in notifications
            appt_obj = Appointment.objects.filter(
                patient=request.user, doctor=doctor,
                date=parsed_date, start_time=start
            ).order_by('-created_at').first()
            appt_ref = appt_obj.appointment_ref if appt_obj else ''

            # In-app: notify patient their request was submitted
            notify(request.user, f'Your appointment request [{appt_ref}] with {doctor} on {parsed_date} at {start.strftime("%I:%M %p")} has been submitted. Keep your Ref ID: {appt_ref}')
            # In-app: notify doctor of new request
            notify(doctor.user, f'New appointment request [{appt_ref}] from {request.user.get_full_name() or request.user.username} on {parsed_date} at {start.strftime("%I:%M %p")}.')
            # Email patient: booking submitted confirmation
            if request.user.email:
                try:
                    send_email_notification(
                        request.user.email,
                        'Appointment Request Submitted — Addis Clinic',
                        f'Dear {request.user.get_full_name() or request.user.username},\n\n'
                        f'Your appointment request has been submitted successfully.\n\n'
                        f'╔══════════════════════════════╗\n'
                        f'  APPOINTMENT REF: {appt_ref}\n'
                        f'  Keep this ID — you will need it\n'
                        f'  when you visit the clinic.\n'
                        f'╚══════════════════════════════╝\n\n'
                        f'=== Booking Details ===\n'
                        f'Doctor     : {doctor}\n'
                        f'Specialty  : {doctor.specialization or "General"}\n'
                        f'Date       : {parsed_date.strftime("%A, %B %d %Y")}\n'
                        f'Time       : {start.strftime("%I:%M %p")}\n'
                        f'Status     : Pending doctor approval\n\n'
                        f'You will receive another email once the doctor responds.\n\n'
                        f'Addis Clinic'
                    )
                except Exception:
                    pass
            # Email doctor: new request notification
            if doctor.user.email:
                try:
                    send_email_notification(
                        doctor.user.email,
                        'New Appointment Request — Addis Clinic',
                        f'Dear {doctor},\n\n'
                        f'You have a new appointment request from {request.user.get_full_name() or request.user.username}.\n\n'
                        f'=== Request Details ===\n'
                        f'Patient : {request.user.get_full_name() or request.user.username}\n'
                        f'Date    : {parsed_date.strftime("%A, %B %d %Y")}\n'
                        f'Time    : {start.strftime("%I:%M %p")}\n\n'
                        f'Please log in to accept or reject this request.\n'
                        f'Login: http://127.0.0.1:8000/login/\n\n'
                        f'Addis Clinic'
                    )
                except Exception:
                    pass
            messages.success(request, 'Appointment requested. A confirmation email has been sent to you.')
            return redirect('patient_dashboard')
        else:
            messages.error(request, 'Please select a time slot.')

    return render(request, 'core/book_appointment.html', {
        'doctor': doctor,
        'availabilities': availabilities,
        'upcoming_dates': upcoming_dates,
        'selected_date': selected_date,
        'parsed_date': parsed_date,
        'slots': slots,
        'on_leave': on_leave,
        'leave_on_selected': leave_on_selected,
        'blocking_annual': blocking_annual,
        'annual_return_date': annual_return_date,
        'show_warning': False,
    })


@role_required('patient')
def cancel_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)

    if appointment.status not in ['pending', 'confirmed']:
        messages.error(request, 'This appointment cannot be cancelled.')
        return redirect('patient_dashboard')

    # Block cancellation if appointment time has already started or passed
    appointment_dt = datetime.combine(appointment.date, appointment.start_time)
    if datetime.now() >= appointment_dt:
        messages.error(request, 'Cannot cancel an appointment that has already started or passed.')
        return redirect('patient_dashboard')

    appointment.status = 'cancelled'
    appointment.save()
    notify(appointment.doctor.user, f'Appointment on {appointment.date} at {appointment.start_time.strftime("%I:%M %p")} was cancelled by {request.user.get_full_name() or request.user.username}.')
    messages.success(request, 'Appointment cancelled successfully.')
    return redirect('patient_dashboard')


@role_required('patient')
def patient_reschedule_request(request, appointment_id):
    from .models import RescheduleRequest, DoctorAvailability, LeaveRequest
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)

    if appointment.status not in ['pending', 'confirmed']:
        messages.error(request, 'Only pending or confirmed appointments can be rescheduled.')
        return redirect('patient_dashboard')

    appointment_dt = datetime.combine(appointment.date, appointment.start_time)
    if datetime.now() >= appointment_dt:
        messages.error(request, 'Cannot reschedule an appointment that has already started or passed.')
        return redirect('patient_dashboard')

    # Check no pending reschedule request already exists
    if appointment.reschedule_requests.filter(status='pending').exists():
        messages.warning(request, 'You already have a pending reschedule request for this appointment.')
        return redirect('patient_dashboard')

    doctor = appointment.doctor
    availabilities = DoctorAvailability.objects.filter(doctor=doctor).order_by('day_of_week')
    available_day_nums = list(availabilities.values_list('day_of_week', flat=True))

    # Exclude leave dates
    approved_leaves = LeaveRequest.objects.filter(doctor=doctor, status='approved')
    leave_dates = set()
    for leave in approved_leaves:
        d = leave.start_date
        while d <= leave.end_date:
            leave_dates.add(d)
            d += timedelta(days=1)

    # Available dates — next 14 days excluding today and leave dates
    upcoming_dates = []
    for i in range(1, 15):
        d = today_date.today() + timedelta(days=i)
        if d.weekday() in available_day_nums and d not in leave_dates and d != appointment.date:
            upcoming_dates.append(d)

    selected_date = request.GET.get('date') or request.POST.get('date')
    slots = []
    parsed_date = None

    if selected_date:
        try:
            parsed_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
            if parsed_date > today_date.today() and parsed_date.weekday() in available_day_nums and parsed_date not in leave_dates:
                slots = get_available_slots(doctor, parsed_date)
        except ValueError:
            parsed_date = None

    if request.method == 'POST':
        slot_time = request.POST.get('slot')
        if slot_time and parsed_date:
            try:
                req_time = datetime.strptime(slot_time, '%H:%M').time()
            except ValueError:
                messages.error(request, 'Invalid time slot.')
                return redirect(request.path + f'?date={selected_date}')

            RescheduleRequest.objects.create(
                appointment=appointment,
                requested_date=parsed_date,
                requested_time=req_time,
                status='pending'
            )
            # Notify doctor for approval
            notify(doctor.user,
                f'RESCHEDULE REQUEST: {request.user.get_full_name() or request.user.username} '
                f'wants to reschedule appointment [{appointment.appointment_ref}] '
                f'from {appointment.date} at {appointment.start_time.strftime("%I:%M %p")} '
                f'→ {parsed_date} at {req_time.strftime("%I:%M %p")}. '
                f'Go to Reschedule Requests to approve or reject.')
            # Notify admins informally
            from .models import User as UserModel
            admins = UserModel.objects.filter(is_active=True).filter(
                Q(role='admin') | Q(is_superuser=True)
            )
            for admin in admins:
                notify(admin,
                    f'Patient {request.user.get_full_name() or request.user.username} '
                    f'requested reschedule for [{appointment.appointment_ref}] with {doctor} '
                    f'→ {parsed_date} at {req_time.strftime("%I:%M %p")}. Doctor will handle approval.')
            messages.success(request, 'Reschedule request sent to your doctor. Waiting for approval.')
            return redirect('patient_dashboard')
        else:
            messages.error(request, 'Please select a time slot.')

    return render(request, 'core/patient_reschedule.html', {
        'appointment': appointment,
        'upcoming_dates': upcoming_dates,
        'selected_date': selected_date,
        'parsed_date': parsed_date,
        'slots': slots,
    })


@role_required('admin')
@role_required('doctor')
def doctor_reschedule_requests(request):
    from .models import RescheduleRequest
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    requests_qs = RescheduleRequest.objects.select_related(
        'appointment__patient'
    ).filter(appointment__doctor=doctor, status='pending').order_by('created_at')
    return render(request, 'core/doctor_reschedule_requests.html', {'requests': requests_qs})


@role_required('doctor')
def doctor_handle_reschedule(request, req_id):
    from .models import RescheduleRequest
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    rr = get_object_or_404(RescheduleRequest, id=req_id, appointment__doctor=doctor)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            # Re-check doctor is still free at requested time
            conflict = Appointment.objects.filter(
                doctor=doctor,
                date=rr.requested_date,
                start_time=rr.requested_time,
                status__in=['pending', 'confirmed']
            ).exclude(id=rr.appointment.id).exists()

            if conflict:
                messages.error(request,
                    f'Cannot approve — you already have an appointment '
                    f'on {rr.requested_date} at {rr.requested_time.strftime("%I:%M %p")}.')
                return redirect('doctor_reschedule_requests')

            old_date = rr.appointment.date
            old_time = rr.appointment.start_time
            rr.appointment.date = rr.requested_date
            rr.appointment.start_time = rr.requested_time
            avail = DoctorAvailability.objects.filter(
                doctor=doctor, day_of_week=rr.requested_date.weekday()
            ).order_by('start_time').first()
            if avail:
                end_dt = datetime.combine(rr.requested_date, rr.requested_time) + timedelta(minutes=avail.slot_duration)
                rr.appointment.end_time = end_dt.time()
            rr.appointment.status = 'confirmed'
            rr.appointment.save()
            rr.status = 'approved'
            rr.save()

            notify(rr.appointment.patient,
                f'Your reschedule request for [{rr.appointment.appointment_ref}] has been APPROVED by {doctor}. '
                f'New date: {rr.requested_date} at {rr.requested_time.strftime("%I:%M %p")}.')
            if rr.appointment.patient.email:
                send_email_notification(
                    rr.appointment.patient.email,
                    'Reschedule Approved — Addis Clinic',
                    f'Dear {rr.appointment.patient.get_full_name() or rr.appointment.patient.username},\n\n'
                    f'Your reschedule request has been APPROVED.\n\n'
                    f'Ref        : {rr.appointment.appointment_ref}\n'
                    f'Doctor     : {doctor}\n'
                    f'New Date   : {rr.requested_date.strftime("%A, %B %d %Y")}\n'
                    f'New Time   : {rr.requested_time.strftime("%I:%M %p")}\n'
                    f'Previous   : {old_date} at {old_time.strftime("%I:%M %p")}\n\n'
                    f'Addis Clinic'
                )
            messages.success(request, 'Reschedule approved. Patient notified.')

        elif action == 'reject':
            rr.status = 'rejected'
            rr.save()
            notify(rr.appointment.patient,
                f'Your reschedule request for [{rr.appointment.appointment_ref}] has been REJECTED by {doctor}. '
                f'Your original appointment on {rr.appointment.date} at {rr.appointment.start_time.strftime("%I:%M %p")} remains.')
            if rr.appointment.patient.email:
                send_email_notification(
                    rr.appointment.patient.email,
                    'Reschedule Request Rejected — Addis Clinic',
                    f'Dear {rr.appointment.patient.get_full_name() or rr.appointment.patient.username},\n\n'
                    f'Your reschedule request for [{rr.appointment.appointment_ref}] has been REJECTED.\n\n'
                    f'Your original appointment on {rr.appointment.date.strftime("%A, %B %d %Y")} '
                    f'at {rr.appointment.start_time.strftime("%I:%M %p")} remains unchanged.\n\nAddis Clinic'
                )
            messages.warning(request, 'Reschedule rejected. Patient notified.')

    return redirect('doctor_reschedule_requests')


# ---------- Doctor ----------

@role_required('doctor')
def doctor_dashboard(request):
    auto_expire_appointments()
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    today = today_date.today()

    today_appointments = Appointment.objects.filter(
        doctor=doctor, date=today
    ).exclude(status='cancelled').order_by('start_time')

    pending = Appointment.objects.filter(
        doctor=doctor, status='pending'
    ).order_by('date', 'start_time')

    upcoming = Appointment.objects.filter(
        doctor=doctor, date__gt=today, status='confirmed'
    ).order_by('date', 'start_time')

    return render(request, 'core/doctor_dashboard.html', {
        'today_appointments': today_appointments,
        'pending': pending,
        'upcoming': upcoming,
        'today': today,
        'now': datetime.now(),
    })


@role_required('doctor')
def manage_appointment(request, appointment_id):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'confirm':
            appointment.status = 'confirmed'
            appointment.save()
            # In-app notification to this specific patient
            notify(appointment.patient, f'Your appointment with {doctor} on {appointment.date} at {appointment.start_time.strftime("%I:%M %p")} has been CONFIRMED.')
            # Email this specific patient
            if appointment.patient.email:
                try:
                    send_email_notification(
                        appointment.patient.email,
                        'Appointment Confirmed — Addis Clinic',
                        f'Dear {appointment.patient.get_full_name() or appointment.patient.username},\n\n'
                        f'Great news! Your appointment has been CONFIRMED.\n\n'
                        f'=== Appointment Details ===\n'
                        f'Doctor     : {doctor}\n'
                        f'Specialty  : {doctor.user.doctor_profile.specialization or "General"}\n'
                        f'Date       : {appointment.date.strftime("%A, %B %d %Y")}\n'
                        f'Time       : {appointment.start_time.strftime("%I:%M %p")}\n'
                        f'Status     : CONFIRMED\n\n'
                        f'Please arrive on time. If you need to cancel, do so at least 1 hour before.\n\n'
                        f'Addis Clinic'
                    )
                except Exception:
                    pass
            messages.success(request, 'Appointment confirmed. Patient has been notified.')

        elif action == 'reject':
            appointment.status = 'rejected'
            appointment.save()
            # In-app notification to this specific patient
            notify(appointment.patient, f'Your appointment with {doctor} on {appointment.date} at {appointment.start_time.strftime("%I:%M %p")} has been REJECTED.')
            # Email this specific patient
            if appointment.patient.email:
                try:
                    send_email_notification(
                        appointment.patient.email,
                        'Appointment Rejected — Addis Clinic',
                        f'Dear {appointment.patient.get_full_name() or appointment.patient.username},\n\n'
                        f'We regret to inform you that your appointment request has been REJECTED.\n\n'
                        f'=== Appointment Details ===\n'
                        f'Doctor : {doctor}\n'
                        f'Date   : {appointment.date.strftime("%A, %B %d %Y")}\n'
                        f'Time   : {appointment.start_time.strftime("%I:%M %p")}\n\n'
                        f'You may book another appointment at a different time.\n'
                        f'Login: http://127.0.0.1:8000/login/\n\n'
                        f'Addis Clinic'
                    )
                except Exception:
                    pass
            messages.success(request, 'Appointment rejected. Patient has been notified.')

        elif action == 'reschedule':
            new_date = request.POST.get('new_date')
            new_time = request.POST.get('new_time')
            if new_date and new_time:
                # Validate: new date must not be in the past
                try:
                    new_date_obj = datetime.strptime(new_date, '%Y-%m-%d').date()
                    new_time_obj = datetime.strptime(new_time, '%H:%M').time()
                except ValueError:
                    messages.error(request, 'Invalid date or time format.')
                    appointment_dt = datetime.combine(appointment.date, appointment.start_time)
                    return render(request, 'core/manage_appointment.html', {
                        'appointment': appointment,
                        'appointment_passed': datetime.now() >= appointment_dt,
                    })

                new_dt = datetime.combine(new_date_obj, new_time_obj)
                if new_dt <= datetime.now():
                    messages.error(request, 'Reschedule date and time must be in the future.')
                    appointment_dt = datetime.combine(appointment.date, appointment.start_time)
                    return render(request, 'core/manage_appointment.html', {
                        'appointment': appointment,
                        'appointment_passed': datetime.now() >= appointment_dt,
                    })

                old_date = appointment.date
                old_time = appointment.start_time
                appointment.date = new_date_obj
                appointment.start_time = new_time_obj
                appointment.status = 'rescheduled'
                appointment.save()
                notify(appointment.patient, f'Your appointment with {doctor} has been RESCHEDULED to {new_date} at {new_time_obj.strftime("%I:%M %p")}.')
                if appointment.patient.email:
                    try:
                        send_email_notification(
                            appointment.patient.email,
                            'Appointment Rescheduled — Addis Clinic',
                            f'Dear {appointment.patient.get_full_name() or appointment.patient.username},\n\n'
                            f'Your appointment has been RESCHEDULED by the doctor.\n\n'
                            f'=== New Schedule ===\n'
                            f'Doctor   : {doctor}\n'
                            f'New Date : {new_date_obj.strftime("%A, %B %d %Y")}\n'
                            f'New Time : {new_time_obj.strftime("%I:%M %p")}\n\n'
                            f'Previous: {old_date} at {old_time.strftime("%I:%M %p")}\n\n'
                            f'Please log in to confirm or cancel the new time.\n'
                            f'Login: http://127.0.0.1:8000/login/\n\n'
                            f'Addis Clinic'
                        )
                    except Exception:
                        pass
                messages.success(request, 'Appointment rescheduled. Patient has been notified.')
            else:
                messages.error(request, 'Please provide a new date and time.')
                appointment_dt = datetime.combine(appointment.date, appointment.start_time)
                return render(request, 'core/manage_appointment.html', {
                    'appointment': appointment,
                    'appointment_passed': datetime.now() >= appointment_dt,
                })
        return redirect('doctor_dashboard')

    appointment_dt = datetime.combine(appointment.date, appointment.start_time)
    return render(request, 'core/manage_appointment.html', {
        'appointment': appointment,
        'appointment_passed': datetime.now() >= appointment_dt,
    })


@role_required('doctor')
def doctor_schedule(request):
    from .models import DoctorAvailability
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    availabilities = DoctorAvailability.objects.filter(doctor=doctor).order_by('day_of_week')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            day = request.POST.get('day_of_week')
            start = request.POST.get('start_time')
            end = request.POST.get('end_time')
            duration = request.POST.get('slot_duration', 30)
            if day and start and end:
                start_t = datetime.strptime(start, '%H:%M').time()
                end_t   = datetime.strptime(end, '%H:%M').time()
                if end_t <= start_t:
                    messages.error(request, 'End time must be after start time.')
                    return redirect('doctor_schedule')
                window_mins = (end_t.hour * 60 + end_t.minute) - (start_t.hour * 60 + start_t.minute)
                if int(duration) > window_mins:
                    messages.error(request, f'Slot duration ({duration} min) cannot exceed the schedule window ({window_mins} min).')
                    return redirect('doctor_schedule')
                # If adding for today's day of week, start must be at least 10 min from now
                now = datetime.now()
                if int(day) == now.weekday():
                    min_start = (now + timedelta(minutes=10)).time().replace(second=0, microsecond=0)
                    if start_t < min_start:
                        messages.error(request,
                            f'Start time must be at least 10 minutes from now '
                            f'({min_start.strftime("%I:%M %p")}) for today.')
                        return redirect('doctor_schedule')
                # Block overlapping schedules on the same day
                existing = DoctorAvailability.objects.filter(doctor=doctor, day_of_week=day)
                for ex in existing:
                    ex_start = datetime.combine(today_date.today(), ex.start_time)
                    ex_end   = datetime.combine(today_date.today(), ex.end_time)
                    new_start_dt = datetime.combine(today_date.today(), start_t)
                    new_end_dt   = datetime.combine(today_date.today(), end_t)
                    if new_start_dt < ex_end and new_end_dt > ex_start:
                        messages.error(request,
                            f'This schedule overlaps with an existing one on the same day '
                            f'({ex.start_time.strftime("%I:%M %p")} – {ex.end_time.strftime("%I:%M %p")}). '
                            f'Please choose a non-overlapping time.')
                        return redirect('doctor_schedule')

                DoctorAvailability.objects.get_or_create(
                    doctor=doctor,
                    day_of_week=day,
                    start_time=start,
                    defaults={'end_time': end, 'slot_duration': duration}
                )
                messages.success(request, 'Availability added.')
            else:
                messages.error(request, 'Please fill all fields.')
        elif action == 'delete':
            avail_id = request.POST.get('avail_id')
            DoctorAvailability.objects.filter(id=avail_id, doctor=doctor).delete()
            messages.success(request, 'Availability removed.')
        return redirect('doctor_schedule')

    day_choices = DoctorAvailability.DAY_CHOICES
    return render(request, 'core/doctor_schedule.html', {
        'availabilities': availabilities,
        'day_choices': day_choices,
    })


@role_required('doctor')
def edit_availability(request, avail_id):
    from .models import DoctorAvailability
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    avail = get_object_or_404(DoctorAvailability, id=avail_id, doctor=doctor)

    # Rule 3: Block edit if there are future booked appointments on this day
    booked_on_day = Appointment.objects.filter(
        doctor=doctor,
        date__gte=today_date.today(),
        date__week_day=avail.day_of_week + 2,  # Django week_day: 1=Sun, 2=Mon ... 8=Sat
        status__in=['pending', 'confirmed', 'rescheduled']
    )
    # Simpler: check by day_of_week directly
    from datetime import timedelta as td
    # Find next occurrence of this weekday and check
    booked_on_day = Appointment.objects.filter(
        doctor=doctor,
        date__gte=today_date.today(),
        status__in=['pending', 'confirmed', 'rescheduled']
    ).filter(date__week_day=(avail.day_of_week + 2) % 7 or 7)

    # Most reliable: filter all future appointments and check weekday in Python
    future_appts = Appointment.objects.filter(
        doctor=doctor,
        date__gte=today_date.today(),
        status__in=['pending', 'confirmed', 'rescheduled']
    )
    booked = [a for a in future_appts if a.date.weekday() == avail.day_of_week]

    if booked:
        booked_dates = ', '.join(str(a.date) for a in booked[:3])
        messages.error(request,
            f'Cannot edit this schedule — there are {len(booked)} booked appointment(s) '
            f'on {avail.get_day_of_week_display()} (e.g. {booked_dates}). '
            f'Cancel or complete those appointments first.')
        return redirect('doctor_schedule')

    if request.method == 'POST':
        start = request.POST.get('start_time')
        end = request.POST.get('end_time')
        duration = request.POST.get('slot_duration', 30)
        if start and end:
            start_t = datetime.strptime(start, '%H:%M').time()
            end_t   = datetime.strptime(end, '%H:%M').time()
            if end_t <= start_t:
                messages.error(request, 'End time must be after start time.')
            else:
                # If editing today's day of week, start must be at least 10 min from now
                now = datetime.now()
                if avail.day_of_week == now.weekday():
                    min_start = (now + timedelta(minutes=10)).time().replace(second=0, microsecond=0)
                    if start_t < min_start:
                        messages.error(request,
                            f'Start time must be at least 10 minutes from now '
                            f'({min_start.strftime("%I:%M %p")}) for today.')
                        return render(request, 'core/edit_availability.html', {'avail': avail})
                avail.start_time = start_t
                avail.end_time = end_t
                avail.slot_duration = int(duration)
                avail.save()
                messages.success(request, 'Availability updated.')
                return redirect('doctor_schedule')
        else:
            messages.error(request, 'Please fill all fields.')

    return render(request, 'core/edit_availability.html', {'avail': avail})


@login_required
def notifications_view(request):
    from .models import Notification
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'core/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def clear_notification(request, notif_id):
    from .models import Notification
    Notification.objects.filter(id=notif_id, user=request.user).delete()
    return redirect('notifications')


@login_required
def clear_all_notifications(request):
    from .models import Notification
    if request.method == 'POST':
        Notification.objects.filter(user=request.user).delete()
    return redirect('notifications')


# ---------- Admin ----------

@role_required('admin')
def admin_dashboard(request):
    from .models import User
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    import json

    total_doctors = DoctorProfile.objects.count()
    total_patients = User.objects.filter(role='patient').count()
    total_appointments = Appointment.objects.count()
    today_appointments = Appointment.objects.filter(date=today_date.today()).count()
    pending_approvals = Appointment.objects.filter(status='pending').count()

    recent_appointments = Appointment.objects.select_related(
        'patient', 'doctor__user'
    ).order_by('-created_at')[:10]

    # Chart: appointments per day (last 7 days)
    from datetime import timedelta
    last_7 = [(today_date.today() - timedelta(days=i)) for i in range(6, -1, -1)]
    appt_counts = Appointment.objects.filter(
        date__gte=last_7[0]
    ).values('date').annotate(count=Count('id'))
    count_map = {str(a['date']): a['count'] for a in appt_counts}
    chart_labels = [d.strftime('%b %d') for d in last_7]
    chart_data = [count_map.get(str(d), 0) for d in last_7]

    # Most active doctors
    top_doctors = DoctorProfile.objects.annotate(
        appt_count=Count('appointments')
    ).order_by('-appt_count')[:5]

    # Pie chart: appointment status breakdown
    status_counts = {}
    for s, _ in Appointment.STATUS_CHOICES:
        status_counts[s] = Appointment.objects.filter(status=s).count()

    pie_labels = [label for _, label in Appointment.STATUS_CHOICES if status_counts.get(_, 0) > 0 or True]
    pie_labels = [label for s, label in Appointment.STATUS_CHOICES]
    pie_data = [status_counts.get(s, 0) for s, _ in Appointment.STATUS_CHOICES]
    pie_colors = ['#f59e0b', '#22c55e', '#ef4444', '#8b5cf6', '#6b7280', '#3b82f6']

    # Pending registrations
    from .models import User as UserModel, DoctorAvailability
    pending_registrations = UserModel.objects.filter(is_active=False).exclude(role='admin').count()

    # ── Doctor availability stats ──
    spec_filter = request.GET.get('avail_spec', '')
    doctors_qs = DoctorProfile.objects.select_related('user', 'specialization').prefetch_related('availabilities')
    if spec_filter:
        doctors_qs = doctors_qs.filter(specialization_id=spec_filter)

    doctor_avail_stats = []
    for doc in doctors_qs:
        avails = doc.availabilities.all()
        days_per_week = avails.count()
        total_mins_week = sum(
            (a.end_time.hour * 60 + a.end_time.minute) - (a.start_time.hour * 60 + a.start_time.minute)
            for a in avails
        )
        total_hours_week = round(total_mins_week / 60, 1)
        total_hours_month = round(total_hours_week * 4, 1)
        doctor_avail_stats.append({
            'doctor': doc,
            'days_per_week': days_per_week,
            'hours_per_week': total_hours_week,
            'hours_per_month': total_hours_month,
        })

    return render(request, 'core/admin_dashboard.html', {
        'total_doctors': total_doctors,
        'total_patients': total_patients,
        'total_appointments': total_appointments,
        'today_appointments': today_appointments,
        'pending_approvals': pending_approvals,
        'recent_appointments': recent_appointments,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'top_doctors': top_doctors,
        'pie_labels': json.dumps(pie_labels),
        'pie_data': json.dumps(pie_data),
        'pie_colors': json.dumps(pie_colors),
        'status_choices': Appointment.STATUS_CHOICES,
        'status_counts': status_counts,
        'status_summary': [(label, status_counts.get(s, 0), s) for s, label in Appointment.STATUS_CHOICES],
        'doctor_avail_stats': doctor_avail_stats,
        'specializations': Specialization.objects.all().order_by('name'),
        'avail_spec_filter': spec_filter,
        'stats': [
            ('Doctors', total_doctors),
            ('Patients', total_patients),
            ('Total Appointments', total_appointments),
            ('Today', today_appointments),
            ('Pending Appointments', pending_approvals),
            ('Pending Registrations', pending_registrations),
        ],
    })


# ---------- Leave Management ----------

@role_required('doctor')
def doctor_leave_request(request):
    from .models import LeaveRequest
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    leaves = LeaveRequest.objects.filter(doctor=doctor)

    # Check for any active (pending or approved) leave right now
    today = today_date.today()
    active_leave = leaves.filter(
        status__in=['pending', 'approved'],
        start_date__lte=today,
        end_date__gte=today
    ).first()

    # Also check for any future pending/approved leave
    future_leave = leaves.filter(
        status__in=['pending', 'approved'],
        end_date__gte=today
    ).order_by('start_date').first()

    # Block form submission if any active or future leave exists
    has_blocking_leave = future_leave is not None

    pending_annual = leaves.filter(leave_type='vacation', status='pending').first()
    approved_annual = leaves.filter(leave_type='vacation', status='approved').first()

    if request.method == 'POST':
        # Hard block — reject POST if doctor already has active/future leave
        if has_blocking_leave:
            messages.error(request, 'You already have an active or upcoming time off. You cannot submit another request until it ends.')
            return redirect('doctor_leave_request')

        leave_type = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date   = request.POST.get('end_date')
        reason     = request.POST.get('reason', '')

        if not start_date or not end_date:
            messages.error(request, 'Please provide both start and end dates.')
        elif start_date > end_date:
            messages.error(request, 'End date must be after start date.')
        elif leave_type != 'vacation' and len(reason.split()) < 3:
            messages.error(request, 'Reason must be at least 3 words.')
        else:
            from datetime import date as date_type
            start_d = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_d   = datetime.strptime(end_date, '%Y-%m-%d').date()

            # Block overlapping time off — any active leave that overlaps the requested range
            overlap = LeaveRequest.objects.filter(
                doctor=doctor,
                status__in=['pending', 'approved'],
                start_date__lte=end_d,
                end_date__gte=start_d
            ).first()
            if overlap:
                if overlap.leave_type == 'vacation':
                    messages.error(request,
                        f'You are already on annual leave ({overlap.start_date} to {overlap.end_date}). '
                        f'You cannot request any other time off until your annual leave ends.')
                else:
                    messages.error(request,
                        f'You already have an active {overlap.get_leave_type_display()} time off '
                        f'({overlap.start_date} to {overlap.end_date}) that overlaps with the requested dates. '
                        f'Double time off is not allowed.')
                return redirect('doctor_leave_request')

            # Annual leave: only once per year
            if leave_type == 'vacation':
                current_year = today_date.today().year
                already_taken = LeaveRequest.objects.filter(
                    doctor=doctor,
                    leave_type='vacation',
                    start_date__year=current_year,
                    status__in=['pending', 'approved']
                ).exists()
                if already_taken:
                    messages.error(request, f'You have already requested or taken annual leave in {current_year}. Only one annual leave per year is allowed.')
                    return redirect('doctor_leave_request')
                # Set reason automatically
                reason = 'Annual leave'
                last_appt = Appointment.objects.filter(
                    doctor=doctor,
                    status__in=['pending', 'confirmed'],
                    date__gte=today_date.today()
                ).order_by('-date').first()

                if last_appt and last_appt.date >= start_d:
                    # Push start to day after last appointment
                    adjusted_start = last_appt.date + timedelta(days=1)
                    duration = (end_d - start_d).days  # preserve 21-day duration
                    start_d = adjusted_start
                    end_d   = adjusted_start + timedelta(days=duration)
                    start_date = str(start_d)
                    end_date   = str(end_d)
                    messages.warning(request,
                        f'You have appointments until {last_appt.date}. '
                        f'Annual leave start adjusted to {start_d} (return: {end_d + timedelta(days=1)}).'
                    )

            leave = LeaveRequest.objects.create(
                doctor=doctor,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                status='pending'
            )
            # Notify all admins
            from .models import User as UserModel
            from django.db.models import Q as DQ
            admins = UserModel.objects.filter(is_active=True).filter(
                DQ(role='admin') | DQ(is_superuser=True)
            )
            for admin in admins:
                notify(admin, f'Time off request from {doctor}: {leave.get_leave_type_display()} '
                              f'({start_date} to {end_date}). Please review.')
            messages.success(request, 'Time off request submitted. Waiting for admin approval.')
            return redirect('doctor_leave_request')

    import calendar as cal_module
    type_filter  = request.GET.get('leave_type', '')
    month_filter = request.GET.get('month', '')
    year_filter  = request.GET.get('year', str(today_date.today().year))
    all_months   = [(str(i), cal_module.month_name[i]) for i in range(1, 13)]

    filtered_leaves = leaves
    if type_filter:
        filtered_leaves = filtered_leaves.filter(leave_type=type_filter)
    if month_filter and year_filter:
        filtered_leaves = filtered_leaves.filter(start_date__month=month_filter, start_date__year=year_filter)

    return render(request, 'core/doctor_leave_request.html', {
        'leaves': filtered_leaves,
        'leave_type_choices': LeaveRequest.LEAVE_TYPE_CHOICES,
        'pending_annual': pending_annual,
        'approved_annual': approved_annual,
        'has_blocking_leave': has_blocking_leave,
        'future_leave': future_leave,
        'all_months': all_months,
        'type_filter': type_filter,
        'month_filter': month_filter,
        'year_filter': year_filter,
        'remaining_appointments': Appointment.objects.filter(
            doctor=doctor,
            status__in=['pending', 'confirmed'],
            date__gte=today_date.today()
        ).order_by('date', 'start_time') if pending_annual else [],
    })


@role_required('doctor')
def doctor_extend_leave(request, leave_id):
    from .models import LeaveRequest
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    leave = get_object_or_404(LeaveRequest, id=leave_id, doctor=doctor, status='approved')

    # Block extension if the original leave hasn't ended yet
    if leave.end_date >= today_date.today():
        messages.error(request,
            f'You can only request an extension after your current leave ends on {leave.end_date}.')
        return redirect('doctor_leave_request')

    if request.method == 'POST':
        extra_days = request.POST.get('extra_days', '').strip()
        reason = request.POST.get('reason', '').strip()

        if not extra_days or not extra_days.isdigit() or int(extra_days) < 1:
            messages.error(request, 'Please enter a valid number of extra days.')
            return redirect('doctor_leave_request')
        if len(reason.split()) < 3:
            messages.error(request, 'Extension reason must be at least 3 words.')
            return redirect('doctor_leave_request')

        extra = int(extra_days)
        new_start = leave.end_date + timedelta(days=1)
        new_end   = new_start + timedelta(days=extra - 1)

        # Check no overlap with other leaves
        overlap = LeaveRequest.objects.filter(
            doctor=doctor,
            status__in=['pending', 'approved'],
            start_date__lte=new_end,
            end_date__gte=new_start
        ).exclude(id=leave.id).first()
        if overlap:
            messages.error(request, f'Extension dates overlap with another time off ({overlap.start_date} to {overlap.end_date}).')
            return redirect('doctor_leave_request')

        ext = LeaveRequest.objects.create(
            doctor=doctor,
            leave_type='extension',
            start_date=new_start,
            end_date=new_end,
            reason=f'Extension of {leave.get_leave_type_display()} ({leave.start_date}–{leave.end_date}). {reason}',
            status='pending'
        )
        from .models import User as UserModel
        from django.db.models import Q as DQ
        admins = UserModel.objects.filter(is_active=True).filter(DQ(role='admin') | DQ(is_superuser=True))
        for admin in admins:
            notify(admin, f'{doctor} has requested a leave extension: {new_start} to {new_end} ({extra} days). Reason: {reason}')
        # Email doctor confirmation
        if doctor.user.email:
            send_email_notification(
                doctor.user.email,
                'Leave Extension Request Submitted — Addis Clinic',
                f'Dear {doctor},\n\n'
                f'Your leave extension request has been submitted successfully.\n\n'
                f'Extension Period : {new_start} to {new_end} ({extra} days)\n'
                f'Reason           : {reason}\n'
                f'Status           : Pending admin approval\n\n'
                f'You will be notified once the admin reviews your request.\n\nAddis Clinic'
            )
        messages.success(request, f'Extension request submitted for {new_start} to {new_end}. Waiting for admin approval.')
    return redirect('doctor_leave_request')


@role_required('doctor')
def doctor_cancel_leave(request, leave_id):
    from .models import LeaveRequest
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    leave = get_object_or_404(LeaveRequest, id=leave_id, doctor=doctor, status='pending')
    leave_info = f'{leave.get_leave_type_display()} ({leave.start_date} to {leave.end_date})'
    leave.delete()
    # Notify admins of cancellation
    from .models import User as UserModel
    from django.db.models import Q as DQ
    admins = UserModel.objects.filter(is_active=True).filter(DQ(role='admin') | DQ(is_superuser=True))
    for admin in admins:
        notify(admin, f'{doctor} has cancelled their time off request: {leave_info}.')
    messages.success(request, 'Leave request cancelled.')
    return redirect('doctor_leave_request')


@role_required('doctor')
def doctor_reschedule_requests(request):
    from .models import RescheduleRequest
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    requests_qs = RescheduleRequest.objects.select_related(
        'appointment__patient'
    ).filter(appointment__doctor=doctor, status='pending').order_by('created_at')
    return render(request, 'core/doctor_reschedule_requests.html', {'requests': requests_qs})


@role_required('doctor')
def doctor_handle_reschedule(request, req_id):
    from .models import RescheduleRequest, DoctorAvailability
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    rr = get_object_or_404(RescheduleRequest, id=req_id, appointment__doctor=doctor)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            conflict = Appointment.objects.filter(
                doctor=doctor,
                date=rr.requested_date,
                start_time=rr.requested_time,
                status__in=['pending', 'confirmed']
            ).exclude(id=rr.appointment.id).exists()

            if conflict:
                messages.error(request,
                    f'Cannot approve — you already have an appointment '
                    f'on {rr.requested_date} at {rr.requested_time.strftime("%I:%M %p")}.')
                return redirect('doctor_reschedule_requests')

            old_date = rr.appointment.date
            old_time = rr.appointment.start_time
            rr.appointment.date = rr.requested_date
            rr.appointment.start_time = rr.requested_time
            avail = DoctorAvailability.objects.filter(
                doctor=doctor, day_of_week=rr.requested_date.weekday()
            ).order_by('start_time').first()
            if avail:
                end_dt = datetime.combine(rr.requested_date, rr.requested_time) + timedelta(minutes=avail.slot_duration)
                rr.appointment.end_time = end_dt.time()
            rr.appointment.status = 'confirmed'
            rr.appointment.save()
            rr.status = 'approved'
            rr.save()

            notify(rr.appointment.patient,
                f'Your reschedule request for [{rr.appointment.appointment_ref}] has been APPROVED by {doctor}. '
                f'New date: {rr.requested_date} at {rr.requested_time.strftime("%I:%M %p")}.')
            if rr.appointment.patient.email:
                send_email_notification(
                    rr.appointment.patient.email,
                    'Reschedule Approved — Addis Clinic',
                    f'Dear {rr.appointment.patient.get_full_name() or rr.appointment.patient.username},\n\n'
                    f'Your reschedule request has been APPROVED.\n\n'
                    f'Ref        : {rr.appointment.appointment_ref}\n'
                    f'Doctor     : {doctor}\n'
                    f'New Date   : {rr.requested_date.strftime("%A, %B %d %Y")}\n'
                    f'New Time   : {rr.requested_time.strftime("%I:%M %p")}\n'
                    f'Previous   : {old_date} at {old_time.strftime("%I:%M %p")}\n\n'
                    f'Addis Clinic'
                )
            messages.success(request, 'Reschedule approved. Patient notified.')

        elif action == 'reject':
            rr.status = 'rejected'
            rr.save()
            notify(rr.appointment.patient,
                f'Your reschedule request for [{rr.appointment.appointment_ref}] has been REJECTED by {doctor}. '
                f'Your original appointment on {rr.appointment.date} at {rr.appointment.start_time.strftime("%I:%M %p")} remains.')
            if rr.appointment.patient.email:
                send_email_notification(
                    rr.appointment.patient.email,
                    'Reschedule Request Rejected — Addis Clinic',
                    f'Dear {rr.appointment.patient.get_full_name() or rr.appointment.patient.username},\n\n'
                    f'Your reschedule request for [{rr.appointment.appointment_ref}] has been REJECTED.\n\n'
                    f'Your original appointment on {rr.appointment.date.strftime("%A, %B %d %Y")} '
                    f'at {rr.appointment.start_time.strftime("%I:%M %p")} remains unchanged.\n\nAddis Clinic'
                )
            messages.warning(request, 'Reschedule rejected. Patient notified.')

    return redirect('doctor_reschedule_requests')


@role_required('admin')
def admin_custom_schedule_requests(request):
    from .models import CustomScheduleRequest
    requests_qs = CustomScheduleRequest.objects.select_related('doctor__user').filter(status='pending').order_by('created_at')
    return render(request, 'core/admin_custom_schedule_requests.html', {'requests': requests_qs})


@role_required('admin')
def admin_handle_custom_schedule(request, req_id):
    from .models import CustomScheduleRequest
    csr = get_object_or_404(CustomScheduleRequest, id=req_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        admin_note = request.POST.get('admin_note', '')
        if action == 'approve':
            csr.status = 'approved'
            csr.admin_note = admin_note
            csr.save()
            # Create the actual availability
            from .models import DoctorAvailability
            DoctorAvailability.objects.get_or_create(
                doctor=csr.doctor,
                day_of_week=csr.day_of_week,
                start_time=csr.start_time,
                defaults={'end_time': csr.end_time, 'slot_duration': csr.slot_duration}
            )
            notify(csr.doctor.user,
                f'Your custom schedule request for {csr.get_day_of_week_display()} '
                f'({csr.start_time.strftime("%I:%M %p")} – {csr.end_time.strftime("%I:%M %p")}) '
                f'has been APPROVED and added to your schedule.'
                + (f' Note: {admin_note}' if admin_note else ''))
            messages.success(request, 'Custom schedule approved and applied.')
        elif action == 'reject':
            csr.status = 'rejected'
            csr.admin_note = admin_note
            csr.save()
            notify(csr.doctor.user,
                f'Your custom schedule request for {csr.get_day_of_week_display()} '
                f'({csr.start_time.strftime("%I:%M %p")} – {csr.end_time.strftime("%I:%M %p")}) '
                f'has been REJECTED.'
                + (f' Reason: {admin_note}' if admin_note else ''))
            messages.warning(request, 'Custom schedule rejected.')
    return redirect('admin_custom_schedule_requests')


@role_required('admin')
def admin_leave_requests(request):
    import calendar as cal_module
    from .models import LeaveRequest

    type_filter  = request.GET.get('leave_type', '')
    month_filter = request.GET.get('month', '')
    year_filter  = request.GET.get('year', str(today_date.today().year))
    all_months   = [(str(i), cal_module.month_name[i]) for i in range(1, 13)]

    leaves = LeaveRequest.objects.select_related('doctor__user').all().order_by('-created_at')

    if type_filter:
        leaves = leaves.filter(leave_type=type_filter)
    if month_filter and year_filter:
        leaves = leaves.filter(start_date__month=month_filter, start_date__year=year_filter)

    return render(request, 'core/admin_leave_requests.html', {
        'leaves': leaves,
        'leave_type_choices': LeaveRequest.LEAVE_TYPE_CHOICES,
        'all_months': all_months,
        'type_filter': type_filter,
        'month_filter': month_filter,
        'year_filter': year_filter,
    })


@role_required('admin')
def admin_handle_leave(request, leave_id):
    from .models import LeaveRequest, DoctorAvailability
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        admin_note = request.POST.get('admin_note', '')
        if action in ('approve', 'reject'):
            leave.status = 'approved' if action == 'approve' else 'rejected'
            leave.admin_note = admin_note

            if leave.status == 'approved':

                if leave.leave_type == 'vacation':
                    # ── Annual leave: adjust dates, never cancel appointments ──
                    duration = (leave.end_date - leave.start_date).days
                    last_appt = Appointment.objects.filter(
                        doctor=leave.doctor,
                        status__in=['pending', 'confirmed'],
                        date__gte=today_date.today()
                    ).order_by('-date').first()

                    if last_appt and last_appt.date >= leave.start_date:
                        new_start = last_appt.date + timedelta(days=1)
                        leave.start_date = new_start
                        leave.end_date   = new_start + timedelta(days=duration)
                        if not admin_note:
                            leave.admin_note = (
                                f'Leave dates adjusted: starts after last appointment '
                                f'({last_appt.date}). New dates: {leave.start_date} – {leave.end_date}.'
                            )

                else:
                    # ── Other time off: handle affected appointments ──
                    affected = Appointment.objects.filter(
                        doctor=leave.doctor,
                        date__range=(leave.start_date, leave.end_date),
                        status__in=['pending', 'confirmed']
                    ).order_by('date', 'start_time')

                    # Find all available doctors in same specialization (excluding this doctor)
                    same_spec_doctors = DoctorProfile.objects.filter(
                        specialization=leave.doctor.specialization,
                        is_available=True
                    ).exclude(id=leave.doctor.id).prefetch_related('availabilities') if leave.doctor.specialization else DoctorProfile.objects.none()

                    for appt in affected:
                        reassigned = False

                        # Try to find a replacement free at the exact same date+time
                        for rep_doc in same_spec_doctors:
                            # Check rep_doc works on that day of week
                            avail = DoctorAvailability.objects.filter(
                                doctor=rep_doc,
                                day_of_week=appt.date.weekday()
                            ).order_by('start_time').first()
                            if not avail:
                                continue

                            # Check the slot is within working hours
                            if not (avail.start_time <= appt.start_time < avail.end_time):
                                continue

                            # Check rep_doc has no conflicting appointment at that time
                            conflict = Appointment.objects.filter(
                                doctor=rep_doc,
                                date=appt.date,
                                start_time=appt.start_time,
                                status__in=['pending', 'confirmed']
                            ).exists()
                            if conflict:
                                continue

                            # Check rep_doc is not on approved leave that day
                            from .models import LeaveRequest as LR
                            on_leave = LR.objects.filter(
                                doctor=rep_doc,
                                status='approved',
                                start_date__lte=appt.date,
                                end_date__gte=appt.date
                            ).exists()
                            if on_leave:
                                continue

                            # Valid replacement found — reassign
                            old_doctor = appt.doctor
                            appt.doctor = rep_doc
                            appt.status = 'pending'
                            appt.save()

                            notify(appt.patient,
                                f'Your appointment on {appt.date} at {appt.start_time.strftime("%I:%M %p")} '
                                f'has been reassigned from {old_doctor} to {rep_doc} '
                                f'due to a time off request. Same date and time.')
                            if appt.patient.email:
                                send_email_notification(
                                    appt.patient.email,
                                    'Appointment Reassigned — Addis Clinic',
                                    f'Dear {appt.patient.get_full_name() or appt.patient.username},\n\n'
                                    f'Your appointment has been reassigned to a different doctor '
                                    f'due to {old_doctor} being on approved time off.\n\n'
                                    f'New Doctor : {rep_doc}\n'
                                    f'Date       : {appt.date}\n'
                                    f'Time       : {appt.start_time.strftime("%I:%M %p")}\n'
                                    f'Status     : Pending (awaiting new doctor confirmation)\n\n'
                                    f'Addis Clinic'
                                )
                            notify(rep_doc.user,
                                f'You have been assigned an appointment from '
                                f'{appt.patient.get_full_name() or appt.patient.username} '
                                f'on {appt.date} at {appt.start_time.strftime("%I:%M %p")} '
                                f'(transferred from {old_doctor}).')
                            if rep_doc.user.email:
                                send_email_notification(
                                    rep_doc.user.email,
                                    'New Appointment Assigned — Addis Clinic',
                                    f'Dear {rep_doc},\n\n'
                                    f'An appointment has been transferred to you due to {old_doctor} being on approved time off.\n\n'
                                    f'Patient : {appt.patient.get_full_name() or appt.patient.username}\n'
                                    f'Date    : {appt.date}\n'
                                    f'Time    : {appt.start_time.strftime("%I:%M %p")}\n'
                                    f'Status  : Pending your confirmation\n\n'
                                    f'Please log in to confirm or reject.\n\nAddis Clinic'
                                )
                            reassigned = True
                            break

                        if not reassigned:
                            # No replacement free at that time — postpone to first available
                            # slot for the SAME doctor after leave ends
                            postpone_start = leave.end_date + timedelta(days=1)
                            new_date = None
                            new_slot = None

                            # Search up to 30 days after leave ends
                            for offset in range(0, 31):
                                candidate = postpone_start + timedelta(days=offset)
                                avail = DoctorAvailability.objects.filter(
                                    doctor=leave.doctor,
                                    day_of_week=candidate.weekday()
                                ).order_by('start_time').first()
                                if not avail:
                                    continue

                                # Find first free slot on this day
                                slots = get_available_slots(leave.doctor, candidate)
                                if slots:
                                    new_date = candidate
                                    new_slot = slots[0]
                                    break

                            if new_date and new_slot:
                                old_date = appt.date
                                old_time = appt.start_time
                                # Calculate end time
                                avail = DoctorAvailability.objects.filter(
                                    doctor=leave.doctor,
                                    day_of_week=new_date.weekday()
                                ).order_by('start_time').first()
                                if avail:
                                    end_dt = datetime.combine(new_date, new_slot) + timedelta(minutes=avail.slot_duration)
                                    new_end = end_dt.time()
                                else:
                                    new_end = new_slot

                                appt.date = new_date
                                appt.start_time = new_slot
                                appt.end_time = new_end
                                appt.status = 'rescheduled'
                                appt.save()

                                notify(appt.patient,
                                    f'Your appointment with {leave.doctor} originally on {old_date} at '
                                    f'{old_time.strftime("%I:%M %p")} has been postponed to '
                                    f'{new_date} at {new_slot.strftime("%I:%M %p")} '
                                    f'due to the doctor\'s approved time off.')
                                if appt.patient.email:
                                    send_email_notification(
                                        appt.patient.email,
                                        'Appointment Postponed — Addis Clinic',
                                        f'Dear {appt.patient.get_full_name() or appt.patient.username},\n\n'
                                        f'Your appointment with {leave.doctor} has been postponed '
                                        f'due to an approved time off request.\n\n'
                                        f'Original : {old_date} at {old_time.strftime("%I:%M %p")}\n'
                                        f'New Date : {new_date}\n'
                                        f'New Time : {new_slot.strftime("%I:%M %p")}\n\n'
                                        f'Addis Clinic'
                                    )
                            else:
                                # No slot found in 30 days — notify patient to rebook manually
                                notify(appt.patient,
                                    f'Your appointment with {leave.doctor} on {appt.date} at '
                                    f'{appt.start_time.strftime("%I:%M %p")} could not be automatically '
                                    f'rescheduled. Please contact the clinic to rebook.')
                                if appt.patient.email:
                                    send_email_notification(
                                        appt.patient.email,
                                        'Action Required — Appointment Needs Rebooking',
                                        f'Dear {appt.patient.get_full_name() or appt.patient.username},\n\n'
                                        f'Your appointment with {leave.doctor} on {appt.date} at '
                                        f'{appt.start_time.strftime("%I:%M %p")} could not be '
                                        f'automatically rescheduled due to limited availability.\n\n'
                                        f'Please log in and book a new appointment.\n\nAddis Clinic'
                                    )

            leave.save()

            # Email + notify doctor
            status_word = 'APPROVED' if leave.status == 'approved' else 'REJECTED'
            notify(leave.doctor.user,
                   f'Your {leave.get_leave_type_display()} request '
                   f'({leave.start_date} to {leave.end_date}) has been {status_word}.'
                   + (f' Note: {leave.admin_note}' if leave.admin_note else ''))
            if leave.doctor.user.email:
                if leave.leave_type == 'extension':
                    subject = f'Leave Extension {status_word} — Addis Clinic'
                    body = (
                        f'Dear {leave.doctor},\n\n'
                        f'Your leave extension request ({leave.start_date} to {leave.end_date}) has been {status_word}.\n\n'
                        + (f'Admin response: {leave.admin_note}\n\n' if leave.admin_note else '')
                        + 'Addis Clinic'
                    )
                elif leave.leave_type == 'vacation' and leave.status == 'approved':
                    subject = f'Annual Leave APPROVED — Addis Clinic'
                    body = (
                        f'Dear {leave.doctor},\n\n'
                        f'Your Annual Leave has been APPROVED.\n\n'
                        f'Leave Period : {leave.start_date} to {leave.end_date}\n'
                        f'Return Date  : {leave.end_date + timedelta(days=1)}\n\n'
                        + (f'Note: {leave.admin_note}\n\n' if leave.admin_note else '')
                        + 'Addis Clinic'
                    )
                else:
                    subject = f'Time Off Request {status_word} — Addis Clinic'
                    body = (
                        f'Dear {leave.doctor},\n\n'
                        f'Your {leave.get_leave_type_display()} request '
                        f'({leave.start_date} to {leave.end_date}) has been {status_word}.\n\n'
                        + (f'Admin response: {leave.admin_note}\n\n' if leave.admin_note else '')
                        + 'Addis Clinic'
                    )
                send_email_notification(leave.doctor.user.email, subject, body)
            messages.success(request, f'Time off request {status_word.lower()}.')
    return redirect('admin_leave_requests')


@role_required('admin')
def admin_users(request):
    import calendar as cal_module
    from .models import User

    month_filter = request.GET.get('month', '')
    year_filter = request.GET.get('year', str(today_date.today().year))
    all_months = [(str(i), cal_module.month_name[i]) for i in range(1, 13)]

    users = User.objects.filter(role='patient', is_active=True).order_by('-date_joined')

    # Only filter when BOTH month and year are provided, and only show results
    # if that exact (year, month) combination actually has data.
    if month_filter and year_filter:
        filtered = users.filter(date_joined__month=month_filter, date_joined__year=year_filter)
        users = filtered  # will be empty queryset if no data for that combo

    # Separate pending (never approved) from blocked (were active, now blocked)
    # Pending = inactive + no appointments; Blocked = inactive + has activity
    all_inactive = User.objects.filter(is_active=False, role='patient').order_by('-date_joined')
    pending = all_inactive.filter(appointments__isnull=True, notifications__isnull=True).distinct()
    blocked_users = all_inactive.exclude(id__in=pending.values('id'))

    return render(request, 'core/admin_users.html', {
        'users': users,
        'pending': pending,
        'blocked_users': blocked_users,
        'all_months': all_months,
        'month_filter': month_filter,
        'year_filter': year_filter,
    })


@role_required('admin')
def admin_approve_user(request, user_id):
    from .models import User
    user = get_object_or_404(User, id=user_id)
    action = request.POST.get('action')
    if action == 'approve':
        user.is_active = True
        user.save()
        notify(user, 'Your account has been approved. You can now log in.')
        if user.email:
            try:
                send_email_notification(
                    user.email,
                    'Account Approved — Addis Clinic',
                    f'Dear {user.get_full_name() or user.username},\n\n'
                    f'Your account has been approved. You can now log in at http://127.0.0.1:8000/login/\n\nAddis Clinic'
                )
            except Exception:
                pass
        messages.success(request, f'{user.username} approved.')
    elif action == 'reject':
        username = user.username
        user.delete()
        messages.success(request, f'Registration for {username} rejected and removed.')
    return redirect('admin_users')


@role_required('admin')
def admin_toggle_user(request, user_id):
    from .models import User
    user = get_object_or_404(User, id=user_id, role='patient')
    user.is_active = not user.is_active
    user.save()
    status = 'activated' if user.is_active else 'blocked'
    messages.success(request, f'User {user.username} has been {status}.')
    return redirect('admin_users')


@role_required('admin')
def admin_delete_user(request, user_id):
    from .models import User
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        username = user.username
        email = user.email
        # Delete the user and any other inactive accounts sharing the same username or email
        User.objects.filter(username=username).delete()
        if email:
            User.objects.filter(email=email).delete()
        messages.success(request, f'User {username} has been permanently deleted.')
    return redirect('admin_users')


@role_required('admin')
def admin_appointments(request):
    import calendar as cal_module

    status_filter = request.GET.get('status', '')
    month_filter = request.GET.get('month', '')
    year_filter = request.GET.get('year', str(today_date.today().year))

    # Always show all 12 months
    all_months = [(str(i), cal_module.month_name[i]) for i in range(1, 13)]

    # Show appointments when year is provided (month optional — empty = all months for that year)
    if year_filter:
        appointments = Appointment.objects.select_related('patient', 'doctor__user').order_by('-date', '-start_time')
        appointments = appointments.filter(date__year=year_filter)
        if month_filter:
            appointments = appointments.filter(date__month=month_filter)
        if status_filter:
            appointments = appointments.filter(status=status_filter)
    else:
        appointments = None

    if request.method == 'POST':
        appt_id = request.POST.get('appointment_id')
        action = request.POST.get('action')
        appt = get_object_or_404(Appointment, id=appt_id)
        if action == 'confirm':
            appt.status = 'confirmed'
        elif action == 'reject':
            appt.status = 'rejected'
        appt.save()
        messages.success(request, f'Appointment {action}ed.')
        return redirect(request.get_full_path())

    return render(request, 'core/admin_appointments.html', {
        'appointments': appointments,
        'status_filter': status_filter,
        'month_filter': month_filter,
        'year_filter': year_filter,
        'status_choices': Appointment.STATUS_CHOICES,
        'all_months': all_months,
    })


# ── Today's appointments for admin ──

def _get_available_doctors_for_emergency(today):
    """
    Returns doctors sorted for emergency assignment:
    1. Available + on schedule today + no active emergency + not on leave
    2. Sorted by today's appointment load (fewest first = most free)
    """
    from .models import LeaveRequest, EmergencyCase
    from django.db.models import Count

    # Doctors on leave today
    on_leave_ids = LeaveRequest.objects.filter(
        status='approved',
        start_date__lte=today,
        end_date__gte=today
    ).values_list('doctor_id', flat=True)

    # Doctors with active emergency
    active_em_ids = EmergencyCase.objects.filter(
        status='active'
    ).values_list('doctor_id', flat=True)

    # Doctors with schedule today
    today_dow = today.weekday()
    from .models import DoctorAvailability
    scheduled_ids = DoctorAvailability.objects.filter(
        day_of_week=today_dow
    ).values_list('doctor_id', flat=True)

    doctors = DoctorProfile.objects.filter(
        is_available=True,
        id__in=scheduled_ids
    ).exclude(
        id__in=on_leave_ids
    ).exclude(
        id__in=active_em_ids
    ).select_related('user', 'specialization').annotate(
        today_load=Count(
            'appointments',
            filter=Q(appointments__date=today, appointments__status__in=['confirmed', 'pending', 'delayed'])
        )
    ).order_by('today_load', 'user__first_name')

    return doctors


@role_required('admin')
def admin_today_appointments(request):
    today = today_date.today()
    now = datetime.now()

    todays = Appointment.objects.filter(
        date=today
    ).select_related('patient', 'doctor__user', 'doctor__specialization').order_by('start_time')

    # Mark overdue: time has passed, status is still confirmed/pending
    overdue_ids = set()
    for appt in todays:
        appt_dt = datetime.combine(appt.date, appt.start_time)
        if now > appt_dt and appt.status in ('confirmed', 'pending'):
            overdue_ids.add(appt.id)

    # Follow-up appointments scheduled for future dates linked to today's appts
    upcoming_followups = Appointment.objects.filter(
        follow_up_of__date=today,
        date__gt=today
    ).select_related('patient', 'doctor__user').order_by('date', 'start_time')

    return render(request, 'core/admin_today_appointments.html', {
        'appointments': todays,
        'today': today,
        'now': now,
        'overdue': overdue_ids,
        'upcoming_followups': upcoming_followups,
        'doctors': _get_available_doctors_for_emergency(today),
        'active_emergencies': EmergencyCase.objects.filter(status='active', triggered_at__date=today).select_related('doctor__user'),
    })


# ── Admin Medical Records Search ──
@role_required('admin')
def admin_medical_records(request):
    import calendar as cal_module
    searched = any([
        request.GET.get('ref', ''),
        request.GET.get('patient', ''),
        request.GET.get('doctor', ''),
        request.GET.get('date', ''),
        request.GET.get('month', ''),
        request.GET.get('status', ''),
    ])
    records = None

    if searched:
        records = Appointment.objects.select_related(
            'patient', 'doctor__user', 'doctor__specialization', 'follow_up_of'
        ).order_by('-date', '-start_time')

        ref = request.GET.get('ref', '').strip()
        patient = request.GET.get('patient', '').strip()
        doctor = request.GET.get('doctor', '').strip()
        date = request.GET.get('date', '').strip()
        month = request.GET.get('month', '').strip()
        year = request.GET.get('year', '').strip()
        status = request.GET.get('status', '').strip()

        if ref:
            records = records.filter(appointment_ref__icontains=ref)
        if patient:
            records = records.filter(
                Q(patient__first_name__icontains=patient) |
                Q(patient__last_name__icontains=patient) |
                Q(patient__username__icontains=patient)
            )
        if doctor:
            records = records.filter(
                Q(doctor__user__first_name__icontains=doctor) |
                Q(doctor__user__last_name__icontains=doctor) |
                Q(doctor__user__username__icontains=doctor)
            )
        if date:
            records = records.filter(date=date)
        if month and year:
            records = records.filter(date__month=month, date__year=year)
        elif month:
            records = records.filter(date__month=month)
        if status:
            records = records.filter(status=status)

    all_months = [(str(i), cal_module.month_name[i]) for i in range(1, 13)]

    return render(request, 'core/admin_medical_records.html', {
        'records': records,
        'searched': searched,
        'status_choices': Appointment.STATUS_CHOICES,
        'all_months': all_months,
        'get': request.GET,
    })


# ── Admin reschedules appointment (date + time) ──
@role_required('admin')
def admin_reschedule_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    if request.method == 'POST':
        new_date = request.POST.get('new_date', '').strip()
        new_time = request.POST.get('new_time', '').strip()
        if not new_date or not new_time:
            messages.error(request, 'Please provide both a new date and time.')
            return redirect('admin_today_appointments')
        try:
            new_date_obj = datetime.strptime(new_date, '%Y-%m-%d').date()
            new_time_obj = datetime.strptime(new_time, '%H:%M').time()
        except ValueError:
            messages.error(request, 'Invalid date or time format.')
            return redirect('admin_today_appointments')

        new_dt = datetime.combine(new_date_obj, new_time_obj)
        if new_dt <= datetime.now():
            messages.error(request, 'New date and time must be in the future.')
            return redirect('admin_today_appointments')

        # Check doctor is free at new time
        conflict = Appointment.objects.filter(
            doctor=appointment.doctor,
            date=new_date_obj,
            start_time=new_time_obj,
            status__in=['pending', 'confirmed']
        ).exclude(id=appointment.id).exists()
        if conflict:
            messages.error(request,
                f'{appointment.doctor} already has an appointment on {new_date_obj} at {new_time_obj.strftime("%I:%M %p")}.')
            return redirect('admin_today_appointments')

        old_date = appointment.date
        old_time = appointment.start_time
        # Recalculate end time
        from .models import DoctorAvailability
        avail = DoctorAvailability.objects.filter(
            doctor=appointment.doctor,
            day_of_week=new_date_obj.weekday()
        ).order_by('start_time').first()
        if avail:
            end_dt = datetime.combine(new_date_obj, new_time_obj) + timedelta(minutes=avail.slot_duration)
            appointment.end_time = end_dt.time()

        appointment.date = new_date_obj
        appointment.start_time = new_time_obj
        appointment.status = 'rescheduled'
        appointment.save()

        notify(appointment.patient,
            f'Your appointment [{appointment.appointment_ref}] with {appointment.doctor} '
            f'has been rescheduled by the clinic.\n'
            f'New: {new_date_obj.strftime("%A, %B %d %Y")} at {new_time_obj.strftime("%I:%M %p")}\n'
            f'Previous: {old_date} at {old_time.strftime("%I:%M %p")}')
        if appointment.patient.email:
            send_email_notification(
                appointment.patient.email,
                'Appointment Rescheduled — Addis Clinic',
                f'Dear {appointment.patient.get_full_name() or appointment.patient.username},\n\n'
                f'Your appointment has been rescheduled by the clinic.\n\n'
                f'Ref          : {appointment.appointment_ref}\n'
                f'Doctor       : {appointment.doctor}\n'
                f'New Date     : {new_date_obj.strftime("%A, %B %d %Y")}\n'
                f'New Time     : {new_time_obj.strftime("%I:%M %p")}\n'
                f'Previous     : {old_date} at {old_time.strftime("%I:%M %p")}\n\n'
                f'Addis Clinic'
            )
        if appointment.doctor:
            notify(appointment.doctor.user,
                f'Appointment [{appointment.appointment_ref}] with '
                f'{appointment.patient.get_full_name() or appointment.patient.username} '
                f'rescheduled by admin to {new_date_obj} at {new_time_obj.strftime("%I:%M %p")}.')

        messages.success(request,
            f'Appointment {appointment.appointment_ref} rescheduled to '
            f'{new_date_obj.strftime("%b %d")} at {new_time_obj.strftime("%I:%M %p")}.')
    return redirect('admin_today_appointments')


# ── Admin marks appointment as completed ──
@role_required('admin')
def admin_complete_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    if request.method == 'POST':
        # Block if the appointment slot hasn't finished yet
        appt_end_dt = datetime.combine(appointment.date, appointment.end_time)
        if datetime.now() < appt_end_dt:
            remaining = int((appt_end_dt - datetime.now()).total_seconds() / 60)
            messages.error(request,
                f'Cannot complete appointment [{appointment.appointment_ref}] yet. '
                f'The slot ends at {appointment.end_time.strftime("%I:%M %p")} — '
                f'{remaining} minute(s) remaining.')
            return redirect('admin_today_appointments')

        appointment.status = 'completed'
        appointment.save(update_fields=['status', 'updated_at'])

        # Check if this appointment has a follow-up scheduled
        followup = appointment.follow_ups.filter(status__in=['pending', 'confirmed']).first()

        # Notify patient
        followup_msg = ''
        if followup:
            followup_msg = (f'\n\nYou have a follow-up appointment scheduled:\n'
                           f'Ref  : {followup.appointment_ref}\n'
                           f'Date : {followup.date.strftime("%A, %B %d %Y")}\n'
                           f'Time : {followup.start_time.strftime("%I:%M %p")}')

        notify(appointment.patient,
               f'Your appointment [{appointment.appointment_ref}] with {appointment.doctor} '
               f'on {appointment.date} has been marked as COMPLETED.'
               + (f' Your follow-up is on {followup.date} at {followup.start_time.strftime("%I:%M %p")} [{followup.appointment_ref}].' if followup else ''))

        if appointment.patient.email:
            send_email_notification(
                appointment.patient.email,
                'Visit Completed — Addis Clinic',
                f'Dear {appointment.patient.get_full_name() or appointment.patient.username},\n\n'
                f'Your appointment has been marked as COMPLETED.\n\n'
                f'Ref        : {appointment.appointment_ref}\n'
                f'Doctor     : {appointment.doctor}\n'
                f'Date       : {appointment.date.strftime("%A, %B %d %Y")}\n'
                f'Time       : {appointment.start_time.strftime("%I:%M %p")}\n\n'
                + (f'Visit Notes:\n{appointment.notes}\n\n' if appointment.notes else '')
                + followup_msg
                + '\n\nYou can view your full medical history by logging in.\nAddis Clinic'
            )

        # Notify doctor — auto-complete on their side
        if appointment.doctor:
            notify(appointment.doctor.user,
                   f'Appointment [{appointment.appointment_ref}] with '
                   f'{appointment.patient.get_full_name() or appointment.patient.username} '
                   f'on {appointment.date} has been marked as completed by the admin/receptionist.'
                   + (f' Follow-up scheduled: {followup.date} [{followup.appointment_ref}].' if followup else ''))

        # Check replacement queue
        if appointment.doctor and appointment.doctor.specialization:
            from .models import DoctorReplacementQueue
            waiting = DoctorReplacementQueue.objects.filter(
                specialization=appointment.doctor.specialization, status='waiting'
            ).order_by('created_at')
            if waiting.exists():
                from .models import User as UserModel
                admins = UserModel.objects.filter(Q(role='admin') | Q(is_superuser=True), is_active=True)
                for admin_user in admins:
                    notify(admin_user,
                           f'{waiting.count()} patient(s) waiting for a '
                           f'{appointment.doctor.specialization} doctor. Go to Replacement Queue.')

        messages.success(request, f'Appointment {appointment.appointment_ref} marked as completed.'
                        + (f' Follow-up on {followup.date} is active.' if followup else ''))
    return redirect('admin_today_appointments')


# ── Emergency Priority Flow ──

@role_required('admin')
def admin_trigger_emergency(request):
    """Admin marks a walk-in patient as URGENT and triggers schedule shift."""
    from .models import EmergencyCase, LeaveRequest
    if request.method == 'POST':
        doctor_id = request.POST.get('doctor_id')
        patient_name = request.POST.get('patient_name', '').strip()
        patient_phone = request.POST.get('patient_phone', '').strip()
        duration = int(request.POST.get('estimated_duration', 30))
        notes = request.POST.get('notes', '').strip()

        doctor = get_object_or_404(DoctorProfile, id=doctor_id)
        today = today_date.today()
        now = datetime.now()

        # ── Guard 1: Doctor must be marked available ──
        if not doctor.is_available:
            messages.error(request, f'{doctor} is marked as unavailable and cannot be assigned to an emergency.')
            return redirect('admin_today_appointments')

        # ── Guard 2: Doctor must not be on approved leave today ──
        on_leave = LeaveRequest.objects.filter(
            doctor=doctor,
            status='approved',
            start_date__lte=today,
            end_date__gte=today
        ).first()
        if on_leave:
            messages.error(request,
                f'{doctor} is on approved {on_leave.get_leave_type_display()} '
                f'({on_leave.start_date} to {on_leave.end_date}) and cannot be assigned.')
            return redirect('admin_today_appointments')

        # ── Guard 3: Doctor must not already be handling an active emergency ──
        active_em = EmergencyCase.objects.filter(doctor=doctor, status='active').first()
        if active_em:
            messages.error(request,
                f'{doctor} is already handling an active emergency '
                f'(patient: {active_em.patient_name}). Resolve it first.')
            return redirect('admin_today_appointments')

        # ── Guard 4: Doctor must have a schedule today ──
        has_schedule = doctor.availabilities.filter(day_of_week=today.weekday()).exists()
        if not has_schedule:
            messages.error(request, f'{doctor} has no schedule today and cannot be assigned.')
            return redirect('admin_today_appointments')

        # Create emergency case
        emergency = EmergencyCase.objects.create(
            doctor=doctor,
            patient_name=patient_name,
            patient_phone=patient_phone,
            estimated_duration=duration,
            notes=notes,
            status='active'
        )

        # ── Register emergency patient for medical record ──
        from .models import User as UserModel
        import re, random, string
        # Create a system user account for the walk-in patient
        base_username = re.sub(r'[^a-zA-Z0-9]', '', patient_name.lower())[:8] or 'walkin'
        username = base_username
        counter = 1
        while UserModel.objects.filter(username=username).exists():
            username = f'{base_username}{counter}'
            counter += 1
        temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        emergency_user = UserModel.objects.create_user(
            username=username,
            first_name=patient_name.split()[0] if patient_name else 'Emergency',
            last_name=' '.join(patient_name.split()[1:]) if len(patient_name.split()) > 1 else 'Patient',
            phone=patient_phone or '',
            role='patient',
            is_active=True,
        )
        emergency_user.set_password(temp_password)
        emergency_user.save()

        # Notify admin with the new patient's credentials (to hand to patient)
        notify(request.user,
            f'Emergency patient registered: Username: {username} | Temp Password: {temp_password} | '
            f'Name: {patient_name}. Please give these credentials to the patient for future logins.')

        # Create appointment record for medical history
        emergency_appt = Appointment.objects.create(
            patient=emergency_user,
            doctor=doctor,
            date=today,
            start_time=now.time().replace(second=0, microsecond=0),
            end_time=(now + timedelta(minutes=duration)).time().replace(second=0, microsecond=0),
            status='confirmed',
            notes=f'Emergency walk-in. {notes}',
            patient_phone=patient_phone or '',
        )

        # Shift all remaining today's confirmed/pending/delayed appointments for this doctor
        remaining = Appointment.objects.filter(
            doctor=doctor,
            date=today,
            status__in=['confirmed', 'pending'],
            start_time__gte=now.time()
        ).order_by('start_time')

        shifted_count = 0
        for appt in remaining:
            old_start = appt.start_time
            old_end = appt.end_time
            # Shift forward by emergency duration
            new_start_dt = datetime.combine(today, old_start) + timedelta(minutes=duration)
            new_end_dt   = datetime.combine(today, old_end)   + timedelta(minutes=duration)
            appt.start_time = new_start_dt.time()
            appt.end_time   = new_end_dt.time()
            appt.status = 'delayed'
            appt.save(update_fields=['start_time', 'end_time', 'status', 'updated_at'])
            shifted_count += 1

            # Notify patient
            notify(appt.patient,
                f'⚠️ DELAY NOTICE: Your appointment [{appt.appointment_ref}] with {doctor} '
                f'has been delayed by {duration} minutes due to an emergency case. '
                f'New time: {appt.start_time.strftime("%I:%M %p")}. We apologize for the inconvenience.')
            if appt.patient.email:
                send_email_notification(
                    appt.patient.email,
                    'Appointment Delayed — Addis Clinic',
                    f'Dear {appt.patient.get_full_name() or appt.patient.username},\n\n'
                    f'We regret to inform you that your appointment has been delayed due to an emergency case.\n\n'
                    f'Ref          : {appt.appointment_ref}\n'
                    f'Doctor       : {doctor}\n'
                    f'Original Time: {old_start.strftime("%I:%M %p")}\n'
                    f'New Time     : {appt.start_time.strftime("%I:%M %p")}\n'
                    f'Delay        : {duration} minutes\n\n'
                    f'We sincerely apologize for the inconvenience.\n\nAddis Clinic'
                )

        # Notify doctor immediately
        notify(doctor.user,
            f'🚨 EMERGENCY: Walk-in patient "{patient_name}" has been marked URGENT. '
            f'Estimated duration: {duration} min. '
            f'{shifted_count} appointment(s) shifted forward by {duration} minutes. '
            f'Please attend to the emergency immediately.')
        if doctor.user.email:
            send_email_notification(
                doctor.user.email,
                '🚨 Emergency Patient — Addis Clinic',
                f'Dear {doctor},\n\n'
                f'An emergency patient has been assigned to you.\n\n'
                f'Patient      : {patient_name}\n'
                f'Phone        : {patient_phone or "N/A"}\n'
                f'Est. Duration: {duration} minutes\n'
                f'Notes        : {notes or "None"}\n\n'
                f'{shifted_count} of your today\'s appointments have been shifted forward by {duration} minutes.\n\n'
                f'Please attend to the emergency immediately.\n\nAddis Clinic'
            )

        messages.success(request,
            f'🚨 Emergency triggered for {doctor}. '
            f'{shifted_count} appointment(s) shifted by {duration} min. Doctor notified. '
            f'Patient account created — Username: {username} | Temp Password: {temp_password} — '
            f'Give these credentials to the patient for future logins.')
    return redirect('admin_today_appointments')


@role_required('admin')
def admin_resolve_emergency(request, emergency_id):
    """Admin/doctor marks emergency as resolved — schedule resumes at shifted times."""
    from .models import EmergencyCase
    emergency = get_object_or_404(EmergencyCase, id=emergency_id, status='active')
    if request.method == 'POST':
        emergency.status = 'resolved'
        from django.utils import timezone
        emergency.resolved_at = timezone.now()
        emergency.save()

        # Restore delayed appointments back to confirmed
        today = today_date.today()
        delayed = Appointment.objects.filter(
            doctor=emergency.doctor,
            date=today,
            status='delayed'
        ).order_by('start_time')

        for appt in delayed:
            appt.status = 'confirmed'
            appt.save(update_fields=['status', 'updated_at'])
            notify(appt.patient,
                f'✅ UPDATE: The emergency has been resolved. Your appointment [{appt.appointment_ref}] '
                f'with {emergency.doctor} is now confirmed at {appt.start_time.strftime("%I:%M %p")}.')

        notify(emergency.doctor.user,
            f'Emergency case for "{emergency.patient_name}" has been resolved. '
            f'Your schedule resumes. {delayed.count()} appointment(s) restored to confirmed.')

        messages.success(request, f'Emergency resolved. {delayed.count()} appointment(s) restored.')
    return redirect('admin_today_appointments')


# ── Feature 5: Doctor assigns follow-up appointment ──
@role_required('doctor')
def doctor_followup_appointment(request, appointment_id):
    from .models import DoctorAvailability
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    original = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)

    availabilities = DoctorAvailability.objects.filter(doctor=doctor).order_by('day_of_week')
    available_day_nums = list(availabilities.values_list('day_of_week', flat=True))

    # Exclude leave dates
    from .models import LeaveRequest
    approved_leaves = LeaveRequest.objects.filter(doctor=doctor, status='approved')
    leave_dates = set()
    for leave in approved_leaves:
        d = leave.start_date
        while d <= leave.end_date:
            leave_dates.add(d)
            d += timedelta(days=1)

    upcoming_dates = []
    for i in range(1, 30):
        d = today_date.today() + timedelta(days=i)
        if d.weekday() in available_day_nums and d not in leave_dates:
            upcoming_dates.append(d)

    selected_date = request.GET.get('date') or request.POST.get('date')
    slots = []
    parsed_date = None

    if selected_date:
        try:
            parsed_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
            if parsed_date >= today_date.today() and parsed_date.weekday() in available_day_nums and parsed_date not in leave_dates:
                slots = get_available_slots(doctor, parsed_date)
        except ValueError:
            parsed_date = None

    if request.method == 'POST':
        slot_time = request.POST.get('slot')
        if slot_time and parsed_date:
            try:
                start = datetime.strptime(slot_time, '%H:%M').time()
            except ValueError:
                messages.error(request, 'Invalid time slot.')
                return redirect(request.path + f'?date={selected_date}')

            avail = DoctorAvailability.objects.filter(
                doctor=doctor, day_of_week=parsed_date.weekday()
            ).order_by('start_time').first()
            if avail:
                end_dt = datetime.combine(parsed_date, start) + timedelta(minutes=avail.slot_duration)
                end = end_dt.time()
            else:
                end = start

            followup = Appointment.objects.create(
                patient=original.patient,
                doctor=doctor,
                date=parsed_date,
                start_time=start,
                end_time=end,
                status='confirmed',  # auto-confirmed since doctor is assigning it
                patient_email=original.patient.email or '',
                patient_phone=original.patient.phone or '',
                follow_up_of=original,
            )

            notify(original.patient,
                   f'A follow-up appointment has been scheduled for you with {doctor} '
                   f'on {parsed_date} at {start.strftime("%I:%M %p")}. '
                   f'Ref: {followup.appointment_ref}')
            if original.patient.email:
                send_email_notification(
                    original.patient.email,
                    'Follow-Up Appointment Scheduled — Addis Clinic',
                    f'Dear {original.patient.get_full_name() or original.patient.username},\n\n'
                    f'A follow-up appointment has been scheduled for you.\n\n'
                    f'=== Follow-Up Details ===\n'
                    f'Ref        : {followup.appointment_ref}\n'
                    f'Doctor     : {doctor}\n'
                    f'Specialty  : {doctor.specialization or "General"}\n'
                    f'Date       : {parsed_date.strftime("%A, %B %d %Y")}\n'
                    f'Time       : {start.strftime("%I:%M %p")}\n'
                    f'Status     : CONFIRMED\n\n'
                    f'Original Appointment Ref: {original.appointment_ref}\n\n'
                    f'Please arrive on time.\n\nAddis Clinic'
                )
            messages.success(request, f'Follow-up appointment {followup.appointment_ref} scheduled for {parsed_date}.')
            return redirect('doctor_dashboard')
        else:
            messages.error(request, 'Please select a time slot.')

    return render(request, 'core/doctor_followup.html', {
        'original': original,
        'doctor': doctor,
        'availabilities': availabilities,
        'upcoming_dates': upcoming_dates,
        'selected_date': selected_date,
        'parsed_date': parsed_date,
        'slots': slots,
    })


@role_required('admin')
def admin_doctors(request):
    from django.db.models import Prefetch, Count
    from .models import DoctorAvailability
    # Group doctors under their specialization, annotate with schedule count
    specializations = Specialization.objects.prefetch_related(
        Prefetch(
            'doctorprofile_set',
            queryset=DoctorProfile.objects.select_related('user').annotate(
                schedule_count=Count('availabilities')
            ).order_by('user__first_name'),
            to_attr='doctors'
        )
    ).order_by('name')
    unassigned = DoctorProfile.objects.filter(specialization__isnull=True).select_related('user').annotate(
        schedule_count=Count('availabilities')
    ).order_by('user__first_name')
    return render(request, 'core/admin_doctors.html', {
        'specializations': specializations,
        'unassigned': unassigned,
    })


@role_required('admin')
def admin_toggle_doctor_availability(request, doctor_id):
    """Admin toggles a doctor's is_available flag."""
    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    if request.method == 'POST':
        doctor.is_available = not doctor.is_available
        doctor.save(update_fields=['is_available'])
        status = 'available' if doctor.is_available else 'unavailable'
        notify(doctor.user, f'Your availability status has been set to {status.upper()} by the admin.')
        messages.success(request, f'{doctor} marked as {status}.')
    return redirect('admin_doctors')


@role_required('admin')
def admin_add_doctor(request):
    from .models import User
    import re

    errors = {}
    form_data = {}

    if request.method == 'POST':
        username   = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        email      = request.POST.get('email', '').strip()
        phone      = request.POST.get('phone', '').strip()
        password   = request.POST.get('password', '')
        spec_id    = request.POST.get('specialization', '')
        new_spec   = request.POST.get('new_specialization', '').strip()
        bio        = request.POST.get('bio', '')

        form_data = {
            'username': username, 'first_name': first_name, 'last_name': last_name,
            'email': email, 'phone': phone, 'bio': bio,
            'specialization': spec_id, 'new_specialization': new_spec,
        }

        if not re.match(r'^[A-Za-z]{3,30}$', first_name):
            errors['first_name'] = 'First name must be letters only, 3–30 characters.'
        if not re.match(r'^[A-Za-z]{3,30}$', last_name):
            errors['last_name'] = 'Last name must be letters only, 3–30 characters.'
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]{2,9}$', username):
            errors['username'] = 'Username must start with a letter, 3–10 chars, letters/numbers/underscore only.'
        elif User.objects.filter(username=username).exists():
            errors['username'] = 'Username already taken.'
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors['email'] = 'Enter a valid email address.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'This email is already registered.'
        if phone and not re.match(r'^\+?[0-9]{7,15}$', phone):
            errors['phone'] = 'Enter a valid phone number (7–15 digits).'
        if len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        elif not re.search(r'[A-Z]', password):
            errors['password'] = 'Password must contain at least 1 uppercase letter.'
        elif not re.search(r'[a-z]', password):
            errors['password'] = 'Password must contain at least 1 lowercase letter.'
        elif not re.search(r'[0-9]', password):
            errors['password'] = 'Password must contain at least 1 number.'
        elif not re.search(r'[\W_]', password):
            errors['password'] = 'Password must contain at least 1 special character.'

        # Validate new specialization if selected
        if spec_id == 'new':
            if not new_spec:
                errors['new_specialization'] = 'Please enter a specialization name.'
            elif not re.match(r'^[A-Za-z\s\(\)&\-]{3,100}$', new_spec):
                errors['new_specialization'] = 'Specialization must be letters only, 3–100 characters.'
            elif Specialization.objects.filter(name__iexact=new_spec).exists():
                errors['new_specialization'] = 'This specialization already exists.'

        if not errors:
            user = User.objects.create_user(
                username=username, password=password,
                first_name=first_name, last_name=last_name,
                email=email, phone=phone, role='doctor', is_active=True
            )
            if spec_id == 'new' and new_spec:
                spec, _ = Specialization.objects.get_or_create(name=new_spec)
            else:
                spec = Specialization.objects.filter(id=spec_id).first()
            DoctorProfile.objects.create(user=user, specialization=spec, bio=bio)
            try:
                send_email_notification(
                    email,
                    'Your Doctor Account — Addis Clinic',
                    f'Dear Dr. {first_name} {last_name},\n\n'
                    f'Your doctor account has been created on Addis Clinic.\n\n'
                    f'=== Login Credentials ===\n'
                    f'Full Name : Dr. {first_name} {last_name}\n'
                    f'Username  : {username}\n'
                    f'Password  : {password}\n'
                    f'Role      : Doctor\n'
                    f'Login URL : http://127.0.0.1:8000/login/\n\n'
                    f'Please log in and change your password immediately after first login.\n\n'
                    f'Best regards,\nAddis Clinic Administration'
                )
                messages.success(request, f'Dr. {first_name} {last_name} added. Credentials sent to {email}.')
            except Exception as e:
                messages.warning(request, f'Dr. {first_name} {last_name} added, but email failed: {e}. Please share credentials manually.')
            return redirect('admin_doctors')

    specializations = Specialization.objects.all().order_by('name')
    return render(request, 'core/admin_add_doctor.html', {
        'specializations': specializations,
        'errors': errors,
        'form_data': form_data,
    })



@role_required('admin')
def admin_edit_doctor(request, doctor_id):
    import re
    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    errors = {}

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        email      = request.POST.get('email', '').strip()
        phone      = request.POST.get('phone', '').strip()
        spec_id    = request.POST.get('specialization', '')
        new_spec   = request.POST.get('new_specialization', '').strip()
        bio        = request.POST.get('bio', '')

        if not re.match(r'^[A-Za-z]{3,30}$', first_name):
            errors['first_name'] = 'First name must be letters only, 3–30 characters.'
        if not re.match(r'^[A-Za-z]{3,30}$', last_name):
            errors['last_name'] = 'Last name must be letters only, 3–30 characters.'
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors['email'] = 'Enter a valid email address.'
        elif doctor.user.email != email and doctor.user.__class__.objects.filter(email=email).exists():
            errors['email'] = 'This email is already registered to another user.'
        if phone and not re.match(r'^\+?[0-9]{7,15}$', phone):
            errors['phone'] = 'Enter a valid phone number (7–15 digits).'
        if spec_id == 'new':
            if not new_spec:
                errors['new_specialization'] = 'Please enter a specialization name.'
            elif not re.match(r'^[A-Za-z\s\(\)&\-]{3,100}$', new_spec):
                errors['new_specialization'] = 'Specialization must be letters only, 3–100 characters.'

        if not errors:
            doctor.user.first_name = first_name
            doctor.user.last_name  = last_name
            doctor.user.email      = email
            doctor.user.phone      = phone
            doctor.user.save()

            if spec_id == 'new' and new_spec:
                doctor.specialization, _ = Specialization.objects.get_or_create(name=new_spec)
            else:
                doctor.specialization = Specialization.objects.filter(id=spec_id).first()
            doctor.bio          = bio
            doctor.is_available = request.POST.get('is_available') == 'on'
            doctor.save()
            messages.success(request, 'Doctor updated successfully.')
            return redirect('admin_doctors')

    specializations = Specialization.objects.all().order_by('name')
    return render(request, 'core/admin_edit_doctor.html', {
        'doctor': doctor,
        'specializations': specializations,
        'errors': errors,
    })


@role_required('admin')
def admin_delete_doctor(request, doctor_id):
    from .models import DoctorReplacementQueue
    doctor = get_object_or_404(DoctorProfile, id=doctor_id)

    # Get all active appointments for this doctor
    active_appointments = Appointment.objects.filter(
        doctor=doctor,
        status__in=['pending', 'confirmed', 'rescheduled']
    ).select_related('patient')

    # Find replacement doctors in same specialization (excluding this doctor)
    replacement_doctors = DoctorProfile.objects.filter(
        specialization=doctor.specialization,
        is_available=True
    ).exclude(id=doctor.id) if doctor.specialization else DoctorProfile.objects.none()

    # Check if there are any doctors at all in this specialization
    any_doctors_in_spec = DoctorProfile.objects.filter(
        specialization=doctor.specialization
    ).exclude(id=doctor.id).exists() if doctor.specialization else False

    if request.method == 'POST':
        action = request.POST.get('action', 'cancel')  # default to cancel
        replacement_id = request.POST.get('replacement_doctor')
        replacement = DoctorProfile.objects.filter(id=replacement_id).first() if replacement_id else None

        doctor_name = str(doctor)
        doctor_email = doctor.user.email
        spec_name = str(doctor.specialization) if doctor.specialization else 'General'

        # Process each active appointment
        for appt in active_appointments:
            patient = appt.patient

            if action == 'replace' and replacement:
                # Reassign appointment to replacement doctor
                appt.doctor = replacement
                appt.status = 'pending'  # Reset to pending for new doctor to confirm
                appt.save()

                # Notify patient
                notify(patient, f'Your appointment with {doctor_name} has been reassigned to {replacement}. '
                               f'Same date ({appt.date}) and time ({appt.start_time.strftime("%I:%M %p")}). '
                               f'Please wait for the new doctor\'s confirmation.')
                if patient.email:
                    try:
                        send_email_notification(
                            patient.email,
                            'Doctor Change — Your Appointment Has Been Reassigned',
                            f'Dear {patient.get_full_name() or patient.username},\n\n'
                            f'Your doctor ({doctor_name}) is no longer available.\n\n'
                            f'Your appointment has been reassigned to:\n'
                            f'New Doctor  : {replacement}\n'
                            f'Specialization: {spec_name}\n'
                            f'Date        : {appt.date}\n'
                            f'Time        : {appt.start_time.strftime("%I:%M %p")}\n'
                            f'Status      : Pending (awaiting new doctor confirmation)\n\n'
                            f'Please log in to check your appointment status.\n\nAddis Clinic'
                        )
                    except Exception:
                        pass

                # Notify new doctor
                notify(replacement.user, f'You have been assigned a new appointment from {patient.get_full_name() or patient.username} '
                                        f'on {appt.date} at {appt.start_time.strftime("%I:%M %p")} (transferred from {doctor_name}).')

            else:
                # No replacement — cancel appointment and add to waiting queue
                appt.status = 'cancelled'
                appt.save()

                if any_doctors_in_spec:
                    # There are doctors in this spec but none free right now — add to queue
                    DoctorReplacementQueue.objects.create(
                        patient=patient,
                        specialization=doctor.specialization,
                        original_doctor_name=doctor_name,
                        original_date=appt.date,
                        original_time=appt.start_time,
                        status='waiting'
                    )
                    notify(patient, f'Your appointment with {doctor_name} has been cancelled. '
                                   f'We are looking for an available {spec_name} doctor for you. '
                                   f'You will be notified as soon as one becomes available.')
                    # Notify all admins to manually assign
                    from .models import User as UserModel
                    admins = UserModel.objects.filter(Q(role='admin') | Q(is_superuser=True), is_active=True)
                    for admin_user in admins:
                        notify(admin_user, f'ACTION REQUIRED: {patient.get_full_name() or patient.username} needs a '
                                          f'replacement {spec_name} doctor (was: {doctor_name}, date: {appt.date} at {appt.start_time.strftime("%I:%M %p")}). '
                                          f'Go to Replacement Queue to assign → /admin-dashboard/replacement-queue/')
                    if patient.email:
                        try:
                            send_email_notification(
                                patient.email,
                                'Appointment Cancelled — Waiting for Replacement Doctor',
                                f'Dear {patient.get_full_name() or patient.username},\n\n'
                                f'We regret to inform you that your doctor ({doctor_name}) is no longer available.\n\n'
                                f'Your appointment on {appt.date} at {appt.start_time.strftime("%I:%M %p")} has been cancelled.\n\n'
                                f'We are actively searching for an available {spec_name} specialist for you.\n'
                                f'You will receive a notification as soon as a replacement is assigned.\n\n'
                                f'We apologize for the inconvenience.\n\nAddis Clinic'
                            )
                        except Exception:
                            pass
                else:
                    # No doctors at all in this specialization
                    notify(patient, f'Your appointment with {doctor_name} has been cancelled. '
                                   f'Unfortunately, there are currently no {spec_name} doctors available in our system. '
                                   f'Please contact the clinic directly or book with a different specialization.')
                    if patient.email:
                        try:
                            send_email_notification(
                                patient.email,
                                'Appointment Cancelled — No Available Doctors',
                                f'Dear {patient.get_full_name() or patient.username},\n\n'
                                f'We regret to inform you that your doctor ({doctor_name}) is no longer available.\n\n'
                                f'Your appointment on {appt.date} at {appt.start_time.strftime("%I:%M %p")} has been cancelled.\n\n'
                                f'Unfortunately, there are currently no {spec_name} specialists available in our system.\n'
                                f'Please contact us directly or consider booking with a different specialization.\n\n'
                                f'We sincerely apologize for the inconvenience.\n\nAddis Clinic'
                            )
                        except Exception:
                            pass

        # Notify the doctor being removed
        if doctor_email:
            try:
                send_email_notification(
                    doctor_email,
                    'Account Removal Notice — Addis Clinic',
                    f'Dear {doctor_name},\n\n'
                    f'This is to inform you that your doctor account has been removed from the Addis Clinic system '
                    f'by the administrator.\n\n'
                    f'All your scheduled appointments have been handled accordingly.\n\n'
                    f'If you believe this is an error, please contact the clinic administration.\n\nAddis Clinic'
                )
            except Exception:
                pass

        # Now delete the doctor (appointments already handled above)
        # Use SET_NULL on appointments instead of CASCADE — update appointment doctor to null first
        Appointment.objects.filter(doctor=doctor).update(doctor=None)
        doctor.user.delete()  # This cascades to DoctorProfile, availability, etc.

        messages.success(request, f'Dr. {doctor_name} has been removed. All affected patients have been notified.')
        return redirect('admin_doctors')

    # GET — show confirmation page with options
    return render(request, 'core/admin_confirm_delete.html', {
        'doctor': doctor,
        'active_appointments': active_appointments,
        'replacement_doctors': replacement_doctors,
        'any_doctors_in_spec': any_doctors_in_spec,
        'spec_name': str(doctor.specialization) if doctor.specialization else 'General',
    })


# ---------- Medical Records ----------

@role_required('doctor')
def add_visit_notes(request, appointment_id):
    """Doctor adds notes only — admin/receptionist marks as completed."""
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor=doctor)

    # Block if appointment hasn't happened yet
    appointment_dt = datetime.combine(appointment.date, appointment.start_time)
    if datetime.now() < appointment_dt:
        messages.error(request, 'Cannot add notes before the appointment time.')
        return redirect('doctor_dashboard')

    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        appointment.notes = notes
        appointment.save(update_fields=['notes', 'updated_at'])
        messages.success(request, 'Visit notes saved.')
        return redirect('doctor_dashboard')

    return render(request, 'core/visit_notes.html', {'appointment': appointment})


@role_required('patient')
def patient_medical_history(request):
    month_filter = request.GET.get('month', '')
    status_filter = request.GET.get('status', '')

    appointments = Appointment.objects.filter(
        patient=request.user
    ).select_related('doctor__user', 'doctor__specialization').order_by('-date', '-start_time')

    if month_filter:
        try:
            year, month = month_filter.split('-')
            appointments = appointments.filter(date__year=int(year), date__month=int(month))
        except Exception:
            pass
    if status_filter:
        appointments = appointments.filter(status=status_filter)

    months_with_data = Appointment.objects.filter(patient=request.user).dates('date', 'month', order='DESC')

    clear_options = [
        ('Last Week', 'week'), ('Last Month', 'month'), ('Last 3 Months', '3months'),
        ('Last 6 Months', '6months'), ('Last Year', 'year'), ('Clear All History', 'all'),
    ]
    return render(request, 'core/medical_history.html', {
        'appointments': appointments,
        'clear_options': clear_options,
        'months_with_data': months_with_data,
        'month_filter': month_filter,
        'status_filter': status_filter,
        'status_choices': Appointment.STATUS_CHOICES,
    })


@role_required('doctor')
def doctor_today_schedule(request):
    from .models import DoctorAvailability
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    today = today_date.today()
    day_of_week = today.weekday()

    # Today's booked appointments
    appointments = Appointment.objects.filter(
        doctor=doctor, date=today
    ).exclude(status='cancelled').order_by('start_time')

    # Today's availability slots
    availability = DoctorAvailability.objects.filter(
        doctor=doctor, day_of_week=day_of_week
    ).order_by('start_time').first()
    slots = get_available_slots(doctor, today) if availability else []

    day_names = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

    return render(request, 'core/doctor_today.html', {
        'appointments': appointments,
        'availability': availability,
        'slots': slots,
        'today': today,
        'day_name': day_names[day_of_week],
    })


@role_required('doctor')
def doctor_upcoming(request):
    doctor = get_object_or_404(DoctorProfile, user=request.user)
    upcoming = Appointment.objects.filter(
        doctor=doctor,
        date__gt=today_date.today(),
        status__in=['confirmed', 'pending']
    ).order_by('date', 'start_time')
    return render(request, 'core/doctor_upcoming.html', {'upcoming': upcoming, 'now': datetime.now()})


# ---------- Profile & Password ----------

@login_required
def profile_view(request):
    import re
    errors = {}

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        email      = request.POST.get('email', '').strip()
        phone      = request.POST.get('phone', '').strip()

        if not re.match(r'^[A-Za-z]{3,30}$', first_name):
            errors['first_name'] = 'First name must be letters only, 3–30 characters.'
        if not re.match(r'^[A-Za-z]{3,30}$', last_name):
            errors['last_name'] = 'Last name must be letters only, 3–30 characters.'
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors['email'] = 'Enter a valid email address.'
        elif request.user.email != email and request.user.__class__.objects.filter(email=email).exists():
            errors['email'] = 'This email is already used by another account.'
        if phone and not re.match(r'^\+?[0-9]{7,15}$', phone):
            errors['phone'] = 'Enter a valid phone number (7–15 digits).'

        if not errors:
            user = request.user
            user.first_name = first_name
            user.last_name  = last_name
            user.email      = email
            user.phone      = phone
            user.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')

    return render(request, 'core/profile.html', {'user': request.user, 'errors': errors})


@login_required
def change_password_view(request):
    if request.method == 'POST':
        current = request.POST.get('current_password')
        new_pass = request.POST.get('new_password')
        confirm = request.POST.get('confirm_password')

        if not request.user.check_password(current):
            messages.error(request, 'Current password is incorrect.')
        elif new_pass != confirm:
            messages.error(request, 'New passwords do not match.')
        else:
            import re
            errors = []
            if len(new_pass) < 8:
                errors.append('at least 8 characters')
            if not re.search(r'[A-Z]', new_pass):
                errors.append('1 uppercase letter')
            if not re.search(r'[a-z]', new_pass):
                errors.append('1 lowercase letter')
            if not re.search(r'[0-9]', new_pass):
                errors.append('1 number')
            if not re.search(r'[\W_]', new_pass):
                errors.append('1 special character')
            if errors:
                messages.error(request, f'Password must contain: {", ".join(errors)}.')
            else:
                request.user.set_password(new_pass)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password changed successfully.')
                return redirect('profile')

    return render(request, 'core/change_password.html')


# ---------- Specialization Management (Admin) ----------

@role_required('admin')
def admin_specializations(request):
    import re
    specs = Specialization.objects.all().order_by('name')
    spec_error = None

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            if not name:
                spec_error = 'Specialization name cannot be empty.'
            elif not re.match(r'^[A-Za-z\s\(\)&\-]{3,100}$', name):
                spec_error = 'Specialization must be letters only, 3–100 characters.'
            elif Specialization.objects.filter(name__iexact=name).exists():
                spec_error = f'"{name}" already exists.'
            else:
                Specialization.objects.create(name=name)
                messages.success(request, f'Specialization "{name}" added.')
                return redirect('admin_specializations')
        elif action == 'delete':
            spec_id = request.POST.get('spec_id')
            Specialization.objects.filter(id=spec_id).delete()
            messages.success(request, 'Specialization deleted.')
            return redirect('admin_specializations')
        elif action == 'edit':
            spec_id = request.POST.get('spec_id')
            name = request.POST.get('name', '').strip()
            if not re.match(r'^[A-Za-z\s\(\)&\-]{3,100}$', name):
                messages.error(request, 'Invalid name. Letters only, 3–100 characters.')
            elif Specialization.objects.filter(name__iexact=name).exclude(id=spec_id).exists():
                messages.error(request, f'"{name}" already exists.')
            else:
                Specialization.objects.filter(id=spec_id).update(name=name)
                messages.success(request, 'Specialization updated.')
            return redirect('admin_specializations')

    return render(request, 'core/admin_specializations.html', {
        'specs': specs,
        'spec_error': spec_error,
    })




# ---------- Chart Data API ----------

@role_required('admin')
def chart_data_api(request):
    from django.http import JsonResponse
    from datetime import timedelta
    import calendar as cal

    period = request.GET.get('period', 'daily')
    now = today_date.today()
    statuses = ['pending', 'confirmed', 'rejected', 'rescheduled', 'cancelled', 'completed']
    colors   = ['#f59e0b', '#22c55e', '#ef4444', '#8b5cf6', '#6b7280', '#3b82f6']

    def get_counts(filter_kwargs):
        result = {}
        # Convert date filters to created_at filters
        converted = {}
        for k, v in filter_kwargs.items():
            if k == 'date':
                converted['created_at__date'] = v
            elif k == 'date__gte':
                converted['created_at__date__gte'] = v
            elif k == 'date__lt':
                converted['created_at__date__lt'] = v
            elif k == 'date__year':
                converted['created_at__year'] = v
            elif k == 'date__month':
                converted['created_at__month'] = v
            else:
                converted[k] = v
        for s in statuses:
            result[s] = Appointment.objects.filter(status=s, **converted).count()
        return result

    labels = []
    datasets_raw = {s: [] for s in statuses}

    if period == 'hourly':
        from datetime import datetime as dt
        now_dt = dt.now()
        for i in range(23, -1, -1):
            hour_start = now_dt - timedelta(hours=i+1)
            hour_end   = now_dt - timedelta(hours=i)
            labels.append(hour_start.strftime('%H:00'))
            counts = {}
            for s in statuses:
                counts[s] = Appointment.objects.filter(
                    status=s, created_at__gte=hour_start, created_at__lt=hour_end
                ).count()
            for s in statuses:
                datasets_raw[s].append(counts[s])

    elif period == 'daily':
        for i in range(6, -1, -1):
            d = now - timedelta(days=i)
            labels.append(d.strftime('%b %d'))
            counts = get_counts({'date': d})
            for s in statuses:
                datasets_raw[s].append(counts[s])

    elif period == 'weekly':
        for i in range(6, -1, -1):
            d = now - timedelta(days=i)
            labels.append(d.strftime('%a %d'))
            counts = get_counts({'date': d})
            for s in statuses:
                datasets_raw[s].append(counts[s])

    elif period == 'lastmonth':
        for i in range(29, -1, -1):
            d = now - timedelta(days=i)
            labels.append(d.strftime('%b %d'))
            counts = get_counts({'date': d})
            for s in statuses:
                datasets_raw[s].append(counts[s])

    elif period == '3months':
        for i in range(12, -1, -1):
            ws = now - timedelta(weeks=i+1)
            we = now - timedelta(weeks=i)
            labels.append(ws.strftime('%b %d'))
            counts = get_counts({'date__gte': ws, 'date__lt': we})
            for s in statuses:
                datasets_raw[s].append(counts[s])

    elif period == '6months':
        for i in range(25, -1, -1):
            ws = now - timedelta(weeks=i+1)
            we = now - timedelta(weeks=i)
            labels.append(ws.strftime('%b %d'))
            counts = get_counts({'date__gte': ws, 'date__lt': we})
            for s in statuses:
                datasets_raw[s].append(counts[s])

    elif period == 'monthly':
        for i in range(11, -1, -1):
            month = now.month - i
            year  = now.year
            while month <= 0:
                month += 12
                year  -= 1
            labels.append(f"{cal.month_abbr[month]} {year}")
            counts = get_counts({'date__year': year, 'date__month': month})
            for s in statuses:
                datasets_raw[s].append(counts[s])

    elif period == 'yearly':
        for month in range(1, 13):
            labels.append(cal.month_abbr[month])
            counts = get_counts({'date__year': now.year, 'date__month': month})
            for s in statuses:
                datasets_raw[s].append(counts[s])

    datasets = []
    for s, color in zip(statuses, colors):
        datasets.append({
            'label': s.capitalize(),
            'data': datasets_raw[s],
            'backgroundColor': color,
            'borderColor': color,
            'borderWidth': 1,
            'borderRadius': 4,
        })

    return JsonResponse({'labels': labels, 'datasets': datasets})


# ---------- Clear History ----------

@role_required('patient')
def clear_history(request):
    from datetime import timedelta

    period = request.GET.get('period') or request.POST.get('period')
    now = today_date.today()

    period_labels = {
        'week': 'Last Week',
        'month': 'Last Month',
        '3months': 'Last 3 Months',
        '6months': 'Last 6 Months',
        'year': 'Last Year',
        'all': 'All History',
    }

    if not period or period not in period_labels:
        return redirect('medical_history')

    # Calculate cutoff
    if period == 'all':
        to_delete = Appointment.objects.filter(patient=request.user)
    else:
        cutoffs = {
            'week': timedelta(weeks=1),
            'month': timedelta(days=30),
            '3months': timedelta(days=90),
            '6months': timedelta(days=180),
            'year': timedelta(days=365),
        }
        cutoff = now - cutoffs[period]
        to_delete = Appointment.objects.filter(patient=request.user, date__lt=cutoff)

    to_delete = to_delete.select_related('doctor__user', 'doctor__specialization').order_by('-date')

    if request.method == 'POST' and request.POST.get('confirm') == 'yes':
        count = to_delete.count()
        to_delete.delete()
        messages.success(request, f'{count} appointment record(s) cleared.')
        return redirect('medical_history')

    return render(request, 'core/clear_history_preview.html', {
        'appointments': to_delete,
        'period': period,
        'period_label': period_labels[period],
        'count': to_delete.count(),
    })


# ---------- Report Generation ----------

@role_required('admin')
def generate_report(request):
    from datetime import timedelta, datetime as dt

    now = today_date.today()
    period = request.GET.get('period', 'month')

    # Custom date range
    custom_value = request.GET.get('custom_value', '1')
    custom_unit = request.GET.get('custom_unit', 'days')

    # Period definitions — all count backwards from TODAY
    period_map = {
        'week':    ('Last 7 Days',     now - timedelta(weeks=1),   now),
        'month':   ('Last 30 Days',    now - timedelta(days=30),   now),
        '3months': ('Last 3 Months',   now - timedelta(days=90),   now),
        '6months': ('Last 6 Months',   now - timedelta(days=180),  now),
        'year':    ('Last 365 Days',   now - timedelta(days=365),  now),
    }

    if period == 'custom':
        try:
            val = int(custom_value)
            if custom_unit == 'weeks':
                delta = timedelta(weeks=val)
                unit_label = f'{val} Week{"s" if val > 1 else ""}'
            elif custom_unit == 'months':
                delta = timedelta(days=val * 30)
                unit_label = f'{val} Month{"s" if val > 1 else ""}'
            else:
                delta = timedelta(days=val)
                unit_label = f'{val} Day{"s" if val > 1 else ""}'
            start_date = now - delta
            end_date = now
            period_label = f'Last {unit_label}'
        except (ValueError, TypeError):
            start_date = now - timedelta(days=30)
            end_date = now
            period_label = 'Last 30 Days'
            custom_value = '30'
            custom_unit = 'days'
    elif period in period_map:
        period_label, start_date, end_date = period_map[period]
    else:
        period_label, start_date, end_date = period_map['month']
        period = 'month'

    appointments = Appointment.objects.filter(
        created_at__date__gte=start_date, created_at__date__lte=end_date
    ).select_related('patient', 'doctor__user', 'doctor__specialization').order_by('date', 'start_time')

    from .models import User as UserModel
    from django.db.models import Count
    from .models import DoctorReplacementQueue

    status_summary = {}
    for s, label in Appointment.STATUS_CHOICES:
        status_summary[label] = appointments.filter(status=s).count()

    doctor_summary = appointments.values(
        'doctor__user__first_name', 'doctor__user__last_name', 'doctor__specialization__name'
    ).annotate(total=Count('id')).order_by('-total')[:10]

    # Additional activity stats for the period
    activity_stats = {
        'New Registrations': UserModel.objects.filter(
            date_joined__date__gte=start_date, date_joined__date__lte=end_date
        ).count(),
        'Pending Registrations': UserModel.objects.filter(
            is_active=False, date_joined__date__gte=start_date, date_joined__date__lte=end_date
        ).count(),
        'Doctor Replacements Queued': DoctorReplacementQueue.objects.filter(
            created_at__date__gte=start_date, created_at__date__lte=end_date
        ).count(),
        'Replacements Assigned': DoctorReplacementQueue.objects.filter(
            status='assigned', created_at__date__gte=start_date, created_at__date__lte=end_date
        ).count(),
        'Total Doctors': DoctorProfile.objects.count(),
        'Active Patients': UserModel.objects.filter(role='patient', is_active=True).count(),
        'Total Specializations': Specialization.objects.count(),
    }

    # System activity stats for the period
    from .models import DoctorReplacementQueue, Notification
    activity_stats = {
        'new_registrations': UserModel.objects.filter(
            date_joined__date__gte=start_date, date_joined__date__lte=end_date
        ).count(),
        'pending_registrations': UserModel.objects.filter(
            is_active=False, date_joined__date__gte=start_date
        ).count(),
        'replacement_queue_items': DoctorReplacementQueue.objects.filter(
            created_at__date__gte=start_date, created_at__date__lte=end_date
        ).count(),
        'notifications_sent': Notification.objects.filter(
            created_at__date__gte=start_date, created_at__date__lte=end_date
        ).count(),
        'doctors_total': DoctorProfile.objects.count(),
        'patients_total': UserModel.objects.filter(role='patient', is_active=True).count(),
        'specializations_total': Specialization.objects.count(),
    }

    period_choices = [
        ('week',    'Last 7 Days'),
        ('month',   'Last 30 Days'),
        ('3months', 'Last 3 Months'),
        ('6months', 'Last 6 Months'),
        ('year',    'Last 365 Days'),
        ('custom',  'Custom Range'),
    ]

    # Doctor availability stats for report
    from .models import DoctorAvailability as DA
    report_avail_stats = []
    for doc in DoctorProfile.objects.select_related('user', 'specialization').prefetch_related('availabilities'):
        avails = doc.availabilities.all()
        days_pw = avails.count()
        mins_pw = sum(
            (a.end_time.hour * 60 + a.end_time.minute) - (a.start_time.hour * 60 + a.start_time.minute)
            for a in avails
        )
        report_avail_stats.append({
            'doctor': doc,
            'days_per_week': days_pw,
            'hours_per_week': round(mins_pw / 60, 1),
            'hours_per_month': round(mins_pw / 60 * 4, 1),
        })

    context = {
        'period_label': period_label,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'appointments': appointments,
        'total_appointments': appointments.count(),
        'status_summary': status_summary,
        'doctor_summary': doctor_summary,
        'activity_stats': activity_stats,
        'total_doctors': DoctorProfile.objects.count(),
        'total_patients': UserModel.objects.filter(role='patient').count(),
        'generated_by': request.user.get_full_name() or request.user.username,
        'generated_at': now,
        'period_choices': period_choices,
        'custom_value': custom_value,
        'custom_unit': custom_unit,
        'report_avail_stats': report_avail_stats,
    }
    return render(request, 'core/report.html', context)


# ---------- Auto-expire past appointments ----------

def auto_expire_appointments():
    """
    Called on doctor/admin dashboard load.
    Marks confirmed appointments as 'completed' if time has passed.
    Marks pending appointments as 'cancelled' if time has passed without doctor action.
    Notifies relevant users.
    """
    now = datetime.now()

    # Confirmed but time passed → auto-complete (doctor can still add notes)
    past_confirmed = Appointment.objects.filter(
        status='confirmed',
        date__lt=today_date.today()
    )
    for appt in past_confirmed:
        appt_dt = datetime.combine(appt.date, appt.end_time)
        if now > appt_dt:
            appt.status = 'completed'
            appt.save()
            notify(appt.patient, f'Your appointment with {appt.doctor} on {appt.date} has been marked as completed.')
            notify(appt.doctor.user, f'Appointment with {appt.patient.get_full_name() or appt.patient.username} on {appt.date} was auto-completed. Add visit notes if needed.')

    # Pending but time passed → auto-cancel (doctor never responded)
    past_pending = Appointment.objects.filter(
        status='pending',
        date__lt=today_date.today()
    )
    for appt in past_pending:
        appt_dt = datetime.combine(appt.date, appt.start_time)
        if now > appt_dt:
            appt.status = 'cancelled'
            appt.save()
            notify(appt.patient, f'Your appointment with {appt.doctor} on {appt.date} was automatically cancelled — the doctor did not respond in time.')
            notify(appt.doctor.user, f'Appointment with {appt.patient.get_full_name() or appt.patient.username} on {appt.date} was auto-cancelled due to no response.')


@role_required('admin')
def admin_replacement_queue(request):
    from .models import DoctorReplacementQueue
    waiting = DoctorReplacementQueue.objects.filter(status='waiting').select_related('patient', 'specialization')
    return render(request, 'core/admin_replacement_queue.html', {'waiting': waiting})


@role_required('admin')
def admin_assign_replacement(request, queue_id):
    from .models import DoctorReplacementQueue
    item = get_object_or_404(DoctorReplacementQueue, id=queue_id)

    if request.method == 'POST':
        doctor_id = request.POST.get('doctor_id')
        new_doctor = get_object_or_404(DoctorProfile, id=doctor_id)

        # Create new appointment
        new_appt = Appointment.objects.create(
            patient=item.patient,
            doctor=new_doctor,
            date=item.original_date,
            start_time=item.original_time,
            end_time=item.original_time,
            status='pending'
        )

        item.status = 'assigned'
        item.assigned_doctor = new_doctor
        item.save()

        # Notify patient
        notify(item.patient, f'Good news! A replacement doctor has been found for you. '
                            f'{new_doctor} ({item.specialization}) will see you on {item.original_date} '
                            f'at {item.original_time.strftime("%I:%M %p")}. Awaiting doctor confirmation.')
        if item.patient.email:
            try:
                send_email_notification(
                    item.patient.email,
                    'Replacement Doctor Assigned — Addis Clinic',
                    f'Dear {item.patient.get_full_name() or item.patient.username},\n\n'
                    f'We are pleased to inform you that a replacement doctor has been assigned to you.\n\n'
                    f'New Doctor     : {new_doctor}\n'
                    f'Specialization : {item.specialization}\n'
                    f'Date           : {item.original_date}\n'
                    f'Time           : {item.original_time.strftime("%I:%M %p")}\n'
                    f'Status         : Pending doctor confirmation\n\n'
                    f'Please log in to check your appointment status.\n\nAddis Clinic'
                )
            except Exception:
                pass

        # Notify new doctor
        notify(new_doctor.user, f'You have been assigned a new patient: {item.patient.get_full_name() or item.patient.username} '
                               f'on {item.original_date} at {item.original_time.strftime("%I:%M %p")}.')

        messages.success(request, f'Replacement assigned. {item.patient.username} has been notified.')
        return redirect('admin_replacement_queue')

    # Get ALL doctors in same specialization (available or not) with their schedules
    available_doctors = DoctorProfile.objects.filter(
        specialization=item.specialization, is_available=True
    ).select_related('user').prefetch_related('availabilities')
    return render(request, 'core/admin_assign_replacement.html', {
        'item': item,
        'available_doctors': available_doctors,
    })
