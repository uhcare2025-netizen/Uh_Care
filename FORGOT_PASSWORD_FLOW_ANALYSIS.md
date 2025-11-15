# Forgot Password Flow Analysis

## Current Status: ⚠️ INCOMPLETE

The forgot password system is **partially implemented**. While the backend is set up, **custom frontend templates are missing**, so users see Django's default admin-styled templates.

---

## Architecture Overview

### 1. **URL Configuration** ✅
**Location**: `/config/urls.py`

```python
path('accounts/password_reset/', PasswordResetNotifyView.as_view(), name='password_reset'),
path('accounts/', include('django.contrib.auth.urls')),  # Includes: reset_done, reset_confirm, reset_complete
```

**Available Routes**:
- `/accounts/password_reset/` — Password reset request form (custom view)
- `/accounts/password_reset/done/` — Confirmation after email sent (Django default)
- `/accounts/password_reset/<uidb64>/<token>/` — Password reset form with token (Django default)
- `/accounts/password_reset/complete/` — Success confirmation (Django default)

---

### 2. **Custom View** ✅
**Location**: `/apps/accounts/views.py` (lines 21-48)

```python
class PasswordResetNotifyView(PasswordResetView):
    """Notifies site admins when a reset is requested."""
    
    def form_valid(self, form):
        # Gathers: email, IP address, user-agent, timestamp
        # Sends admin notification via mail_admins()
        # Calls parent form_valid() to process password reset
        mail_admins(subject, message, fail_silently=True)
        return super().form_valid(form)
```

**Features**:
- Sends email notification to admins when password reset is requested
- Includes: email, IP address, user-agent, timestamp, request path
- Fails silently (won't break user flow if mail_admins fails)

---

### 3. **Frontend Templates** ❌ MISSING

**Currently Used**: Django's default admin templates (unstyled, not branded)

**Missing Templates**:
1. `registration/password_reset_form.html` — Form to enter email
2. `registration/password_reset_done.html` — Confirmation after email sent
3. `registration/password_reset_confirm.html` — Form to set new password
4. `registration/password_reset_complete.html` — Success message
5. `registration/password_reset_email.html` — Email body content (text version)
6. `registration/password_reset_subject.txt` — Email subject line

**Login Page Link** ✅
`/apps/accounts/templates/accounts/login.html` (line 183)
```html
<p><a href="{% url 'password_reset' %}">Forgot Password?</a></p>
```

---

### 4. **Email Configuration** ✅
**Location**: `config/settings.py`

**Current Setup**:
```python
# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Prints to console in DEBUG
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')

# Admin notification
ADMINS = [('Adarsh Thapa', 'adarshthapa9090@gmail.com')]
```

**Status**:
- ✅ Console backend active (development)
- ✅ SMTP configured for production
- ✅ ADMINS configured for notifications

---

### 5. **User Authentication** ✅
**Location**: `/apps/accounts/models.py`

**Custom User Model Features**:
- Custom backend supports login via **username OR email**
- Password management built-in (Django default)
- Supports both patients and providers

---

## Complete User Flow

### **Step 1: User Clicks "Forgot Password"**
```
Login Page → Click "Forgot Password?" link
            → /accounts/password_reset/
```

### **Step 2: Enter Email (PASSWORD_RESET_FORM)**
```
URL: /accounts/password_reset/
Template: registration/password_reset_form.html ❌ MISSING
Form: PasswordResetForm (Django built-in)
- Input: Email address
- Processing:
  1. Validates email exists in User model
  2. If exists:
     a. Admin notification sent (custom)
     b. Password reset email sent to user
     c. Redirect to password_reset_done
  3. If not exists:
     - Still redirects to password_reset_done (for security)
```

### **Step 3: Confirmation Message (PASSWORD_RESET_DONE)**
```
URL: /accounts/password_reset/done/
Template: registration/password_reset_done.html ❌ MISSING
Message: "Email sent with password reset link"
- User checks their email (usually takes 1-2 minutes)
```

### **Step 4: Click Email Link**
```
Email: From: settings.DEFAULT_FROM_EMAIL
       To: user.email
       Subject: registration/password_reset_subject.txt ❌ MISSING
       Body: registration/password_reset_email.html ❌ MISSING
       
Link: /accounts/password_reset/<uidb64>/<token>/
      (uidb64 = encoded user ID, token = one-time reset token)
```

### **Step 5: Set New Password (PASSWORD_RESET_CONFIRM)**
```
URL: /accounts/password_reset/<uidb64>/<token>/
Template: registration/password_reset_confirm.html ❌ MISSING
Form: SetPasswordForm (Django built-in)
- Inputs: new password, confirm password
- Validation:
  1. Token must be valid (expires in 1-3 days)
  2. Passwords must match
  3. Password must meet Django requirements
- On success: redirect to password_reset_complete
```

### **Step 6: Success Confirmation (PASSWORD_RESET_COMPLETE)**
```
URL: /accounts/password_reset/complete/
Template: registration/password_reset_complete.html ❌ MISSING
Message: "Password reset complete. You can now login."
```

---

## Implementation Checklist

### ✅ Backend (Complete)
- [x] Custom User model with email/username login
- [x] PasswordResetNotifyView with admin notifications
- [x] URL routes configured
- [x] Email backend configured (console + SMTP)
- [x] Login page has "Forgot Password" link
- [x] Django built-in forms working

### ❌ Frontend (Missing)
- [ ] `registration/password_reset_form.html` — Request email form
- [ ] `registration/password_reset_done.html` — Email sent confirmation
- [ ] `registration/password_reset_confirm.html` — New password form
- [ ] `registration/password_reset_complete.html` — Success page
- [ ] `registration/password_reset_email.html` — Email body template
- [ ] `registration/password_reset_subject.txt` — Email subject template

---

## What Happens Now

**Current Behavior** (Without Custom Templates):
1. User clicks "Forgot Password?" → Uses Django's default form ❌
2. User enters email → Email is sent ✅
3. User clicks email link → Uses Django's default form ❌
4. User sets password → Password is reset ✅
5. User sees success page → Django default styling ❌

**Admin Notification** ✅
- Admins receive email when reset is requested
- Includes: email, IP, user-agent, timestamp, path

---

## Recommended Next Steps

### Priority 1: Create Custom Templates (UX)
Create 6 new templates matching UH Care branding:
1. Email template with branded logo and professional messaging
2. Forms matching login page styling
3. Confirmation pages with clear CTAs

### Priority 2: Improve Email Content (Product)
- Professional email subject line
- Clear instructions and security messaging
- Company branding and contact info

### Priority 3: Security Enhancements
- Add rate limiting on password reset requests
- Log failed password reset attempts
- Add 2FA option (optional)

### Priority 4: Testing
- Test on development (console backend)
- Test email delivery on PythonAnywhere
- Test token expiration
- Test invalid/expired tokens

---

## Related Files

**Backend**:
- `/apps/accounts/views.py` — PasswordResetNotifyView
- `/apps/accounts/urls.py` — Route to password change (not reset)
- `/config/urls.py` — Password reset routes
- `/config/settings.py` — Email configuration, ADMINS

**Frontend**:
- `/apps/accounts/templates/accounts/login.html` — "Forgot Password?" link
- `/apps/accounts/templates/accounts/password_change.html` — Change password (when logged in)

**Django Built-in** (Used as fallback):
- `django.contrib.auth.views.PasswordResetView`
- `django.contrib.auth.forms.PasswordResetForm`
- `django.contrib.auth.forms.SetPasswordForm`
- Default templates in `venv/lib/python3.13/site-packages/django/contrib/auth/templates/`

---

## Summary

| Component | Status | Notes |
|-----------|--------|-------|
| URL Routes | ✅ Complete | 4 routes configured |
| Custom View | ✅ Complete | Notifies admins |
| Email Backend | ✅ Complete | Console (dev) + SMTP (prod) |
| Forms | ✅ Complete | Django built-in forms |
| Templates | ❌ Missing | 6 templates needed |
| Login Link | ✅ Complete | Points to password_reset |
| User Model | ✅ Complete | Supports email/username login |

**Overall**: The forgot password system is **functionally complete** but **lacks professional branding**. Users can reset their passwords, but they see unstyled Django default pages instead of UH Care branded templates.
