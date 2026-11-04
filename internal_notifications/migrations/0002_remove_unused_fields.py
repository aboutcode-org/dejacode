from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_squashed_0009_alter_notification_options_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="notification",
            name="level",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="target_content_type",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="target_object_id",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="public",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="deleted",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="emailed",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="data",
        ),
    ]
