#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import json
import logging
import os

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

import markdown
from bleach import Cleaner
from bleach.linkifier import LinkifyFilter
from bleach_allowlist import markdown_attrs
from bleach_allowlist import markdown_tags

from dje.fields import LastModifiedByField
from dje.models import DataspacedManager
from dje.models import DataspacedModel
from dje.models import DataspacedQuerySet
from dje.models import HistoryDateFieldsMixin
from dje.models import HistoryFieldsMixin
from dje.models import get_unsecured_manager
from workflow import integrations
from workflow.notification import request_comment_slack_payload
from workflow.notification import request_slack_payload

logger = logging.getLogger("dje")


# Add `RequestMixin` to the following Model classes.
# Also add a `display_name` on the Model API Serializer.
CONTENT_TYPES = (
    models.Q(app_label="component_catalog", model="component")
    | models.Q(app_label="component_catalog", model="package")
    | models.Q(app_label="license_library", model="license")
    | models.Q(app_label="product_portfolio", model="product")
)


class Priority(DataspacedModel):
    label = models.CharField(
        max_length=50,
        help_text=_("Concise name to identify the Priority."),
    )

    position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            "A number to control the sequence of the Priorities presented to "
            "the user when selecting one from the dropdown list."
        ),
    )

    color_code = models.CharField(
        max_length=7,
        blank=True,
        help_text=_(
            "You can specify a valid HTML color code (e.g. #FFFFFF) to apply to your Priority."
        ),
    )

    class Meta:
        unique_together = (("dataspace", "label"), ("dataspace", "uuid"))
        ordering = ["position", "label"]
        verbose_name_plural = _("priorities")

    def __str__(self):
        return self.label


class ExternalIssueLink(DataspacedModel):
    class Platform(models.TextChoices):
        GITHUB = "github", _("GitHub")
        GITLAB = "gitlab", _("GitLab")
        JIRA = "jira", _("Jira")
        SOURCEHUT = "sourcehut", _("SourceHut")
        FORGEJO = "forgejo", _("Forgejo")

    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        help_text=_("External issue tracking platform."),
    )

    repo = models.CharField(
        max_length=100,
        help_text=_("Repository or project identifier (e.g., 'user/repo-name')."),
    )

    issue_id = models.CharField(
        max_length=100,
        help_text=_("ID or key of the issue on the external platform."),
    )

    base_url = models.URLField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_(
            "Base URL of the external issue tracker platform (e.g., https://forgejo.example.org). "
            "Used to construct API endpoints for integrations like Forgejo or Jira."
        ),
    )

    class Meta:
        unique_together = (
            ("dataspace", "platform", "repo", "issue_id"),
            ("dataspace", "uuid"),
        )

    def __str__(self):
        return f"{self.get_platform_display()}:{self.repo}#{self.issue_id}"

    @property
    def issue_url(self):
        if self.platform == self.Platform.GITHUB:
            return f"https://github.com/{self.repo}/issues/{self.issue_id}"
        elif self.platform == self.Platform.GITLAB:
            return f"https://gitlab.com/{self.repo}/-/issues/{self.issue_id}"
        elif self.platform == self.Platform.JIRA:
            return f"{self.repo}/browse/{self.issue_id}"
        elif self.platform == self.Platform.FORGEJO:
            return f"{self.base_url}/{self.repo}/issues/{self.issue_id}"
        elif self.platform == self.Platform.SOURCEHUT:
            return f"https://todo.sr.ht/{self.repo}/{self.issue_id}"

    @property
    def icon_css_class(self):
        platform_icons = {
            self.Platform.GITHUB: "fa-brands fa-github",
            self.Platform.GITLAB: "fa-brands fa-gitlab",
            self.Platform.JIRA: "fa-brands fa-jira",
        }
        return platform_icons.get(self.platform, "fa-solid fa-square-up-right")

    @property
    def integration_class(self):
        return integrations.get_class_for_platform(self.platform)


class RequestQuerySet(DataspacedQuerySet):
    BASE_SELECT_RELATED = [
        "request_template",
        "requester",
        "assignee",
        "priority",
        "product_context",
        "external_issue",
        "last_modified_by",
    ]

    def product_secured(self, user):
        if not user:
            return self.none()

        product_ct = ContentType.objects.get_by_natural_key("product_portfolio", "product")
        product_qs = product_ct.model_class().objects.get_queryset(user=user)

        return (
            self.scope(user.dataspace)
            .filter(
                # If a product_context is set, Limit to authorized Products
                Q(product_context__isnull=True) | Q(product_context__in=product_qs),
            )
            .exclude(
                # If a Product type content_object is set, excludes non-authorized Products
                Q(content_type=product_ct)
                & Q(object_id__isnull=False)
                & ~Q(object_id__in=product_qs),
            )
        )

    def unassigned(self):
        """Limit the QuerySet to unassigned Requests."""
        return self.filter(assignee__isnull=True)

    def assigned_to(self, user):
        """Limit the QuerySet to Requests assigned to the given user."""
        return self.filter(assignee=user)

    def created_by(self, user):
        """Limit the QuerySet to Requests created by the given user."""
        return self.filter(requester=user)

    def followed_by(self, user):
        """
        Limit the QuerySet to Requests followed by the given user:
        requester, assignee, commented or attached a file.
        """
        return self.filter(
            Q(requester=user)
            | Q(assignee=user)
            | Q(comments__user=user)
            | Q(attachments__uploader=user)
        )

    def open(self):
        return self.filter(status=Request.Status.OPEN)

    def closed(self):
        return self.filter(status=Request.Status.CLOSED)

    def with_comments_attachments_counts(self):
        return self.annotate(
            attachments_count=models.Count("attachments", distinct=True),
            comments_count=models.Count("comments", distinct=True),
        )

    def for_list_view(self, user):
        return (
            self.product_secured(user)
            .with_comments_attachments_counts()
            .select_related(*self.BASE_SELECT_RELATED)
            .prefetch_related(
                "content_object__dataspace",
                "product_context__dataspace",
            )
            .distinct()
        )

    def for_details_view(self, user):
        return (
            self.product_secured(user)
            .select_related(*self.BASE_SELECT_RELATED)
            .prefetch_related(
                "attachments__uploader",
                "comments__user",
            )
        )

    def for_edit_view(self, user):
        return self.product_secured(user).select_related(*self.BASE_SELECT_RELATED)

    def for_content_object(self, content_object, user=None):
        """Limit the QuerySet to Requests attach to given `content_object`."""
        base_qs = self.product_secured(user) if user else self
        return base_qs.filter(
            content_type=ContentType.objects.get_for_model(content_object),
            object_id=content_object.id,
        )

    def for_activity_tab(self, content_object, user):
        return (
            self.for_content_object(content_object, user)
            .with_comments_attachments_counts()
            .select_related(*self.BASE_SELECT_RELATED)
        )


class Request(HistoryDateFieldsMixin, DataspacedModel):
    request_template = models.ForeignKey(
        to="workflow.RequestTemplate",
        related_name="requests",
        on_delete=models.PROTECT,
        editable=False,
    )

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        CLOSED = "closed", _("Closed")
        DRAFT = "draft", _("Draft")

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
        help_text=_(
            'Status of the request. "Draft" indicates that the request is not '
            "yet ready for action, pending further details from the requestor. "
            '"Open" indicates that the assignee has not finished the requested '
            "actions, and also that comments from all interested parties are "
            'welcome. "Closed" indicates that no further actions or comments '
            "are needed or expected."
        ),
    )

    is_private = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_(
            "When checked, the details of this request are visible only"
            " to the original requester and to request reviewers, and "
            "other users only see a limited summary. As an "
            "administrator, you can check or un-check this indicator to"
            " make a request private or public."
        ),
    )

    notes = models.TextField(
        blank=True,
        help_text=_(
            "Notes from one or more request reviewers regarding "
            "research, issues, and conclusions related to the "
            "request."
        ),
    )

    requester = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="request_as_requester",
        editable=False,
        help_text=_("Creator of the request."),
    )

    assignee = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="request_as_assignee",
        limit_choices_to={"is_staff": True, "is_active": True},
        null=True,
        blank=True,
        help_text=_(
            "The application user currently assigned to review the "
            "request and take appropriate action."
        ),
    )

    product_context = models.ForeignKey(
        to="product_portfolio.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        # Bypass the validation in ForeignKey.validate()
        # Required since we do not have control over the QuerySet in that method.
        parent_link=True,
        help_text=_("Identify the Product impacted by your Request."),
    )

    serialized_data = models.TextField(
        blank=True,
        help_text=_(
            "Optional data provided by the User making the request. "
            "Can be used by an Admin to pre-fill a form. Stored as "
            "JSON format."
        ),
    )

    content_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.PROTECT,
        limit_choices_to=CONTENT_TYPES,
        help_text=_(
            "Stores the type of the object requested. Supported types "
            "are Component, Package, License and Product"
        ),
    )

    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            "ID of the object attached to this request. This is used "
            "in combination with the content_type for the "
            "content_object field."
        ),
    )

    # No need to be explicit about the content_type abd object_id field names as
    # we are using the default ones.
    content_object = GenericForeignKey()

    content_object_repr = models.CharField(
        max_length=1000,
        blank=True,
        help_text=_(
            "String representation of the attached content_object if any. "
            "This is useful for search purposes and not intended for display."
        ),
    )

    priority = models.ForeignKey(
        to="workflow.Priority",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_(
            "The priority is intended to provide team members with a guideline "
            "for selecting and assigning requests for additional action, based on the "
            "criticality of the request."
        ),
    )

    title = models.CharField(
        max_length=255,
        db_index=True,
        help_text=_("The Request Title is a concise statement of the Request purpose and content."),
    )

    cc_emails = ArrayField(
        base_field=models.EmailField(),
        null=True,
        blank=True,
        help_text=_(
            "You can provide a comma-separated list of email addresses to publish email "
            "notifications to any users that should be aware of the progress of this request."
        ),
    )

    external_issue = models.ForeignKey(
        to="workflow.ExternalIssueLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Link to external issue (GitHub, GitLab, Jira, etc.)"),
    )

    last_modified_by = LastModifiedByField()

    objects = DataspacedManager.from_queryset(RequestQuerySet)()

    class Meta:
        ordering = ["-last_modified_date"]
        unique_together = ("dataspace", "uuid")

    def __str__(self):
        return f"#{self.pk}"

    def save(self, *args, **kwargs):
        """Add the `update_request_count` logic on the related `content_object`."""
        self.content_type = self.request_template.content_type

        # Store the repr of the content_object for search purposes.
        if self.object_id:
            # Bypass the broken GenericForeignKey.__get__ introduced in
            # https://github.com/django/django/commit/cc4cb95
            try:
                self.content_object = self.content_type.get_object_for_this_type(
                    id=self.object_id,
                )
            except ObjectDoesNotExist:
                pass
            else:
                self.content_object_repr = str(self.content_object)

        # `previous_object_id` logic is only required on edition.
        previous_object_id = None
        is_change = self.pk
        if is_change:
            previous_object_id = self.__class__.objects.get(pk=self.pk).object_id

        super().save(*args, **kwargs)

        # Need to be post-save so the current Request exists in the DB before the count()
        if self.content_object and not self.is_draft:
            self.content_object.update_request_count()

        # The `content_object` was changed or removed, we need to update the `request_count`
        # of the previous object instance too. Warning: The previous object may not exist anymore.
        if previous_object_id and previous_object_id != self.object_id:
            try:
                previous_object = self.content_type.get_object_for_this_type(id=previous_object_id)
            except ObjectDoesNotExist:
                return
            previous_object.update_request_count()

        self.handle_integrations()

    def get_absolute_url(self):
        return reverse("workflow:request_details", args=[self.uuid])

    @property
    def details_url(self):
        return self.get_absolute_url()

    def get_serialized_data(self):
        if not self.serialized_data:
            return {}

        try:
            serialized_data = json.loads(self.serialized_data)
        except (ValueError, TypeError):
            return {}

        if not isinstance(serialized_data, dict):
            return {}

        return serialized_data

    def get_serialized_data_as_list(self):
        """Return a python iterable from the serialized_data field."""
        serialized_data = self.get_serialized_data()
        if not serialized_data:
            return []

        return [
            {
                "label": question.label,
                "input_type": question.input_type,
                "value": serialized_data.get(question.label),
            }
            for question in self.request_template.questions.all()
        ]

    def get_serialized_data_as_html(self, html_template="{label}: {value}", separator="<br>"):
        """Return a HTML content of the serialized_data."""
        serialized_data = []
        for data in self.get_serialized_data_as_list():
            try:
                value = data["value"]
                if data["input_type"] == "BooleanField":
                    value = "Yes" if bool(data.get("value")) == 1 else "No"
                line = str(html_template).format(label=data["label"], value=escape(value))
            except KeyError:
                return 'Error in the "Serialized data" value.'
            else:
                serialized_data.append(line)

        return format_html(separator.join(serialized_data))

    @property
    def serialized_data_html(self):
        return self.get_serialized_data_as_html()

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    @property
    def is_closed(self):
        return self.status == self.Status.CLOSED

    @property
    def is_draft(self):
        return self.status == self.Status.DRAFT

    def has_details_permission(self, user):
        """
        Private Requests are not available to regular user unless he is the
        requester or is an administrator.
        """
        return user == self.requester or user.is_staff or not self.is_private

    def has_edit_permission(self, user):
        """
        Only the requester or an administrator can edit a Request,
        unless the Request is closed already.
        """
        return (user == self.requester or user.is_staff) and not self.is_closed

    def has_close_permission(self, user):
        """Only the requester can close a Request if not closed already."""
        return user == self.requester and not self.is_closed

    def get_involved_users(self, exclude=None):
        """
        Return the set of users involved is the Requests:
         - requestor
         - assignee
         - edited by (multiple)
         - commented by (multiple)
        """
        users = {
            self.requester,
            *(event.user for event in self.events.all()),
            *(comment.user for comment in self.comments.all()),
        }

        # The assignee is now required on the RequestForm but not on the Request model.
        # Keeping this condition for compatibility with old Request instances.
        if self.assignee:
            users.add(self.assignee)

        if exclude:
            users.discard(exclude)

        return users

    def serialize_hook(self, hook):
        if "hooks.slack.com" in hook.target:
            return request_slack_payload(self, created="added" in hook.event)

        from workflow.api import RequestSerializer

        serializer = RequestSerializer(self, context={"request": None})

        return {
            "hook": hook.dict(),
            "data": serializer.data,
        }

    def close(self, user, reason):
        """
        Set the Request status to CLOSED.
        A RequestEvent is created and returned.
        """
        self.status = self.Status.CLOSED
        self.last_modified_by = user
        self.save()
        event_instance = self.events.create(
            user=user,
            text=reason,
            event_type=RequestEvent.CLOSED,
            dataspace=self.dataspace,
        )
        return event_instance

    def link_external_issue(self, platform, repo, issue_id, base_url=None):
        """Create or return an ExternalIssueLink associated with this Request."""
        if self.external_issue:
            return self.external_issue

        if base_url:
            base_url = base_url.rstrip("/")

        external_issue = ExternalIssueLink.objects.create(
            dataspace=self.dataspace,
            platform=platform,
            repo=repo,
            issue_id=str(issue_id),
            base_url=base_url,
        )

        # Set the external_issue on this instance without triggering the whole
        # save() + handle_integrations() logic.
        self.raw_update(external_issue=external_issue)

        return external_issue

    def handle_integrations(self):
        issue_tracker_id = self.request_template.issue_tracker_id
        if not issue_tracker_id:
            return

        integration_class = integrations.get_class_for_tracker(issue_tracker_id)
        if integration_class:
            integration_class(dataspace=self.dataspace).sync(request=self)


@receiver(models.signals.post_delete, sender=Request)
def update_request_count_on_delete(sender, instance=None, **kwargs):
    """
    Update the `request_count` on the content_object after deleting the Request instance.
    Using the `post_delete` signal instead of overriding the `delete()` method as it ensure
    this logic gets executed on bulk deletion as well.
    See https://docs.djangoproject.com/en/dev/topics/db/models/#overriding-predefined-model-methods
    """
    if instance.object_id and instance.content_object:
        instance.content_object.update_request_count()


class AbstractRequestEvent(HistoryDateFieldsMixin, DataspacedModel):
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        editable=False,
    )

    text = models.TextField()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Call the handle_integrations method on save, only for addition."""
        is_addition = not self.pk
        super().save(*args, **kwargs)
        if is_addition:
            self.handle_integrations()

    def handle_integrations(self):
        pass


class RequestEvent(AbstractRequestEvent):
    request = models.ForeignKey(
        to="workflow.Request",
        on_delete=models.CASCADE,
        related_name="events",
    )

    EDIT = 1
    ATTACHMENT = 2
    CLOSED = 3

    EVENT_TYPE_CHOICES = (
        (EDIT, "Edition"),
        (ATTACHMENT, "Attachment"),
        (CLOSED, "Closed"),
    )

    event_type = models.IntegerField(
        choices=EVENT_TYPE_CHOICES,
    )

    class Meta:
        ordering = ["created_date"]
        unique_together = ("dataspace", "uuid")

    def __str__(self):
        return f"{self.get_event_type_display()} by {self.user.username}"

    def handle_integrations(self):
        external_issue = self.request.external_issue
        if not external_issue:
            return

        if not self.event_type == self.CLOSED:
            return

        if integration_class := external_issue.integration_class:
            integration_class(dataspace=self.dataspace).post_comment(
                repo_id=external_issue.repo,
                issue_id=external_issue.issue_id,
                comment_body=self.text,
                base_url=external_issue.base_url,
            )


class RequestComment(AbstractRequestEvent):
    request = models.ForeignKey(
        to="workflow.Request",
        on_delete=models.CASCADE,
        related_name="comments",
    )

    class Meta:
        ordering = ["created_date"]
        unique_together = ("dataspace", "uuid")

    def __str__(self):
        return f"{self.user.username}: {self.text[:50]}..."

    def has_delete_permission(self, user):
        """
        Only the Commenter or an administrator with the proper permissions
        can delete a Comment.
        """
        return user == self.user or (
            user.is_staff and user.has_perm("workflow.delete_requestcomment")
        )

    def as_html(self):
        """
        Convert user provided commented content into HTML using markdown.
        The URLs are converted into links using the bleach Linkify feature.
        The HTML code is sanitized using bleach to prevent XSS attacks.
        The clean needs to be applied to the Markdown’s output, not the input.

        See https://michelf.ca/blog/2010/markdown-and-xss/ for details.

        See also the chapter about safe mode in
        https://python-markdown.github.io/change_log/release-3.0/
        """
        unsafe_html = markdown.markdown(
            text=self.text,
            extensions=["markdown.extensions.nl2br"],
        )

        # Using `Cleaner()` with the 1LinkifyFilter1 to clean and linkify in one pass.
        # See https://bleach.readthedocs.io/en/latest/linkify.html notes
        cleaner = Cleaner(
            tags=markdown_tags,
            attributes=markdown_attrs,
            filters=[LinkifyFilter],
        )
        html = cleaner.clean(unsafe_html)

        return mark_safe(html)

    def serialize_hook(self, hook):
        if "hooks.slack.com" in hook.target:
            return request_comment_slack_payload(self)

        from workflow.api import RequestCommentSerializer
        from workflow.api import RequestSerializer

        comment_serializer = RequestCommentSerializer(self, context={"request": None})
        request_serializer = RequestSerializer(self.request, context={"request": None})

        data = comment_serializer.data
        data["request"] = request_serializer.data

        return {
            "hook": hook.dict(),
            "data": data,
        }

    def handle_integrations(self):
        external_issue = self.request.external_issue
        if not external_issue:
            return

        if integration_class := external_issue.integration_class:
            integration_class(dataspace=self.dataspace).post_comment(
                repo_id=external_issue.repo,
                issue_id=external_issue.issue_id,
                comment_body=self.text,
                base_url=external_issue.base_url,
            )


class RequestTemplateQuerySet(DataspacedQuerySet):
    def actives(self):
        return self.filter(is_active=True)

    def for_content_type(self, content_type):
        """
        Return the active RequestTemplate instances within a given dataspace
        for a given model class using the content_type.
        """
        return self.filter(content_type=content_type)


class RequestTemplate(HistoryFieldsMixin, DataspacedModel):
    """
    WARNING: Modifying the schema of this model will require data migration
    (next to the usual schema migration).
    """

    name = models.CharField(
        max_length=100,
        help_text=_("Unique name of the template."),
    )

    description = models.TextField(
        verbose_name=_("Request header text"),
        help_text=_(
            "Provide a title and/or general instructions to the Requestor about this Request form."
        ),
    )

    content_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.PROTECT,
        verbose_name=_("object type"),
        limit_choices_to=CONTENT_TYPES,
        help_text=_("You can define one Request Template for each application object."),
    )

    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_(
            "Enable this to set the current form active. "
            "Only one Form can be active per content type."
        ),
    )

    include_applies_to = models.BooleanField(
        default=True,
        help_text=_(
            'Enable this to present an "Applies to" field to a requester creating a '
            "request based on this template, or anyone subsequently editing that request. "
            'Disable it for a request that does not need an "Applies to" reference.'
        ),
    )

    include_product = models.BooleanField(
        default=False,
        help_text=_(
            "Enable this to present a Product choice to a requester using this template. "
            "Disable it for a request that does not need a Product context."
        ),
    )

    default_assignee = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        limit_choices_to={"is_staff": True, "is_active": True},
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        serialize=False,
        help_text=_(
            "Optionally specify the application user that should be the first to review "
            "a request using this template, and should receive an email when the request "
            "is submitted."
        ),
    )

    issue_tracker_id = models.CharField(
        verbose_name=_("Issue Tracker ID"),
        max_length=1000,
        blank=True,
        help_text=_(
            "Link to associated issue in a tracking application, "
            "provided by the integration when the issue is created."
        ),
    )

    objects = DataspacedManager.from_queryset(RequestTemplateQuerySet)()

    class Meta:
        unique_together = (("dataspace", "name"), ("dataspace", "uuid"))
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("workflow:request_add", args=[self.uuid])

    @staticmethod
    def get_extra_relational_fields():
        return ["questions"]

    def create_request(self, **kwargs):
        if "assignee" not in kwargs and self.default_assignee:
            kwargs["assignee"] = self.default_assignee

        return Request.objects.create(
            request_template=self,
            content_type=self.content_type,
            dataspace=self.dataspace,
            **kwargs,
        )


class Question(DataspacedModel):
    """
    Represent one field of a RequestTemplate Form.

    WARNING: Modifying the schema of this model will require data migration
    (next to the usual schema migration).
    """

    template = models.ForeignKey(
        to="workflow.RequestTemplate",
        on_delete=models.CASCADE,
        related_name="questions",
    )

    label = models.CharField(
        max_length=255,
        help_text=_("Label for the form input."),
    )

    help_text = models.TextField(
        blank=True,
        help_text=_(
            "Descriptive text (instructions) to display to the Requestor below the question."
        ),
    )

    # (django.forms.fields.Field class, description)
    INPUT_TYPE_CHOICES = (
        ("CharField", _("Text")),
        ("TextField", _("Paragraph text")),
        ("BooleanField", _("Yes/No")),
        ("DateField", _("Date")),
    )

    input_type = models.CharField(
        max_length=30,
        choices=INPUT_TYPE_CHOICES,
    )

    is_required = models.BooleanField(
        default=False,
        help_text=_("Indicate if the requestor must enter a value in the answer"),
    )

    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        unique_together = ("dataspace", "uuid")

    def __str__(self):
        return self.label


class RequestMixin(models.Model):
    """Provide fields and methods for Request related models."""

    request_count = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
    )

    class Meta:
        abstract = True

    def get_requests(self, user):
        """
        We could use django.contrib.contenttypes.fields.GenericRelation
        instead but we don't want to avoid the cascade-deletion behavior.

        Private requests are included in the QuerySet but their content is not displayed.
        """
        return Request.objects.for_activity_tab(self, user)

    def count_requests(self):
        """
        Return the count of Request objects attached to this instance.
        Bypass the Product secured system since we need the proper count but do
        not have a user to provide.
        """
        return Request.objects.for_content_object(self).count()

    def update_request_count(self):
        """
        Update the `request_count` field on the instance.
        Using update() rather than save() to avoid noise in the history.
        The update is only applied if the current stored count is not the true
        database count.
        Return True if the request_count was updated.
        """
        model_class = self.__class__
        # We should have default=0 on the `request_count` field instead
        strored_count = self.request_count or 0
        true_count = self.count_requests()

        if strored_count != true_count:
            # Use the unsecured_manager to bypass the security system and get the proper count
            get_unsecured_manager(model_class).filter(pk=self.pk).update(request_count=true_count)
            msg = f"Updated <{model_class.__name__} id={self.pk}>.request_count={true_count}"
            logger.debug(msg)
            return True


def generate_attachment_path(instance, filename):
    return "{dataspace}/{content_type}/{request_uuid}/{timestamp}/{filename}".format(
        dataspace=instance.dataspace.name,
        content_type="requests",
        request_uuid=instance.request.uuid,
        timestamp=timezone.now().isoformat(),
        filename=filename,
    )


class RequestAttachment(HistoryDateFieldsMixin, DataspacedModel):
    request = models.ForeignKey(
        to="workflow.Request",
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    file = models.FileField(
        upload_to=generate_attachment_path,
        # Assuming the prefix is roughly 100 chars,
        # we need ~256 chars available for the actual filename.
        max_length=350,
    )

    uploader = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        editable=False,
    )

    class Meta:
        ordering = ["created_date"]
        unique_together = ("dataspace", "uuid")

    def __str__(self):
        return self.filename

    @cached_property
    def filename(self):
        return os.path.basename(self.file.name)

    def exists(self):
        """Return True if the file exists on the filesystem."""
        return self.file.storage.exists(self.file.name)

    def has_delete_permission(self, user):
        """
        Only the Uploader or an administrator with the proper permissions
        can delete an Attachment.
        """
        return user == self.uploader or (
            user.is_staff and user.has_perm("workflow.delete_requestattachment")
        )
