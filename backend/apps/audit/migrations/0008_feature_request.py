# Phase GB / Gap 151 — FeatureRequest inbox + per-user vote constraint.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0007_entitycomment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=160)),
                ('body', models.TextField()),
                ('category', models.CharField(blank=True, db_index=True, max_length=40)),
                (
                    'priority',
                    models.CharField(
                        choices=[
                            ('low', 'Low — nice to have'),
                            ('medium', 'Medium — would help regularly'),
                            ('high', 'High — blocks my workflow'),
                        ],
                        db_index=True,
                        default='medium',
                        max_length=10,
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('new', 'New'),
                            ('accepted', 'Accepted'),
                            ('planned', 'Planned'),
                            ('shipped', 'Shipped'),
                            ('declined', 'Declined'),
                            ('duplicate', 'Duplicate'),
                        ],
                        db_index=True,
                        default='new',
                        max_length=16,
                    ),
                ),
                ('context', models.JSONField(blank=True, default=dict)),
                ('votes', models.IntegerField(default=0)),
                ('admin_reply', models.TextField(blank=True)),
                (
                    'author',
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name='feature_requests',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'Feature Request',
                'verbose_name_plural': 'Feature Requests',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['status', '-created_at'], name='audit_fr_status_idx'),
                    models.Index(fields=['priority', '-created_at'], name='audit_fr_priority_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='FeatureRequestVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'request',
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name='vote_rows',
                        to='audit.featurerequest',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name='feature_votes',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'Feature Request Vote',
                'verbose_name_plural': 'Feature Request Votes',
                'constraints': [
                    models.UniqueConstraint(
                        fields=('request', 'user'),
                        name='uniq_feature_vote_per_user',
                    ),
                ],
            },
        ),
    ]
