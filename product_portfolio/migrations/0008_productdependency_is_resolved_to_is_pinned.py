# Generated by Django 5.0.9 on 2024-10-31 04:26

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('component_catalog', '0009_componentaffectedbyvulnerability_and_more'),
        ('dje', '0004_dataspace_vulnerabilities_updated_at'),
        ('product_portfolio', '0007_alter_scancodeproject_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='productdependency',
            name='product_por_is_reso_368f34_idx',
        ),
        migrations.RenameField(
            model_name='productdependency',
            old_name='is_resolved',
            new_name='is_pinned',
        ),
        migrations.AddIndex(
            model_name='productdependency',
            index=models.Index(fields=['is_pinned'], name='product_por_is_pinn_aa0755_idx'),
        ),
    ]
