from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sync", "0006_alter_syncjob_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="syncjob",
            name="file_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Saved upload path for file-backed imports that can resume.",
                max_length=1024,
            ),
        ),
    ]
