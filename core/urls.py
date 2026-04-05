from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
  # Aquí conectamos las rutas de tu aplicación Acrylitec
    path('', include('gestion.urls')), 
]