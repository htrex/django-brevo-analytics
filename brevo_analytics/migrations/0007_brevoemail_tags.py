# Add tags JSONField to BrevoEmail for tag-based message grouping

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('brevo_analytics', '0006_replace_unique_together_with_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='brevoemail',
            name='tags',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Tag array from Brevo webhook/CSV (e.g. ['digest:42:Title', 'customer:15:Name'])",
            ),
        ),
    ]
