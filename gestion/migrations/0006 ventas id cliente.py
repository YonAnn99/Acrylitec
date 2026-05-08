from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0005_alter_ventas_options_alter_ventas_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='ventas',
            name='id_cliente',
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_column='id_cliente_directo',
                on_delete=django.db.models.deletion.SET_NULL,
                to='gestion.clientes',
                verbose_name='Cliente directo (POS)',
            ),
        ),
    ]