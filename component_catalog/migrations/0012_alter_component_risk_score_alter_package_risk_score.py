# Generated by Django 5.0.9 on 2024-11-14 12:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('component_catalog', '0011_to_delete_temp_fake_values'),
    ]

    operations = [
        migrations.AlterField(
            model_name='component',
            name='risk_score',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Risk score between 0.00 and 10.00, where higher values indicate greater vulnerability risk for the package.', max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name='package',
            name='risk_score',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Risk score between 0.00 and 10.00, where higher values indicate greater vulnerability risk for the package.', max_digits=4, null=True),
        ),
    ]