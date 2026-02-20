# Replace unique_together with UniqueConstraint for Django 5.x compatibility

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("brevo_analytics", "0005_brevoemail_sender_email"),
    ]

    operations = [
        # BrevoMessage: unique_together → UniqueConstraint
        migrations.AlterUniqueTogether(
            name="brevomessage",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="brevomessage",
            constraint=models.UniqueConstraint(
                fields=["subject", "sent_date"],
                name="unique_brevo_message_subject_date",
            ),
        ),
        # BrevoEmail: unique_together → UniqueConstraint
        migrations.AlterUniqueTogether(
            name="brevoemail",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="brevoemail",
            constraint=models.UniqueConstraint(
                fields=["brevo_message_id", "recipient_email"],
                name="unique_brevo_email_mid_recipient",
            ),
        ),
    ]
