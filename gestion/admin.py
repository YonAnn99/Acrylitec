from django.contrib import admin

# Importamos tus clases para que el admin las reconozca
from .models import Clientes, Materiales, Productos, Cotizaciones, Ventas, TabuladorCostos

# Registros del sitio
admin.site.register(Clientes)
admin.site.register(Materiales)
admin.site.register(Productos)
admin.site.register(Cotizaciones)
admin.site.register(Ventas)
admin.site.register(TabuladorCostos)
