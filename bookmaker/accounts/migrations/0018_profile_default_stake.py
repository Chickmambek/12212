from django.db import migrations, models
import decimal

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_onewinsession_session_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='default_stake',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('10.00'), max_digits=10),
        ),
    ]