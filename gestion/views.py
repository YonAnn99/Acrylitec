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

from .models import (
    Materiales, Clientes, Cotizaciones, Productos,
    TabuladorCostos, Ventas, ConfiguracionPrecios
)


# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────

def _get_tarifa_laser():
    return ConfiguracionPrecios.get_config().tarifa_laser_minuto


def _calcular_monto(largo, ancho, producto, minutos_laser=0):
    largo = Decimal(str(largo))
    ancho = Decimal(str(ancho))
    minutos_laser = Decimal(str(minutos_laser or 0))
    area = largo * ancho
    tabulador = TabuladorCostos.objects.order_by('espesor_mm').first()
    factor = tabulador.factor_costo if tabulador else Decimal('100.00')
    costo_material = area * factor
    utilidad = costo_material * (Decimal(str(producto.porcentaje_utilidad)) / Decimal('100'))
    costo_laser = minutos_laser * _get_tarifa_laser()
    monto_total = (costo_material + utilidad + costo_laser).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    return {
        'area': area,
        'costo_material': costo_material.quantize(Decimal('0.01')),
        'utilidad': utilidad.quantize(Decimal('0.01')),
        'costo_laser': costo_laser.quantize(Decimal('0.01')),
        'monto_total': monto_total,
    }


# ─────────────────────────────────────────
#  CLIENTES
# ─────────────────────────────────────────

def lista_clientes(request):
    return render(request, 'gestion/clientes_list.html',
                  {'clientes': Clientes.objects.all()})


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
    return render(request, 'gestion/materiales_list.html',
                  {'materiales': Materiales.objects.all()})


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
    Materiales.objects.get(id_material=id).delete()
    return redirect('lista_materiales')


# ─────────────────────────────────────────
#  PRODUCTOS
# ─────────────────────────────────────────

def lista_productos(request):
    return render(request, 'gestion/productos_list.html',
                  {'productos': Productos.objects.all()})


def crear_producto(request):
    if request.method == 'POST':
        foto_path = None
        if 'foto' in request.FILES:
            foto = request.FILES['foto']
            ext = os.path.splitext(foto.name)[1]
            foto_path = default_storage.save(f"productos/{uuid.uuid4().hex}{ext}", foto)

        Productos.objects.create(
            nombre=request.POST.get('nombre'),
            detalle=request.POST.get('detalle'),
            porcentaje_utilidad=request.POST.get('porcentaje_utilidad'),
            foto=foto_path,
        )
        return redirect('lista_productos')
    return render(request, 'gestion/producto_form.html', {'accion': 'Crear'})


def editar_producto(request, pk):
    producto = get_object_or_404(Productos, pk=pk)
    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre')
        producto.detalle = request.POST.get('detalle')
        producto.porcentaje_utilidad = request.POST.get('porcentaje_utilidad')
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
#  COTIZACIONES
# ─────────────────────────────────────────

def lista_cotizaciones(request):
    cotizaciones = Cotizaciones.objects.select_related(
        'id_cliente', 'id_producto', 'id_material'
    ).order_by('-fecha', '-id_cotizacion')
    return render(request, 'gestion/cotizaciones_list.html',
                  {'cotizaciones': cotizaciones})


def crear_cotizacion(request):
    clientes = Clientes.objects.all()
    productos = Productos.objects.all()
    materiales = Materiales.objects.all()
    tarifa_laser = _get_tarifa_laser()

    if request.method == 'POST':
        cliente = get_object_or_404(Clientes, pk=request.POST.get('cliente'))
        producto = get_object_or_404(Productos, pk=request.POST.get('producto'))
        material = get_object_or_404(Materiales, pk=request.POST.get('material'))
        largo = request.POST.get('largo_pza')
        ancho = request.POST.get('ancho_pza')
        minutos_laser = request.POST.get('minutos_lazer') or 0
        calculo = _calcular_monto(largo, ancho, producto, minutos_laser)
        cotizacion = Cotizaciones.objects.create(
            id_cliente=cliente, id_producto=producto, id_material=material,
            largo_pza=largo, ancho_pza=ancho, minutos_lazer=minutos_laser,
            monto_total=calculo['monto_total'], fecha=datetime.date.today(),
        )
        return redirect('detalle_cotizacion', pk=cotizacion.id_cotizacion)

    return render(request, 'gestion/cotizacion_form.html', {
        'clientes': clientes, 'productos': productos,
        'materiales': materiales, 'tarifa_laser': tarifa_laser,
    })


def detalle_cotizacion(request, pk):
    cotizacion = get_object_or_404(
        Cotizaciones.objects.select_related('id_cliente', 'id_producto', 'id_material'), pk=pk)
    calculo = _calcular_monto(
        cotizacion.largo_pza, cotizacion.ancho_pza,
        cotizacion.id_producto, cotizacion.minutos_lazer)
    venta_existente = Ventas.objects.filter(id_cotizacion=cotizacion).first()

    cliente = cotizacion.id_cliente
    telefono = (cliente.telefono or '').replace(' ', '').replace('-', '').replace('+', '')
    if telefono and not telefono.startswith('52'):
        telefono = '52' + telefono
    mensaje = (
        f"Hola {cliente.nombre}, te compartimos tu cotización Acrylitec "
        f"#COT-{cotizacion.id_cotizacion:04d}.\n"
        f"Producto: {cotizacion.id_producto.nombre}\n"
        f"Material: {cotizacion.id_material.descripcion}\n"
        f"Medidas: {cotizacion.largo_pza}m × {cotizacion.ancho_pza}m\n"
        f"Total: ${cotizacion.monto_total} MXN\n"
        f"Fecha: {cotizacion.fecha}\n¡Estamos a tus órdenes!"
    )
    whatsapp_url = f"https://wa.me/{telefono}?text={urllib.parse.quote(mensaje)}"
    return render(request, 'gestion/cotizacion_detalle.html', {
        'cotizacion': cotizacion, 'calculo': calculo,
        'whatsapp_url': whatsapp_url, 'venta_existente': venta_existente,
    })


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

def registrar_venta(request, cotizacion_pk):
    cotizacion = get_object_or_404(Cotizaciones, pk=cotizacion_pk)
    venta_existente = Ventas.objects.filter(id_cotizacion=cotizacion).first()
    if venta_existente:
        return redirect('detalle_venta', pk=venta_existente.id_venta)
    if request.method == 'POST':
        venta = Ventas.objects.create(
            id_cotizacion=cotizacion,
            monto_pagado=request.POST.get('monto_pagado') or cotizacion.monto_total,
            estatus=request.POST.get('estatus', 'en_produccion'),
            fecha_entrega=request.POST.get('fecha_entrega') or None,
            fecha_venta=datetime.date.today(),
        )
        return redirect('detalle_venta', pk=venta.id_venta)
    return render(request, 'gestion/venta_form.html', {'cotizacion': cotizacion})


def lista_ventas(request):
    ventas = Ventas.objects.select_related(
        'id_cotizacion__id_cliente', 'id_cotizacion__id_producto',
    ).order_by('-fecha_venta', '-id_venta')
    resumen = {
        'total_ventas': ventas.count(),
        'total_ingresos': ventas.aggregate(s=Sum('monto_pagado'))['s'] or Decimal('0'),
        'en_produccion': ventas.filter(estatus='en_produccion').count(),
        'entregadas': ventas.filter(estatus='entregada').count(),
    }
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
        if nuevo in ['en_produccion', 'pagada', 'entregada']:
            venta.estatus = nuevo
        fecha = request.POST.get('fecha_entrega')
        if fecha:
            venta.fecha_entrega = fecha
        venta.save()
    return redirect('detalle_venta', pk=pk)


# ─────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────

def dashboard(request):
    hoy = datetime.date.today()
    ventas_qs = Ventas.objects.select_related('id_cotizacion__id_producto')

    por_mes = (ventas_qs.filter(fecha_venta__gte=hoy - datetime.timedelta(days=180))
               .annotate(periodo=TruncMonth('fecha_venta'))
               .values('periodo').annotate(total=Sum('monto_pagado'), cantidad=Count('id_venta'))
               .order_by('periodo'))
    por_semana = (ventas_qs.filter(fecha_venta__gte=hoy - datetime.timedelta(weeks=8))
                  .annotate(periodo=TruncWeek('fecha_venta'))
                  .values('periodo').annotate(total=Sum('monto_pagado'), cantidad=Count('id_venta'))
                  .order_by('periodo'))
    por_anio = (ventas_qs.filter(fecha_venta__gte=hoy - datetime.timedelta(days=365 * 3))
                .annotate(periodo=TruncYear('fecha_venta'))
                .values('periodo').annotate(total=Sum('monto_pagado'), cantidad=Count('id_venta'))
                .order_by('periodo'))

    top_productos = (ventas_qs.values('id_cotizacion__id_producto__nombre')
                     .annotate(total=Sum('monto_pagado'), cantidad=Count('id_venta'))
                     .order_by('-cantidad')[:5])

    inicio_mes = hoy.replace(day=1)
    ventas_mes = ventas_qs.filter(fecha_venta__gte=inicio_mes)
    kpis = {
        'ingresos_mes': ventas_mes.aggregate(s=Sum('monto_pagado'))['s'] or Decimal('0'),
        'ventas_mes': ventas_mes.count(),
        'ingresos_total': ventas_qs.aggregate(s=Sum('monto_pagado'))['s'] or Decimal('0'),
        'ventas_total': ventas_qs.count(),
        'clientes_total': Clientes.objects.count(),
        'cotizaciones_mes': Cotizaciones.objects.filter(fecha__gte=inicio_mes).count(),
    }

    labels_mes    = [v['periodo'].strftime('%b %Y')         for v in por_mes]
    data_mes      = [float(v['total'] or 0)                 for v in por_mes]
    labels_semana = [f"Sem {v['periodo'].strftime('%d/%m')}" for v in por_semana]
    data_semana   = [float(v['total'] or 0)                 for v in por_semana]
    labels_anio   = [v['periodo'].strftime('%Y')            for v in por_anio]
    data_anio     = [float(v['total'] or 0)                 for v in por_anio]



    return render(request, 'gestion/dashboard.html', {
        'kpis':         kpis,
        'top_productos': top_productos,

        # ── Versiones JSON seguras para usar en <script> ──────────────────
        'labels_mes':    json.dumps(labels_mes),
        'data_mes':      json.dumps(data_mes),
        'labels_semana': json.dumps(labels_semana),
        'data_semana':   json.dumps(data_semana),
        'labels_anio':   json.dumps(labels_anio),
        'data_anio':     json.dumps(data_anio),
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