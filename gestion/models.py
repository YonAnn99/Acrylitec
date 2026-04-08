from decimal import Decimal

from django.db import models


class Clientes(models.Model):
    id_cliente = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, blank=True, null=True)
    telefono = models.CharField(max_length=100, blank=True, null=True)
    email = models.CharField(max_length=100, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'clientes'
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class Cotizaciones(models.Model):
    id_cotizacion = models.AutoField(primary_key=True)
    id_cliente = models.ForeignKey(Clientes, models.DO_NOTHING, db_column='id_cliente', blank=True, null=True)
    id_producto = models.ForeignKey('Productos', models.DO_NOTHING, db_column='id_producto', blank=True, null=True)
    id_material = models.ForeignKey('Materiales', models.DO_NOTHING, db_column='id_material', blank=True, null=True)
    largo_pza = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Largo (cm)")
    ancho_pza = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Ancho (cm)")
    espesor_mm = models.IntegerField(blank=True, null=True, verbose_name="Espesor (mm)")
    porcentaje_utilidad = models.IntegerField(default=40, verbose_name="Utilidad (%)")
    minutos_lazer = models.IntegerField(blank=True, null=True)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fecha = models.DateField(blank=True, null=True)

    def calcular_monto(self):
        
        
        if self.id_producto and self.id_producto.precio_fijo:
            return self.id_producto.precio_fijo

        # 2. Obtener factor del tabulador (cm2)
        try:
            tabulador = TabuladorCostos.objects.get(espesor_mm=self.espesor_mm)
            factor = tabulador.factor_costo
        except TabuladorCostos.DoesNotExist:
            factor = Decimal('0.00')

        largo = Decimal(str(self.largo_pza or 0))
        ancho = Decimal(str(self.ancho_pza or 0))

        # 3. Cálculo de área y costo base
        area_cm2 = largo * ancho
        area_m2 = area_cm2 / Decimal('10000')  # convertir cm² a m²
        costo_base = area_m2 * factor

        # 4. Utilidad manual (40%, 70%, etc.)
        utilidad = costo_base * (Decimal(self.porcentaje_utilidad) / Decimal(100))

        # 5. Costo Láser
        config = ConfiguracionPrecios.get_config()
        costo_laser = Decimal(self.minutos_lazer or 0) * config.tarifa_laser_minuto

        return (costo_base + utilidad + costo_laser).quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        # Calculamos el monto antes de guardar
        self.monto_total = self.calcular_monto()
        super().save(*args, **kwargs)

    class Meta:
        managed = True
        db_table = 'cotizaciones'
        verbose_name = "Cotizacion"
        verbose_name_plural = "Cotizaciones"


class Materiales(models.Model):
    id_material = models.AutoField(primary_key=True)
    descripcion = models.CharField(max_length=100, blank=True, null=True)
    largo = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    ancho = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock_actual = models.IntegerField()
    stock_minimo = models.IntegerField()

    class Meta:
        managed = True
        db_table = 'materiales'
        verbose_name = "Material"
        verbose_name_plural = "Materiales"


class Productos(models.Model):
    id_producto = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, blank=True, null=True)
    detalle = models.CharField(max_length=100, blank=True, null=True)
    precio_fijo = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio Fijo (Opcional)")
    porcentaje_utilidad = models.IntegerField(default=40)
    foto = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'productos'
        verbose_name = "Producto"
        verbose_name_plural = "Productos"


class TabuladorCostos(models.Model):
    id_tabulador = models.AutoField(primary_key=True)
    espesor_mm = models.IntegerField()
    factor_costo = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        managed = True
        db_table = 'tabulador_costos'
        verbose_name = "Tabulador_Costo"
        verbose_name_plural = "Tabulador_Costos"


class Ventas(models.Model):
    ESTATUS_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_produccion', 'En producción'),
        ('pagada', 'Pagada'),
        ('entregada', 'Entregada'),
    ]

    id_venta = models.AutoField(primary_key=True)
    id_cotizacion = models.ForeignKey(Cotizaciones, models.DO_NOTHING, db_column='id_cotizacion', blank=True, null=True)
    monto_abonado = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Anticipo/Abono")
    estatus = models.CharField(max_length=20, choices=ESTATUS_CHOICES, default='pendiente')
    fecha_entrega = models.DateField(blank=True, null=True)
    fecha_venta = models.DateField(auto_now_add=True, null=True)

    @property
    def saldo_restante(self):
        """Calcula automáticamente cuánto debe el cliente """
        total = self.id_cotizacion.monto_total if self.id_cotizacion else 0
        return total - self.monto_abonado

    class Meta:
        managed = True
        db_table = 'ventas'
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"


class ConfiguracionPrecios(models.Model):
    """
    Tabla singleton — siempre existe solo 1 registro.
    Guarda la tarifa láser por minuto configurable.
    """
    tarifa_laser_minuto = models.DecimalField(
        max_digits=8, decimal_places=2, default=15.00,
        verbose_name="Tarifa láser por minuto ($)"
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'configuracion_precios'
        verbose_name = "Configuración de Precios"
        verbose_name_plural = "Configuración de Precios"

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj