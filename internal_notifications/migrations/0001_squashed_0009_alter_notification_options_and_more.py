# Replaces the migrations of the former django-notifications-patched package,
# so existing databases keep their table and data unchanged.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    replaces = [
        ("notifications", "0001_initial"),
        ("notifications", "0002_auto_20150224_1134"),
        ("notifications", "0003_notification_data"),
        ("notifications", "0004_auto_20150826_1508"),
        ("notifications", "0005_auto_20160504_1520"),
        ("notifications", "0006_indexes"),
        ("notifications", "0007_add_timestamp_index"),
        ("notifications", "0008_index_together_recipient_unread"),
        ("notifications", "0009_alter_notification_options_and_more"),
    ]

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("success", "success"),
                            ("info", "info"),
                            ("warning", "warning"),
                            ("error", "error"),
                        ],
                        default="info",
                        max_length=20,
                        verbose_name="level",
                    ),
                ),
                (
                    "unread",
                    models.BooleanField(db_index=True, default=True, verbose_name="unread"),
                ),
                (
                    "actor_object_id",
                    models.CharField(max_length=255, verbose_name="actor object id"),
                ),
                ("verb", models.CharField(max_length=255, verbose_name="verb")),
                (
                    "description",
                    models.TextField(blank=True, null=True, verbose_name="description"),
                ),
                (
                    "target_object_id",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="target object id"
                    ),
                ),
                (
                    "action_object_object_id",
                    models.CharField(
                        blank=True,
                        max_length=255,
                        null=True,
                        verbose_name="action object object id",
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                        verbose_name="timestamp",
                    ),
                ),
                (
                    "public",
                    models.BooleanField(db_index=True, default=True, verbose_name="public"),
                ),
                (
                    "deleted",
                    models.BooleanField(db_index=True, default=False, verbose_name="deleted"),
                ),
                (
                    "emailed",
                    models.BooleanField(db_index=True, default=False, verbose_name="emailed"),
                ),
                # Text column, as created by the former jsonfield.JSONField
                ("data", models.TextField(blank=True, null=True, verbose_name="data")),
                (
                    "action_object_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notify_action_object",
                        to="contenttypes.contenttype",
                        verbose_name="action object content type",
                    ),
                ),
                (
                    "actor_content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notify_actor",
                        to="contenttypes.contenttype",
                        verbose_name="actor content type",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="recipient",
                    ),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notify_target",
                        to="contenttypes.contenttype",
                        verbose_name="target content type",
                    ),
                ),
            ],
            options={
                "verbose_name": "Notification",
                "verbose_name_plural": "Notifications",
                "ordering": ("-timestamp",),
                "indexes": [
                    models.Index(
                        fields=["recipient", "unread"], name="notificatio_recipie_8bedf2_idx"
                    )
                ],
            },
        ),
    ]
