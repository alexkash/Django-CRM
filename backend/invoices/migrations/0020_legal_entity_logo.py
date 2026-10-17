from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("invoices", "0019_merge_billing_deployment")]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="branding_logo_png",
            field=models.BinaryField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="legalentity",
            name="logo_png",
            field=models.BinaryField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="legalentity",
            name="logo_sha256",
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
    ]
