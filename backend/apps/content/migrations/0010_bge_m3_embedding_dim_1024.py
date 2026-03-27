from django.db import migrations, models
from pgvector.django import VectorField

def null_embeddings(apps, schema_editor):
    ContentItem = apps.get_model('content', 'ContentItem')
    Sentence = apps.get_model('content', 'Sentence')
    ContentItem.objects.all().update(embedding=None)
    Sentence.objects.all().update(embedding=None)
    print("\n-- WARNING: All embeddings have been nulled. Re-run the embed pipeline.")

class Migration(migrations.Migration):
    dependencies = [
        ('content', '0009_add_content_value_score'),
    ]
    operations = [
        migrations.RunPython(null_embeddings),
        migrations.AlterField(
            model_name='contentitem',
            name='embedding',
            field=VectorField(blank=True, dimensions=1024, help_text='1024-dimension sentence embedding for semantic similarity search via pgvector.', null=True),
        ),
        migrations.AlterField(
            model_name='sentence',
            name='word_position',
            field=models.IntegerField(default=0, help_text='Word offset of the sentence start in the post. Sentences with word_position > HOST_SCAN_WORD_LIMIT are excluded from host scanning.'),
        ),
        migrations.AlterField(
            model_name='sentence',
            name='embedding',
            field=VectorField(blank=True, dimensions=1024, help_text='1024-dimension sentence embedding. Used in stage-2 similarity ranking.', null=True),
        ),
    ]
