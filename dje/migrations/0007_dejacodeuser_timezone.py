# Generated by Django 5.0.11 on 2025-02-13 19:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dje', '0006_dejacodeuser_vulnerability_impact_notifications'),
    ]

    operations = [
        migrations.AddField(
            model_name='dejacodeuser',
            name='timezone',
            field=models.CharField(blank=True, help_text="Select your preferred time zone. This will affect how times are displayed across the app. If you don't set a timezone, UTC will be used by default.", max_length=50, null=True, verbose_name='time zone'),
        ),
    ]
