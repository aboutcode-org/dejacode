# Generated by Django 5.0.6 on 2024-09-04 08:13

import django.db.models.deletion
import dje.fields
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('dje', '0004_dataspace_vulnerabilities_updated_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='Vulnerability',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, verbose_name='UUID')),
                ('created_date', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The date and time the object was created.')),
                ('last_modified_date', models.DateTimeField(auto_now=True, db_index=True, help_text='The date and time the object was last modified.')),
                ('vulnerability_id', models.CharField(help_text="A unique identifier for the vulnerability, prefixed with 'VCID-'. For example, 'VCID-2024-0001'.", max_length=20)),
                ('summary', models.TextField(blank=True, help_text='A brief summary of the vulnerability, outlining its nature and impact.')),
                ('aliases', dje.fields.JSONListField(blank=True, default=list, help_text="A list of aliases for this vulnerability, such as CVE identifiers (e.g., 'CVE-2017-1000136').")),
                ('references', dje.fields.JSONListField(blank=True, default=list, help_text='A list of references for this vulnerability. Each reference includes a URL, an optional reference ID, scores, and the URL for further details. ')),
                ('fixed_packages', dje.fields.JSONListField(blank=True, default=list, help_text='A list of packages that are not affected by this vulnerability.')),
                ('fixed_packages_count', models.GeneratedField(db_persist=True, expression=models.Func(models.F('fixed_packages'), function='jsonb_array_length'), output_field=models.IntegerField())),
                ('min_score', models.FloatField(blank=True, help_text='The minimum score of the range.', null=True)),
                ('max_score', models.FloatField(blank=True, help_text='The maximum score of the range.', null=True)),
                ('resource_url', models.URLField(blank=True, help_text='URL of the data source for this Vulnerability.', max_length=1024, verbose_name='Resource URL')),
                ('dataspace', models.ForeignKey(editable=False, help_text='A Dataspace is an independent, exclusive set of DejaCode data, which can be either nexB master reference data or installation-specific data.', on_delete=django.db.models.deletion.PROTECT, to='dje.dataspace')),
            ],
            options={
                'verbose_name_plural': 'Vulnerabilities',
                'indexes': [models.Index(fields=['vulnerability_id'], name='vulnerabili_vulnera_92f044_idx')],
                'unique_together': {('dataspace', 'uuid'), ('dataspace', 'vulnerability_id')},
            },
        ),
    ]