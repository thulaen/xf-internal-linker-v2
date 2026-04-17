# Phase E2 / Gap 51 — initial WebVital table.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0004_clienterrorlog_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebVital',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('name', models.CharField(choices=[('LCP', 'Largest Contentful Paint'), ('CLS', 'Cumulative Layout Shift'), ('INP', 'Interaction to Next Paint'), ('FCP', 'First Contentful Paint'), ('TTFB', 'Time to First Byte')], db_index=True, max_length=10)),
                ('value', models.FloatField(help_text='Metric value. Milliseconds for timings (LCP/INP/FCP/TTFB), unitless for CLS.')),
                ('rating', models.CharField(choices=[('good', 'Good'), ('needs-improvement', 'Needs improvement'), ('poor', 'Poor')], db_index=True, default='good', max_length=20)),
                ('delta', models.FloatField(default=0.0, help_text='Change since the last fire of this metric this page-load (for INP monotonic growth).')),
                ('metric_id', models.CharField(blank=True, help_text='Library-assigned unique id per metric per page-load.', max_length=100)),
                ('navigation_type', models.CharField(blank=True, help_text="'navigate' | 'reload' | 'back-forward' | 'prerender' | 'restore'.", max_length=20)),
                ('path', models.CharField(blank=True, db_index=True, max_length=500)),
                ('device_memory', models.FloatField(blank=True, help_text='navigator.deviceMemory when available (1, 2, 4, 8 GB tiers).', null=True)),
                ('effective_connection_type', models.CharField(blank=True, help_text="'4g' / '3g' / '2g' / 'slow-2g' — navigator.connection.effectiveType.", max_length=10)),
                ('client_timestamp_ms', models.BigIntegerField(blank=True, help_text='Client-side Date.now() at metric fire time.', null=True)),
                ('user_id', models.IntegerField(blank=True, help_text='Authenticated user id, if known. Not a FK — decoupled from the User table.', null=True)),
            ],
            options={
                'verbose_name': 'Web Vital Measurement',
                'verbose_name_plural': 'Web Vital Measurements',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['name', 'path', '-created_at'], name='audit_webvi_name_2063fc_idx'),
                    models.Index(fields=['name', 'rating', '-created_at'], name='audit_webvi_name_de4f88_idx'),
                ],
            },
        ),
    ]
