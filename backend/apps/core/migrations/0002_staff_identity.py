from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]
    operations = [
        migrations.AddField('staffprofile','session_version',models.PositiveBigIntegerField(default=0,editable=False)),
        migrations.AddField('staffprofile','verified_email',models.EmailField(blank=True,editable=False,max_length=254)),
        # Stock auth_user is owned by Django, so the cross-table recovery identity index is explicit.
        migrations.RunSQL(
            "CREATE UNIQUE INDEX hotel_staff_recovery_email_uq ON auth_user (LOWER(BTRIM(email))) WHERE BTRIM(email) <> ''",
            'DROP INDEX hotel_staff_recovery_email_uq',
        ),
    ]
