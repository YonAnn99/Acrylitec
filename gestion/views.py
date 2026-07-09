import os
import uuid
import datetime
import json
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation  # Agrega InvalidOperation aquí
from django.core.cache import cache

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings

from .models import (
    Materiales, Clientes, Cotizaciones, Productos,
    TabuladorCostos, Ventas, ConfiguracionPrecios, DetalleVenta
    
)


# --- VALIDACIONES DE SEGURIDAD ---
EXTENSIONES_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
TAMANO_MAXIMO_MB = 5

def _obtener_tipo_real(archivo):
    """Lee los primeros bytes para descubrir el tipo real de la imagen."""
    cabecera = archivo.read(32)
    archivo.seek(0)  # 🔴 CRÍTICO: Regresar el puntero al inicio para que Django pueda guardar el archivo después
    
    if cabecera.startswith(b'\xff\xd8'):
        return 'jpeg'
    elif cabecera.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    elif cabecera.startswith(b'GIF87a') or cabecera.startswith(b'GIF89a'):
        return 'gif'
    elif cabecera.startswith(b'RIFF') and b'WEBP' in cabecera[:16]:
        return 'webp'
    return None

def _validar_imagen(archivo):
    ext = os.path.splitext(archivo.name)[1].lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        raise ValueError(f"Extensión no permitida: {ext}. Solo se aceptan imágenes.")
    
    tipo_real = _obtener_tipo_real(archivo)
    if not tipo_real:
        raise ValueError("El archivo no es una imagen válida o está corrupto.")
    
    if archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024:
        raise ValueError(f"La imagen no puede superar {TAMANO_MAXIMO_MB} MB.")
    
    return ext

# ── Helpers de rol ──────────────────────────────────────────
def es_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name='Administrador').exists()
    )

@login_required
def crear_producto_rapido(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            nombre = data.get('nombre')
            utilidad = data.get('utilidad', 40)
            precio_fijo = data.get('precio_fijo')

            if not nombre:
                return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio.'})

            precio_val = Decimal(precio_fijo) if precio_fijo else None
            
            # Crear el producto en la base de datos
            nuevo_prod = Productos.objects.create(
                nombre=nombre,
                detalle=data.get('descripcion', ''),
                porcentaje_utilidad=Decimal(utilidad),
                precio_fijo=precio_val
            )

            return JsonResponse({
                'ok': True,
                'id': nuevo_prod.id_producto,
                'nombre': nuevo_prod.nombre,
                'precio_fijo': str(nuevo_prod.precio_fijo) if nuevo_prod.precio_fijo else ''
            })
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e)})
            
    return JsonResponse({'ok': False, 'error': 'Método no permitido'})

# ── Login / Logout ──────────────────────────────────────────
def login_view(request):
    error = None
    
    if request.user.is_authenticated:
         if es_admin(request.user):
            return redirect('dashboard')
         else:
             return redirect('lista_ventas')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            if es_admin(user):
                return redirect('dashboard')
            else:
                return redirect('lista_ventas')         
    else:
            error='Usuario o contraseña incorrectos.'

    return render(request, 'gestion/login.html', {'error': error})

def logout_view(request):
    logout(request)
    request.session.flush()  # ← limpia toda la sesión
    return redirect('login')


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

@login_required
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


@login_required
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

@login_required
def eliminar_cliente(request, pk):
    cliente = get_object_or_404(Clientes, pk=pk)
    
    # 1. Contar si el cliente tiene historial para evitar errores de integridad
    ventas_count = Ventas.objects.filter(id_cliente=cliente).count()
    cot_count = Cotizaciones.objects.filter(id_cliente=cliente).count()
    tiene_refs = ventas_count + cot_count

    if request.method == 'POST':
        if tiene_refs > 0:
            messages.error(request, f'No se puede eliminar a "{cliente.nombre}" porque tiene {ventas_count} venta(s) y {cot_count} cotización(es) asociada(s).')
            return redirect('lista_clientes')
            
        try:
            cliente.delete()
            messages.success(request, f'Cliente "{cliente.nombre}" eliminado correctamente.')
        except Exception as e:
            messages.error(request, f'No se pudo eliminar el cliente: {e}')
            
        return redirect('lista_clientes')

    # Si es GET, mostramos la pantalla de confirmación
    return render(request, 'gestion/cliente_confirm_delete.html', {
        'cliente': cliente,
        'tiene_refs': tiene_refs,
        'ventas_count': ventas_count,
        'cot_count': cot_count,
    })


# ─────────────────────────────────────────
#  MATERIALES
# ─────────────────────────────────────────

@login_required
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


@login_required
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


@login_required
def eliminar_material(request, id):
    material = get_object_or_404(Materiales, pk=id)

    # Contar referencias activas en cotizaciones y detalles de venta
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
#  INVENTARIO (Productos con precio fijo)
# ─────────────────────────────────────────

@login_required
def inventario_productos(request):
    """Muestra productos que tienen precio_fijo definido, con información de stock."""
    query = request.GET.get('q', '')
    productos = Productos.objects.filter(precio_fijo__isnull=False)
    
    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | 
            Q(detalle__icontains=query)
        )
    
    # Contar productos con stock bajo
    productos_bajos = sum(1 for p in productos if p.stock_actual <= p.stock_minimo and p.stock_minimo > 0)
    
    return render(request, 'gestion/inventario_list.html', {
        'productos': productos,
        'query': query,
        'productos_bajos': productos_bajos,
    })


@login_required
def editar_stock_producto(request, pk):
    """Permite editar el stock de un producto específico."""
    producto = get_object_or_404(Productos, pk=pk)
    
    if request.method == 'POST':
        producto.stock_actual = int(request.POST.get('stock_actual', 0))
        producto.stock_minimo = int(request.POST.get('stock_minimo', 0))
        producto.save()
        messages.success(request, f'Stock de "{producto.nombre}" actualizado correctamente.')
        return redirect('inventario_productos')
    
    return render(request, 'gestion/editar_stock.html', {
        'producto': producto,
    })


# ─────────────────────────────────────────
#  PRODUCTOS
# ─────────────────────────────────────────

@login_required
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


@login_required
def crear_producto(request):
    if request.method == 'POST':
        precio_fijo = request.POST.get('precio_fijo') or None
        
        # 🔴 REVISA AMBOS BOTONES
        foto_archivo = request.FILES.get('foto') or request.FILES.get('foto_camara')
        foto_path = None
        
        if foto_archivo:
            try:
                ext = _validar_imagen(foto_archivo)
                foto_path = default_storage.save(f"productos/{uuid.uuid4().hex}{ext}", foto_archivo)
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, 'gestion/producto_form.html', {'accion': 'Crear'})

        Productos.objects.create(
            nombre=request.POST.get('nombre'),
            detalle=request.POST.get('detalle'),
            porcentaje_utilidad=request.POST.get('porcentaje_utilidad') or 40,
            precio_fijo=precio_fijo,
            foto=foto_path,
        )
        return redirect('lista_productos')
    return render(request, 'gestion/producto_form.html', {'accion': 'Crear'})


@login_required
def editar_producto(request, pk):
    producto = get_object_or_404(Productos, pk=pk)
    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre')
        producto.detalle = request.POST.get('detalle')
        producto.porcentaje_utilidad = request.POST.get('porcentaje_utilidad') or 40
        producto.precio_fijo = request.POST.get('precio_fijo') or None
        
        # 🔴 REVISA AMBOS BOTONES
        foto_archivo = request.FILES.get('foto') or request.FILES.get('foto_camara')
        
        if foto_archivo:
            try:
                ext = _validar_imagen(foto_archivo)
                if producto.foto:
                    try:
                        default_storage.delete(producto.foto)
                    except Exception:
                        pass
                producto.foto = default_storage.save(f"productos/{uuid.uuid4().hex}{ext}", foto_archivo)
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, 'gestion/producto_form.html', {'accion': 'Editar', 'producto': producto})
                
        producto.save()
        return redirect('lista_productos')
    return render(request, 'gestion/producto_form.html',
                  {'accion': 'Editar', 'producto': producto})


@login_required
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

@login_required
def nuevo_pedido(request):
    clientes = Clientes.objects.all()
    productos = Productos.objects.all()
    materiales_tabulador = TabuladorCostos.objects.order_by('espesor_mm')

    if request.method == 'POST':
        
        if request.headers.get('Content-Type') == 'application/json':
            try:
                data = json.loads(request.body)
                
                # 1. Buscar cliente (Si viene vacío, se queda como None para "Público General")
                cliente_id = data.get('cliente_id')
                cliente = Clientes.objects.filter(pk=cliente_id).first() if cliente_id else None
                
                monto_abonado = Decimal(str(data.get('monto_abonado') or 0))
                
                # Crear la Venta Maestra
                venta = Ventas.objects.create(
                    id_cliente=cliente,
                    monto_abonado=monto_abonado,
                    estatus=data.get('estatus', 'pendiente'),
                    fecha_entrega=data.get('fecha_entrega') or None,
                    fecha_venta=datetime.date.today(),
                    descuento_porcentaje=Decimal(str(data.get('descuento_porcentaje') or 0)),
                    incluye_iva=bool(data.get('incluye_iva', False))
                )

                alertas_stock = []

                for item in data.get('carrito', []):
                    producto = get_object_or_404(Productos, pk=item['producto_id'])
                    
                    cantidad = int(item.get('cantidad', 1))
                    sub_str = str(item.get('subtotal') or 0).replace(',', '.')

                    # Validar stock del producto con precio fijo
                    if producto.precio_fijo is not None and producto.stock_actual < cantidad:
                        return JsonResponse({
                            'ok': False,
                            'error': f'Stock insuficiente para "{producto.nombre}". Disponible: {producto.stock_actual}, solicitado: {cantidad}.'
                        })

                    DetalleVenta.objects.create(
                        id_venta=venta,
                        id_producto=producto,
                        cantidad=cantidad,
                        largo_pza=item.get('largo') or 0,
                        ancho_pza=item.get('ancho') or 0,
                        espesor_mm=item.get('espesor') or 0,
                        minutos_lazer=item.get('minutos_laser') or 0,
                        subtotal=Decimal(sub_str)
                    )

                    # 3. Descontar stock del producto si tiene precio fijo
                    if producto.precio_fijo is not None:
                        producto.stock_actual = max(0, producto.stock_actual - cantidad)
                        producto.save(update_fields=['stock_actual'])

                        if producto.stock_actual <= producto.stock_minimo:
                            alertas_stock.append({
                                'nombre': producto.nombre,
                                'actual': producto.stock_actual,
                                'minimo': producto.stock_minimo,
                            })

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
        'materiales_tabulador': materiales_tabulador,
        'tarifa_laser': _get_tarifa_laser(),
    })


# ─────────────────────────────────────────
#  COTIZACIONES
# ─────────────────────────────────────────

@login_required
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
    
    subtotal = sum(d.subtotal for d in venta.detalles.all()) or Decimal('0')
    desc = subtotal * (venta.descuento_porcentaje / Decimal('100'))
    neto = subtotal - desc
    iva = neto * Decimal('0.16') if venta.incluye_iva else Decimal('0')
    
    return neto + iva

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

@login_required
def lista_ventas(request):
    limite = datetime.date.today() - datetime.timedelta(days=15)
    Ventas.objects.filter(estatus='cotizacion', fecha_venta__lt=limite).delete()
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


@login_required
def detalle_venta(request, pk):
    venta = get_object_or_404(
        Ventas.objects.select_related(
            'id_cotizacion__id_cliente',
            'id_cotizacion__id_producto',
            'id_cotizacion__id_material',
            'id_cliente',
        ).prefetch_related('detalles__id_producto', 'detalles__id_material'),
        pk=pk
    )
    # Datos resueltos para el template (híbrido POS + cotización)
    venta.cliente_nombre  = _cliente_nombre(venta)
    venta.producto_nombre = _producto_nombre(venta)
    venta.total_calculado = _total_venta(venta)

    # Teléfono del cliente (para WhatsApp)
    if venta.id_cotizacion_id and venta.id_cotizacion.id_cliente:
        cliente_tel = venta.id_cotizacion.id_cliente.telefono or ''
    elif venta.id_cliente_id:
        cliente_tel = venta.id_cliente.telefono or ''
    else:
        cliente_tel = ''

    # Stepper de progreso
    orden = ['cotizacion','pendiente', 'en_produccion', 'pagada', 'entregada']
    iconos = ['📝','⏳', '🔧', '💰', '✅']
    labels = ['Cotización', 'Pendiente', 'En producción', 'Pagada', 'Entregada']
    idx_actual = orden.index(venta.estatus) if venta.estatus in orden else 0

    class Etapa:
        def __init__(self, activo, linea):
            self.activo = activo
            self.linea  = linea

    progreso = [
        (Etapa(i <= idx_actual, i < idx_actual), icono, label)
        for i, (icono, label) in enumerate(zip(iconos, labels))
    ]

    return render(request, 'gestion/venta_detalle.html', {
        'venta':        venta,
        'cliente_tel':  cliente_tel,
        'progreso':     progreso,
        'whatsapp_url': '#',  # se reemplaza en JS con el mensaje dinámico
    })


@login_required
def actualizar_estatus_venta(request, pk):
    venta = get_object_or_404(Ventas, pk=pk)
    if request.method == 'POST':
        nuevo = request.POST.get('estatus')
        if nuevo in ['cotizacion','pendiente','en_produccion', 'pagada', 'entregada']:
            venta.estatus = nuevo
        fecha = request.POST.get('fecha_entrega')
        if fecha:
            venta.fecha_entrega = fecha
        venta.save()
    return redirect('detalle_venta', pk=pk)

@login_required
def actualizar_abono_venta(request, pk):
    venta = get_object_or_404(Ventas, pk=pk)
    if request.method == 'POST':
        nuevo_abono_str = request.POST.get('monto_abonado')
        try:
            nuevo_abono = Decimal(nuevo_abono_str)
            total_pedido = _total_venta(venta) # Utilizamos tu helper que suma los detalles
            
            # Validación: El abono no puede superar el total
            if nuevo_abono > total_pedido:
                messages.error(request, f'No se puede registrar un abono (${nuevo_abono}) mayor al total del pedido (${total_pedido}).')
            else:
                venta.monto_abonado = nuevo_abono
                venta.save()
                messages.success(request, 'Monto abonado actualizado correctamente.')
                
        except Exception as e:
            messages.error(request, f'Error: {e}')
            
    return redirect('detalle_venta', pk=pk)

# ─────────────────────────────────────────
#  AJAX: CREAR CLIENTE DESDE POS
# ─────────────────────────────────────────

@login_required
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
                'nombre': nuevo_cliente.nombre,
                'telefono': nuevo_cliente.telefono
            })
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e)})
            
    return JsonResponse({'ok': False, 'error': 'Método no permitido'})

# ─────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────

def _get_total_venta_val(venta):
    """Total real de una venta: usa cotizacion legacy O suma DetalleVenta."""
    return float(_total_venta(venta))

@login_required
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
                          .filter(estatus__in=['cotizacion', 'pendiente', 'en_produccion'])
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

@login_required
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
        elif accion == 'eliminar_tabulador':
            try:
                tabulador_id = request.POST.get('tabulador_id')
                # Busramos y eliminamos el registro de la base de datos
                TabuladorCostos.objects.filter(pk=tabulador_id).delete()
                messages.success(request, 'Espesor eliminado correctamente.')
            except Exception as e:
                messages.error(request, f'Ocurrió un error al eliminar: {str(e)}')    
            
        return redirect('configuracion_precios')

    return render(request, 'gestion/configuracion_precios.html', {
        'config': config, 'productos': productos, 'tabuladores': tabuladores,
    })

@login_required
def pantalla_pendientes(request):
    # Traemos los mismos pedidos activos que el Dashboard
    pedidos_activos_qs = (Ventas.objects
                          .filter(estatus__in=['cotizacion', 'pendiente', 'en_produccion'])
                          .select_related('id_cotizacion__id_cliente',
                                          'id_cotizacion__id_producto',
                                          'id_cliente')
                          .prefetch_related('detalles__id_producto')
                          .order_by('-fecha_venta'))

    pedidos_activos = []
    for v in pedidos_activos_qs:
        v.cliente_nombre  = _cliente_nombre(v)
        v.producto_nombre = _producto_nombre(v)
        pedidos_activos.append(v)

    return render(request, 'gestion/pantalla_pendientes.html', {
        'pedidos_activos': pedidos_activos,
    })