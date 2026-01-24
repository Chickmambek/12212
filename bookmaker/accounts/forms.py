from django import forms
from .models import Profile
from django.contrib.auth.models import User


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=200)
    country = forms.ChoiceField(choices=Profile.COUNTRIES)
    currency = forms.ChoiceField(choices=Profile.CURRENCIES)
    email = forms.EmailField()
    promo_code = forms.CharField(max_length=100, required=False)
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    # validation for passwords
    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")

        if password != confirm:
            raise forms.ValidationError("Пароли не совпадают!")

        return cleaned

    # email unique check
    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Этот email уже используется")
        return email
