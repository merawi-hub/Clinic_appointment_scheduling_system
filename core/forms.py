import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from .models import User, DoctorProfile, Specialization


def validate_name(value):
    pattern = r'^[A-Za-z]{3,30}$'
    if not re.match(pattern, value):
        raise ValidationError('Name must be letters only (A-Z), min 3 and max 30 characters.')


def validate_username(value):
    pattern = r'^[A-Za-z][A-Za-z0-9_]{2,9}$'
    if not re.match(pattern, value):
        raise ValidationError(
            'Username must start with a letter, be 3-10 characters, '
            'and can only contain letters, numbers, or underscores.'
        )


def validate_phone(value):
    pattern = r'^\+?[0-9]{7,15}$'
    if value and not re.match(pattern, value):
        raise ValidationError('Enter a valid phone number (7-15 digits, optionally starting with +).')


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30, required=True,
        validators=[validate_name],
        widget=forms.TextInput(attrs={'placeholder': 'First name (letters only)', 'class': 'form-control'})
    )
    last_name = forms.CharField(
        max_length=30, required=True,
        validators=[validate_name],
        widget=forms.TextInput(attrs={'placeholder': 'Last name (letters only)', 'class': 'form-control'})
    )
    username = forms.CharField(
        max_length=10, required=True,
        validators=[validate_username],
        widget=forms.TextInput(attrs={'placeholder': 'Username (3-10 chars, start with letter)', 'class': 'form-control'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'Email address', 'class': 'form-control'})
    )
    phone = forms.CharField(
        max_length=15, required=False,
        validators=[validate_phone],
        widget=forms.TextInput(attrs={'placeholder': 'Phone e.g. +251912345678', 'class': 'form-control'})
    )
    role = forms.ChoiceField(
        choices=[('patient', 'Patient')],
        initial='patient',
        widget=forms.HiddenInput()
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'role', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('This email is already registered.')
        return email


class DoctorForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True, validators=[validate_name])
    last_name = forms.CharField(max_length=30, required=True, validators=[validate_name])
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=15, required=False, validators=[validate_phone])

    class Meta:
        model = DoctorProfile
        fields = ['specialization', 'bio', 'is_available']
        widgets = {'bio': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        self.user_instance = kwargs.pop('user_instance', None)
        super().__init__(*args, **kwargs)
        if self.user_instance:
            self.fields['first_name'].initial = self.user_instance.first_name
            self.fields['last_name'].initial = self.user_instance.last_name
            self.fields['email'].initial = self.user_instance.email
            self.fields['phone'].initial = self.user_instance.phone
