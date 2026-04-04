from django.contrib import admin
from django.urls import path, include # <--- Asegúrate de importar 'include'

urlpatterns = [
    path('admin/', admin.site.urls),
    # Aquí conectamos las rutas de tu aplicación Acrylitec
    path('', include('gestion.urls')), 
]