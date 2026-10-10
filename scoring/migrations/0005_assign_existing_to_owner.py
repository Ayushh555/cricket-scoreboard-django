from django.db import migrations


def assign(apps, schema_editor):
    """Teams and matches made before accounts had their own data belong to the first owner account."""
    User = apps.get_model("auth", "User")
    owner = User.objects.filter(is_superuser=True).order_by("id").first() or User.objects.order_by("id").first()
    if owner:
        apps.get_model("scoring", "Team").objects.filter(owner__isnull=True).update(owner=owner)
        apps.get_model("scoring", "Match").objects.filter(owner__isnull=True).update(owner=owner)


class Migration(migrations.Migration):
    dependencies = [("scoring", "0004_owners")]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
