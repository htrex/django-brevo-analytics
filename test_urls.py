from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('brevo-analytics/', include('brevo_analytics.urls')),
]
