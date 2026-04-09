from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0002_silogroup_scopeitem_silo_group"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scopeitem",
            name="scope_type",
            field=models.CharField(
                choices=[
                    ("node", "Forum Node"),
                    ("resource_category", "Resource Category"),
                    ("wp_posts", "WordPress Posts"),
                    ("wp_pages", "WordPress Pages"),
                ],
                help_text="Whether this is a XenForo forum node, resource category, or WordPress scope.",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="contentitem",
            name="content_type",
            field=models.CharField(
                choices=[
                    ("thread", "Forum Thread"),
                    ("resource", "Resource"),
                    ("wp_post", "WordPress Post"),
                    ("wp_page", "WordPress Page"),
                ],
                help_text="Whether this is a forum thread, resource, or WordPress content item.",
                max_length=30,
            ),
        ),
    ]
