import re
from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    def validate(self, password, user=None):
        pattern_upper = r'[A-Z]'
        pattern_lower = r'[a-z]'
        pattern_digit = r'[0-9]'
        pattern_special = r'[\W_]'

        if not re.search(pattern_upper, password):
            raise ValidationError("Must contain at least 1 uppercase letter")
        if not re.search(pattern_lower, password):
            raise ValidationError("Must contain at least 1 lowercase letter")
        if not re.search(pattern_digit, password):
            raise ValidationError("Must contain at least 1 number")
        if not re.search(pattern_special, password):
            raise ValidationError("Must contain at least 1 special character")

    def get_help_text(self):
        return "Your password must include uppercase, lowercase, number, and special character."


def validate_doctor_form(post_data, user_model, existing_user=None):
    """
    Validates doctor creation/edit form data.
    Returns dict of errors (empty if valid).
    """
    errors = {}
    name_pattern = r'^[A-Za-z]{3,30}$'
    username_pattern = r'^[A-Za-z][A-Za-z0-9_]{2,9}$'
    email_pattern = r'^[^@]+@[^@]+\.[^@]+$'
    phone_pattern = r'^\+?[0-9]{7,15}$'

    first_name = post_data.get('first_name', '').strip()
    last_name  = post_data.get('last_name', '').strip()
    username   = post_data.get('username', '').strip()
    email      = post_data.get('email', '').strip()
    phone      = post_data.get('phone', '').strip()
    password   = post_data.get('password', '')

    if not re.match(name_pattern, first_name):
        errors['first_name'] = 'First name must be letters only, 3–30 characters.'

    if not re.match(name_pattern, last_name):
        errors['last_name'] = 'Last name must be letters only, 3–30 characters.'

    if username:
        if not re.match(username_pattern, username):
            errors['username'] = 'Username must start with a letter, 3–10 chars, letters/numbers/underscore only.'
        elif user_model.objects.filter(username=username).exclude(
            pk=existing_user.pk if existing_user else None
        ).exists():
            errors['username'] = 'Username already taken.'

    if not re.match(email_pattern, email):
        errors['email'] = 'Enter a valid email address.'
    elif user_model.objects.filter(email=email).exclude(
        pk=existing_user.pk if existing_user else None
    ).exists():
        errors['email'] = 'This email is already registered.'

    if phone and not re.match(phone_pattern, phone):
        errors['phone'] = 'Enter a valid phone number (7–15 digits).'

    if password:
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

    return errors
