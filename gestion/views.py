import os
import uuid
import datetime
import json
import urllib.parse
from decimal import Decimal, ROUND_HALF_UP

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from django.conf import settings
from reportlab.platypus import Image as RLImage
import io
from django.contrib import messages

from .models import (
    Materiales, Clientes, Cotizaciones, Productos,
    TabuladorCostos, Ventas, ConfiguracionPrecios
)
# ── Helpers de rol ──────────────────────────────────────────
def es_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name='Administrador').exists()
    )

def es_operador(user):
    return user.is_authenticated

# ── Login / Logout ──────────────────────────────────────────
def login_view(request):
    error = None
    
    if request.user.is_authenticated:
         if es_admin(request.user):
            return redirect('dashboard')
         else:
             return redirect('lista_cotizaciones')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            if es_admin(user):
                return redirect('dashboard')
            else:
                return redirect('lista_cotizaciones')         
    else:
            error='Usuario o contraseña incorrectos.'

    return render(request, 'gestion/login.html', {'error': error})

def logout_view(request):
    logout(request)
    request.session.flush()  # ← limpia toda la sesión
    return redirect('login')


# Vistas que TODOS los usuarios autenticados pueden ver:
@login_required
def lista_clientes(request): ...

@login_required
def nueva_cotizacion(request): ...

@login_required
def lista_cotizaciones(request): ...

@login_required
def detalle_venta(request, pk): ...

@login_required
def lista_ventas(request): ...   # la tabla de ventas la pueden ver todos

# Vistas SOLO para Administrador (dinero, reportes, precios):
@login_required
@user_passes_test(es_admin, login_url='/sin-permiso/')
def dashboard(request): ...      # gráficas + KPIs financieros

@login_required
@user_passes_test(es_admin, login_url='/sin-permiso/')
def configuracion_precios(request): ...

def sin_permiso(request):
    return render(request, 'gestion/sin_permiso.html')

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────

def _get_tarifa_laser():
    return ConfiguracionPrecios.get_config().tarifa_laser_minuto


def _calcular_monto(largo, ancho, espesor_mm, porcentaje_utilidad, minutos_laser=0, producto_id=None):
    largo = Decimal(str(largo or 0))
    ancho = Decimal(str(ancho or 0))
    minutos_laser = Decimal(str(minutos_laser or 0))
    porcentaje_utilidad = Decimal(str(porcentaje_utilidad or 40))

    area_cm2 = largo * ancho
    area_m2 = area_cm2 / Decimal('10000')

    if producto_id:
            prod = Productos.objects.filter(pk=producto_id).first()
            if prod and prod.precio_fijo:
                return {
                    'area': largo * ancho,
                    'area_m2': (largo * ancho) / Decimal('10000'),
                    'costo_material': Decimal('0.00'),
                    'utilidad': Decimal('0.00'),
                    'costo_laser': Decimal('0.00'),
                    'monto_total': prod.precio_fijo,
                }

    try:
        tabulador = TabuladorCostos.objects.get(espesor_mm=espesor_mm)
        factor = tabulador.factor_costo
    except TabuladorCostos.DoesNotExist:
        factor = Decimal('0.00')

    costo_material = area_m2 * factor
    utilidad = costo_material * (porcentaje_utilidad / Decimal('100'))
    costo_laser = minutos_laser * _get_tarifa_laser()
    
    monto_total = (costo_material + utilidad + costo_laser).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )

    return {
        'area': area_cm2,
        'area_m2': area_m2,
        'costo_material': costo_material.quantize(Decimal('0.01')),
        'utilidad': utilidad.quantize(Decimal('0.01')),
        'costo_laser': costo_laser.quantize(Decimal('0.01')),
        'monto_total': monto_total,
    }


# ─────────────────────────────────────────
#  CLIENTES
# ─────────────────────────────────────────

def lista_clientes(request):
    query = request.GET.get('q', '')
    clientes = Clientes.objects.all()
    if query:
        clientes = clientes.filter(
            Q(nombre__icontains=query) |
            Q(telefono__icontains=query) |
            Q(email__icontains=query)
        )
    return render(request, 'gestion/clientes_list.html', {
        'clientes': clientes,
        'query': query
    })


def crear_cliente(request):
    if request.method == 'POST':
        Clientes.objects.create(
            nombre=request.POST.get('nombre'),
            telefono=request.POST.get('telefono'),
            email=request.POST.get('email'),
            direccion=request.POST.get('direccion')
        )
        return redirect('lista_clientes')
    return render(request, 'gestion/cliente_form.html')


# ─────────────────────────────────────────
#  MATERIALES
# ─────────────────────────────────────────

def lista_materiales(request):
    query = request.GET.get('q', '')
    materiales = Materiales.objects.all()
    if query:
        materiales = materiales.filter(descripcion__icontains=query)
    materiales_bajos = sum(1 for m in materiales if m.stock_actual <= m.stock_minimo)
    return render(request, 'gestion/materiales_list.html', {
        'materiales':      materiales,
        'query':           query,
        'materiales_bajos': materiales_bajos,
    })


def crear_material(request):
    if request.method == 'POST':
        Materiales.objects.create(
            descripcion=request.POST.get('descripcion'),
            largo=request.POST.get('largo'),
            ancho=request.POST.get('ancho'),
            stock_actual=request.POST.get('stock'),
            stock_minimo=request.POST.get('stock_minimo')
        )
        return redirect('lista_materiales')
    return render(request, 'gestion/material_form.html')


def eliminar_material(request, id):
    material = get_object_or_404(Materiales, pk=id)

    # Contar referencias activas en cotizaciones y detalles de venta
    from .models import DetalleVenta
    cot_count   = Cotizaciones.objects.filter(id_material=material).count()
    det_count   = DetalleVenta.objects.filter(id_material=material).count()
    tiene_refs  = cot_count + det_count

    if request.method == 'POST':
        if tiene_refs:
            messages.error(request,
                f'No se puede eliminar "{material.descripcion}": '
                f'tiene {cot_count} cotización(es) y {det_count} venta(s) asociadas.')
            return redirect('lista_materiales')
        try:
            material.delete()
            messages.success(request, f'Material "{material.descripcion}" eliminado correctamente.')
        except Exception as e:
            messages.error(request, f'No se pudo eliminar: {e}')
        return redirect('lista_materiales')

    # GET → pantalla de confirmación
    return render(request, 'gestion/material_confirm_delete.html', {
        'material':   material,
        'tiene_refs': tiene_refs,
        'cot_count':  cot_count,
        'det_count':  det_count,
    })


# ─────────────────────────────────────────
#  PRODUCTOS
# ─────────────────────────────────────────

def lista_productos(request):
    query = request.GET.get('q', '')  # Captura el texto del buscador
    productos = Productos.objects.all()
    
    if query:
        # Filtra por nombre o detalle (ignora mayúsculas/minúsculas)
        productos = productos.filter(
            Q(nombre__icontains=query) | 
            Q(detalle__icontains=query)
        )
        
    return render(request, 'gestion/productos_list.html', {
        'productos': productos,
        'query': query
    })


def crear_producto(request):
    if request.method == 'POST':
        precio_fijo = request.POST.get('precio_fijo') or None
        foto_path = None
        if 'foto' in request.FILES:
            foto = request.FILES['foto']
            ext = os.path.splitext(foto.name)[1]
            foto_path = default_storage.save(f"productos/{uuid.uuid4().hex}{ext}", foto)

        Productos.objects.create(
            nombre=request.POST.get('nombre'),
            detalle=request.POST.get('detalle'),
            porcentaje_utilidad=request.POST.get('porcentaje_utilidad') or 40,
            precio_fijo=precio_fijo,
            foto=foto_path,
        )
        return redirect('lista_productos')
    return render(request, 'gestion/producto_form.html', {'accion': 'Crear'})


def editar_producto(request, pk):
    producto = get_object_or_404(Productos, pk=pk)
    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre')
        producto.detalle = request.POST.get('detalle')
        producto.porcentaje_utilidad = request.POST.get('porcentaje_utilidad') or 40
        producto.precio_fijo = request.POST.get('precio_fijo') or None
        if 'foto' in request.FILES:
            foto = request.FILES['foto']
            ext = os.path.splitext(foto.name)[1]
            if producto.foto:
                try:
                    default_storage.delete(producto.foto)
                except Exception:
                    pass
            producto.foto = default_storage.save(
                f"productos/{uuid.uuid4().hex}{ext}", foto)
        producto.save()
        return redirect('lista_productos')
    return render(request, 'gestion/producto_form.html',
                  {'accion': 'Editar', 'producto': producto})


def eliminar_producto(request, pk):
    producto = get_object_or_404(Productos, pk=pk)
    if request.method == 'POST':
        if producto.foto:
            try:
                default_storage.delete(producto.foto)
            except Exception:
                pass
        producto.delete()
        return redirect('lista_productos')
    return render(request, 'gestion/producto_confirm_delete.html',
                  {'producto': producto})


# ─────────────────────────────────────────
#  MÓDULO UNIFICADO: NUEVO PEDIDO
# ─────────────────────────────────────────

def nuevo_pedido(request):
    clientes = Clientes.objects.all()
    productos = Productos.objects.all()
    materiales = Materiales.objects.all()
    materiales_tabulador = TabuladorCostos.objects.order_by('espesor_mm')

    if request.method == 'POST':
        # 🌟 NUEVA LÓGICA: Recibimos el carrito por JSON (Fetch API)
        if request.headers.get('Content-Type') == 'application/json':
            try:
                data = json.loads(request.body)
                cliente = get_object_or_404(Clientes, pk=data.get('cliente_id'))
                monto_abonado = Decimal(str(data.get('monto_abonado') or 0))
                
                # 1. Crear la Venta Maestra (guardamos el cliente directamente)
                venta = Ventas.objects.create(
                    id_cliente=cliente,
                    monto_abonado=monto_abonado,
                    estatus=data.get('estatus', 'pendiente'),
                    fecha_entrega=data.get('fecha_entrega') or None,
                    fecha_venta=datetime.date.today(),
                )

                # 2. Guardar cada producto del carrito en DetalleVenta
                from .models import DetalleVenta
                alertas_stock = []  # Materiales que quedan por debajo del mínimo

                for item in data.get('carrito', []):
                    producto = get_object_or_404(Productos, pk=item['producto_id'])
                    material = get_object_or_404(Materiales, pk=item['material_id'])
                    cantidad  = int(item.get('cantidad', 1))

                    # Convertimos comas a puntos por si acaso antes de hacer el Decimal
                    sub_str = str(item.get('subtotal') or 0).replace(',', '.')

                    DetalleVenta.objects.create(
                        id_venta=venta,
                        id_producto=producto,
                        id_material=material,
                        cantidad=cantidad,
                        largo_pza=item.get('largo') or 0,
                        ancho_pza=item.get('ancho') or 0,
                        espesor_mm=item.get('espesor') or 0,
                        minutos_lazer=item.get('minutos_laser') or 0,
                        subtotal=Decimal(sub_str)
                    )

                    # ── Descontar stock ──────────────────────────────────
                    material.stock_actual = max(0, material.stock_actual - cantidad)
                    material.save(update_fields=['stock_actual'])

                    # Verificar si quedó por debajo del mínimo
                    if material.stock_actual <= material.stock_minimo:
                        alertas_stock.append({
                            'nombre':   material.descripcion,
                            'actual':   material.stock_actual,
                            'minimo':   material.stock_minimo,
                        })

                # Devolvemos éxito, ruta al ticket y alertas de stock bajo
                return JsonResponse({
                    'ok': True,
                    'venta_id': venta.id_venta,
                    'alertas_stock': alertas_stock,
                })
            except Exception as e:
                return JsonResponse({'ok': False, 'error': str(e)})

    return render(request, 'gestion/venta_directa.html', {
        'clientes': clientes,
        'productos': productos,
        'materiales': materiales,
        'materiales_tabulador': materiales_tabulador,
        'tarifa_laser': _get_tarifa_laser(),
    })


# ─────────────────────────────────────────
#  COTIZACIONES
# ─────────────────────────────────────────

def calcular_precio_ajax(request):
    if request.method == 'POST':
        try:
            largo = request.POST.get('largo_pza') or 0
            ancho = request.POST.get('ancho_pza') or 0
            producto = Productos.objects.get(pk=request.POST.get('producto'))
            minutos = request.POST.get('minutos_lazer') or 0
            calculo = _calcular_monto(largo, ancho, producto, minutos)
            return JsonResponse({'ok': True,
                'area': str(calculo['area']),
                'costo_material': str(calculo['costo_material']),
                'utilidad': str(calculo['utilidad']),
                'costo_laser': str(calculo['costo_laser']),
                'monto_total': str(calculo['monto_total']),
            })
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e)})
    return JsonResponse({'ok': False})


# ─────────────────────────────────────────
#  VENTAS
# ─────────────────────────────────────────

def _total_venta(venta):
    """Calcula el total de una venta sin importar si es POS o cotización."""
    if venta.id_cotizacion_id:
        return venta.id_cotizacion.monto_total or Decimal('0')
    return sum(d.subtotal for d in venta.detalles.all()) or Decimal('0')

def _cliente_nombre(venta):
    """Resuelve nombre del cliente para POS (id_cliente) y cotización legacy."""
    if venta.id_cotizacion_id and venta.id_cotizacion.id_cliente:
        return venta.id_cotizacion.id_cliente.nombre
    if venta.id_cliente_id:
        return venta.id_cliente.nombre
    return '—'

def _producto_nombre(venta):
    """Resuelve nombre del producto (uno o varios del carrito)."""
    if venta.id_cotizacion_id and venta.id_cotizacion.id_producto:
        return venta.id_cotizacion.id_producto.nombre
    detalles = list(venta.detalles.all())
    if len(detalles) == 1:
        return detalles[0].id_producto.nombre
    elif len(detalles) > 1:
        return f'{detalles[0].id_producto.nombre} +{len(detalles)-1} más'
    return '—'

def lista_ventas(request):
    ventas = Ventas.objects.select_related(
        'id_cotizacion__id_cliente',
        'id_cotizacion__id_producto',
        'id_cliente',
    ).prefetch_related('detalles__id_producto').order_by('-fecha_venta', '-id_venta')

    ESTATUS_COBRADO = ('pagada', 'entregada')
    total_ingresos = sum(
        _total_venta(v)
        for v in ventas
        if v.estatus in ESTATUS_COBRADO
    )

    resumen = {
        'total_ventas':   ventas.count(),
        'total_ingresos': total_ingresos,
        'pendientes':     ventas.filter(estatus='pendiente').count(),
        'en_produccion':  ventas.filter(estatus='en_produccion').count(),
        'entregadas':     ventas.filter(estatus='entregada').count(),
    }

    for v in ventas:
        v.total_calculado = _total_venta(v)
        v.cliente_nombre  = _cliente_nombre(v)
        v.producto_nombre = _producto_nombre(v)

    return render(request, 'gestion/ventas_list.html',
                  {'ventas': ventas, 'resumen': resumen})


def detalle_venta(request, pk):
    venta = get_object_or_404(Ventas.objects.select_related(
        'id_cotizacion__id_cliente', 'id_cotizacion__id_producto',
        'id_cotizacion__id_material'), pk=pk)
    return render(request, 'gestion/venta_detalle.html', {'venta': venta})


def actualizar_estatus_venta(request, pk):
    venta = get_object_or_404(Ventas, pk=pk)
    if request.method == 'POST':
        nuevo = request.POST.get('estatus')
        if nuevo in ['pendiente','en_produccion', 'pagada', 'entregada']:
            venta.estatus = nuevo
        fecha = request.POST.get('fecha_entrega')
        if fecha:
            venta.fecha_entrega = fecha
        venta.save()
    return redirect('detalle_venta', pk=pk)

def actualizar_abono_venta(request, pk):
    venta = get_object_or_404(Ventas, pk=pk)
    if request.method == 'POST':
        nuevo_abono = request.POST.get('monto_abonado')
        try:
            venta.monto_abonado = Decimal(nuevo_abono)
            venta.save()
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return redirect('detalle_venta', pk=pk)

# ─────────────────────────────────────────
#  AJAX: CREAR CLIENTE DESDE POS
# ─────────────────────────────────────────

def crear_cliente_ajax(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            nombre = data.get('nombre')
            
            if not nombre:
                return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio'})

            # Crear el cliente en la base de datos
            nuevo_cliente = Clientes.objects.create(
                nombre=nombre,
                telefono=data.get('telefono'),
                email=data.get('email'),
                direccion=data.get('direccion')
            )
            
            # Devolver el ID y el nombre para que el Select2 lo pueda mostrar
            return JsonResponse({
                'ok': True, 
                'id_cliente': nuevo_cliente.id_cliente,
                'nombre': nuevo_cliente.nombre
            })
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e)})
            
    return JsonResponse({'ok': False, 'error': 'Método no permitido'})

# ─────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────

def _get_total_venta_val(venta):
    """Total real de una venta: usa cotizacion legacy O suma DetalleVenta."""
    if venta.id_cotizacion_id:
        return float(venta.id_cotizacion.monto_total or 0)
    return float(sum(d.subtotal for d in venta.detalles.all()) or 0)

def dashboard(request):
    hoy = datetime.date.today()
    ESTATUS_INGRESO = ('pagada', 'entregada')   # ambos cuentan como cobrado

    # Traer TODAS las ventas con sus detalles (para el cálculo híbrido)
    todas_ventas = (Ventas.objects
                    .select_related('id_cotizacion__id_producto',
                                    'id_cotizacion__id_cliente')
                    .prefetch_related('detalles__id_producto')
                    .order_by('fecha_venta'))

    # ── Calcular totales por venta en Python (híbrido POS + cotización) ───
    from collections import defaultdict
    from datetime import date

    meses_data   = defaultdict(float)   # key: (year, month)
    semanas_data = defaultdict(float)   # key: (year, iso_week, week_start_date)
    anios_data   = defaultdict(float)   # key: year

    for v in todas_ventas:
        if v.estatus not in ESTATUS_INGRESO:
            continue
        if not v.fecha_venta:
            continue
        total = _get_total_venta_val(v)
        y  = v.fecha_venta.year
        m  = v.fecha_venta.month
        iso_week = v.fecha_venta.isocalendar()[1]
        # Inicio de semana (lunes)
        week_start = v.fecha_venta - datetime.timedelta(days=v.fecha_venta.weekday())

        meses_data[(y, m)]              += total
        semanas_data[(y, iso_week, week_start)] += total
        anios_data[y]                   += total

    # ── Construir dicts para los pickers ─────────────────────────────────
    import calendar
    MESES_ES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

    meses_por_anio = {}
    for (y, m), total in sorted(meses_data.items()):
        key = str(y)
        if key not in meses_por_anio:
            meses_por_anio[key] = {'labels': [], 'data': []}
        label = f"{MESES_ES[m-1]} {y}"
        meses_por_anio[key]['labels'].append(label)
        meses_por_anio[key]['data'].append(round(total, 2))

    semanas_por_anio = {}
    for (y, wn, ws), total in sorted(semanas_data.items()):
        key = str(y)
        if key not in semanas_por_anio:
            semanas_por_anio[key] = {'labels': [], 'data': []}
        semanas_por_anio[key]['labels'].append(f"Semana {wn} ({ws.strftime('%d/%m')})")
        semanas_por_anio[key]['data'].append(round(total, 2))

    labels_anio = [str(y) for y in sorted(anios_data.keys())]
    data_anio   = [round(anios_data[int(y)], 2) for y in labels_anio]

    # ── KPIs ─────────────────────────────────────────────────────────────
    inicio_mes = hoy.replace(day=1)
    ingresos_mes   = sum(_get_total_venta_val(v) for v in todas_ventas
                         if v.estatus in ESTATUS_INGRESO and v.fecha_venta and v.fecha_venta >= inicio_mes)
    ingresos_total = sum(_get_total_venta_val(v) for v in todas_ventas
                         if v.estatus in ESTATUS_INGRESO)

    kpis = {
        'ingresos_mes':    Decimal(str(round(ingresos_mes, 2))),
        'ventas_mes':      sum(1 for v in todas_ventas if v.fecha_venta and v.fecha_venta >= inicio_mes),
        'ingresos_total':  Decimal(str(round(ingresos_total, 2))),
        'ventas_total':    todas_ventas.count(),
        'clientes_total':  Clientes.objects.count(),
        'cotizaciones_mes': Cotizaciones.objects.filter(fecha__gte=inicio_mes).count(),
    }

    # ── Pedidos activos (pendiente + en producción) ───────────────────────
    pedidos_activos_qs = (Ventas.objects
                          .filter(estatus__in=['pendiente', 'en_produccion'])
                          .select_related('id_cotizacion__id_cliente',
                                          'id_cotizacion__id_producto',
                                          'id_cliente')
                          .prefetch_related('detalles__id_producto')
                          .order_by('-fecha_venta'))

    # Enriquecer con nombre de cliente/producto usando helpers compartidos
    pedidos_activos = []
    for v in pedidos_activos_qs:
        v.cliente_nombre  = _cliente_nombre(v)
        v.producto_nombre = _producto_nombre(v)
        pedidos_activos.append(v)

    anio_actual = str(hoy.year)

    return render(request, 'gestion/dashboard.html', {
        'kpis':             kpis,
        'pedidos_activos':  pedidos_activos,
        'anio_actual':      anio_actual,
        'meses_por_anio':   json.dumps(meses_por_anio),
        'semanas_por_anio': json.dumps(semanas_por_anio),
        'labels_anio':      json.dumps(labels_anio),
        'data_anio':        json.dumps(data_anio),
    })


@login_required
def nueva_cotizacion(request):
    clientes = Clientes.objects.all()
    productos = Productos.objects.all()
    materiales_tabulador = TabuladorCostos.objects.order_by('espesor_mm') # Para el nuevo select
    
    return render(request, 'gestion/cotizacion_form.html', {
        'clientes': clientes,
        'productos': productos,
        'materiales_tabulador': materiales_tabulador,
        'tarifa_laser': _get_tarifa_laser(),
    })


# ─────────────────────────────────────────
#  CONFIGURACIÓN DE PRECIOS
# ─────────────────────────────────────────

def configuracion_precios(request):
    config = ConfiguracionPrecios.get_config()
    productos = Productos.objects.all()
    tabuladores = TabuladorCostos.objects.order_by('espesor_mm')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'tarifa_laser':
            config.tarifa_laser_minuto = request.POST.get('tarifa_laser_minuto')
            config.save()
        elif accion == 'utilidad_producto':
            Productos.objects.filter(pk=request.POST.get('producto_id')).update(
                porcentaje_utilidad=request.POST.get('porcentaje_utilidad'))
        elif accion == 'factor_costo':
            TabuladorCostos.objects.filter(pk=request.POST.get('tabulador_id')).update(
                factor_costo=request.POST.get('factor_costo'))
        elif accion == 'nuevo_tabulador':
            TabuladorCostos.objects.create(
                espesor_mm=request.POST.get('espesor_mm'),
                factor_costo=request.POST.get('factor_costo_nuevo'))
        return redirect('configuracion_precios')

    return render(request, 'gestion/configuracion_precios.html', {
        'config': config, 'productos': productos, 'tabuladores': tabuladores,
    })