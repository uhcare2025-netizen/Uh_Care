from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.accounts.views import PasswordResetNotifyView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Custom accounts app (includes login, register, profile, etc.)
    # This must come BEFORE django.contrib.auth.urls so custom views take precedence
    path('', include('apps.accounts.urls')),
    # Override the default password-reset form so site admins can be notified
    # when a user requests a password reset.
    path('accounts/password_reset/', PasswordResetNotifyView.as_view(), name='password_reset'),
    # Include Django's built-in auth views for password reset flows and other views
    # (Note: login is handled by custom view in apps.accounts.urls)
    path('accounts/', include('django.contrib.auth.urls')),
    path('services/', include('apps.services.urls')),
    path('appointments/', include('apps.appointments.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
    path('payments/', include('apps.payments.urls')),
    # Phase 2 modules
    path('pharmacy/', include('apps.pharmacy.urls')),
    path('equipment/', include('apps.equipment.urls')),
    # Notifications
    path('notifications/', include('apps.notifications.urls')),
    # Blog
    path('blog/', include('apps.blog.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin site customization
admin.site.site_header = "UH Care Administration"
admin.site.site_title = "UH Care Admin Portal"
admin.site.index_title = "Welcome to UH Care Admin Portal"