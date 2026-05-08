from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # ── Dashboard ───────────────────────────────────────────
    path('', views.login_view, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # ── Materiales ──────────────────────────────────────────
    path('materiales/', views.lista_materiales, name='lista_materiales'),
    path('materiales/nuevo/', views.crear_material, name='crear_material'),
    path('materiales/eliminar/<int:id>/', views.eliminar_material, name='eliminar_material'),

    # ── Clientes ────────────────────────────────────────────
    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('clientes/nuevo/', views.crear_cliente, name='crear_cliente'),

    # ── Productos ───────────────────────────────────────────
    path('productos/', views.lista_productos, name='lista_productos'),
    path('productos/nuevo/', views.crear_producto, name='crear_producto'),
    path('productos/<int:pk>/editar/', views.editar_producto, name='editar_producto'),
    path('productos/<int:pk>/eliminar/', views.eliminar_producto, name='eliminar_producto'),

    # ── Cotizaciones ────────────────────────────────────────
    #path('cotizaciones/', views.lista_cotizaciones, name='lista_cotizaciones'),
    #path('cotizaciones/nueva/', views.crear_cotizacion, name='crear_cotizacion'),
    #path('cotizaciones/<int:pk>/', views.detalle_cotizacion, name='detalle_cotizacion'),
    #path('cotizaciones/express/', views.cotizacion_express, name='cotizacion_express'),

    # ── Ventas ──────────────────────────────────────────────
    path('ventas/', views.lista_ventas, name='lista_ventas'),
    path('ventas/<int:pk>/', views.detalle_venta, name='detalle_venta'),
    path('ventas/<int:pk>/estatus/', views.actualizar_estatus_venta, name='actualizar_estatus_venta'),
    path('ventas/<int:pk>/abono/', views.actualizar_abono_venta, name='actualizar_abono_venta'),
    #path('cotizaciones/<int:cotizacion_pk>/registrar-venta/', views.registrar_venta, name='registrar_venta'),
    path('pedidos/nuevo/', views.nuevo_pedido, name='nuevo_pedido'),
    #path('ventas/nueva-directa/', views.venta_directa, name='venta_directa'),

    # ── Configuración de Precios ────────────────────────────
    path('configuracion/', views.configuracion_precios, name='configuracion_precios'),

    # ── AJAX ────────────────────────────────────────────────
    path('ajax/calcular/', views.calcular_precio_ajax, name='calcular_precio_ajax'),
    path('ajax/crear-cliente/', views.crear_cliente_ajax, name='crear_cliente_ajax'),


    # ── LOGIN ────────────────────────────────────────────────
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('sin-permiso/', views.sin_permiso, name='sin_permiso'),
]



# Servir archivos de media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)