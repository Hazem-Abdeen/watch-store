from django.db import migrations, models


def quarantine_legacy_failures(apps, schema_editor):
    # The old handler also marked ambiguous SMTP errors and post-send DB errors
    # as failed. Their delivery cannot safely be inferred from that status.
    apps.get_model('checkout', 'OrderEmailNotification').objects.using(
        schema_editor.connection.alias,
    ).filter(status='failed').update(status='uncertain')


class Migration(migrations.Migration):
    dependencies = [('checkout', '0001_initial')]

    operations = [
        migrations.AlterField(
            model_name='orderemailnotification', name='status',
            field=models.CharField(max_length=16, default='sending', choices=[
                ('sending', 'Sending'), ('sent', 'Sent'), ('failed', 'Failed'),
                ('uncertain', 'Delivery uncertain'), ('skipped', 'Skipped'),
            ]),
        ),
        migrations.RunPython(quarantine_legacy_failures, migrations.RunPython.noop),
    ]
