# Phase OB / Gaps 131 + 132 — FeatureFlag + FeatureFlagExposure tables.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_quarantinerecord'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureFlag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.SlugField(max_length=80, unique=True)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('enabled', models.BooleanField(default=False)),
                ('rollout_percent', models.PositiveSmallIntegerField(default=100)),
                ('variants', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Feature Flag',
                'verbose_name_plural': 'Feature Flags',
                'ordering': ['key'],
            },
        ),
        migrations.CreateModel(
            name='FeatureFlagExposure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('key', models.SlugField(db_index=True, max_length=80)),
                ('variant', models.CharField(blank=True, max_length=60)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='feature_flag_exposures', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Feature Flag Exposure',
                'verbose_name_plural': 'Feature Flag Exposures',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['key', '-created_at'], name='core_ffexp_key_created_idx'),
                ],
            },
        ),
    ]
