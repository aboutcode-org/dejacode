#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from itertools import groupby
from operator import attrgetter
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.html import format_html

from dje.utils import get_preserved_filters
from dje.utils import group_by
from dje.views import DataspacedFilterView
from workflow.filters import RequestFilterSet
from workflow.forms import RequestAttachmentForm
from workflow.forms import RequestForm
from workflow.models import Request
from workflow.models import RequestAttachment
from workflow.models import RequestComment
from workflow.models import RequestEvent
from workflow.models import RequestTemplate
from workflow.notification import send_request_comment_notification
from workflow.notification import send_request_notification


class RequestListView(
    LoginRequiredMixin,
    DataspacedFilterView,
):
    """Display a list of current Request objects."""

    model = Request
    filterset_class = RequestFilterSet
    template_name = "workflow/request_list.html"
    template_list_table = "workflow/includes/request_list_table.html"
    paginate_by = 50

    def get_queryset(self):
        """
        Scope the QuerySet to the current user dataspace.

        Instances with is_private=True are included in this QuerySet but those
        will not be displayed unless the user is the requester or a superuser.
        """
        return (
            super()
            .get_queryset()
            .for_list_view(user=self.request.user)
            .order_by("-last_modified_date")
        )

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        # order_by content_type matter for proper following groupby
        request_templates_qs = (
            RequestTemplate.objects.scope(self.request.user.dataspace)
            .actives()
            .select_related("content_type")
            .order_by("content_type", "name")
        )

        grouped = groupby(request_templates_qs, attrgetter("content_type"))
        # Converting into a list in the view as Django templates does not handle
        # well generators.
        request_templates_grouped = [
            (content_type, list(request_templates)) for content_type, request_templates in grouped
        ]

        context_data.update(
            {
                "request_templates_grouped": request_templates_grouped,
            }
        )

        return context_data


@login_required
def request_add_view(request, template_uuid):
    """Form based on a RequestTemplate, to submit a new Request."""
    request_template = get_object_or_404(
        RequestTemplate, uuid=template_uuid, dataspace=request.user.dataspace
    )

    form = RequestForm(
        request.POST or None,
        user=request.user,
        request_template=request_template,
        initial={"object_id": request.GET.get("content_object_id")},
    )

    if form.is_valid():
        instance = form.save()

        if instance.is_draft:
            msg = "Your request was saved as a draft and self-assigned to you."
        else:
            send_request_notification(request, instance, created=True)
            msg = (
                f"Your request was successfully submitted as {instance} with an "
                f"email notification to the assignee, and a copy to you.\n"
                f"You can open your Request at any time to add Attachments and/or "
                f"Comments."
            )

        msg += (
            f"\n"
            f'<a href="{request_template.get_absolute_url()}">'
            f'Add a new "{request_template.name}" Request'
            f"</a>"
        )

        messages.success(request, format_html(msg))
        return redirect(instance.get_absolute_url())

    return render(request, "workflow/request_form.html", {"form": form})


@login_required
def request_edit_view(request, request_uuid):
    """Edit a Request."""
    qs = Request.objects.for_edit_view(request.user)
    request_instance = get_object_or_404(qs, uuid=request_uuid, dataspace=request.user.dataspace)
    request_template = request_instance.request_template

    has_change_permission = request.user.has_perm("workflow.change_request")
    has_edit_permission = request_instance.has_edit_permission(request.user)

    if not has_edit_permission and not has_change_permission:
        raise Http404("No match for the given query.")

    form = RequestForm(
        request.POST or None,
        user=request.user,
        request_template=request_template,
        instance=request_instance,
    )

    if form.is_valid() and form.has_changed():
        instance = form.save()

        updated_labels = []
        for field_name in form.changed_data:
            if field_name == "applies_to":
                updated_labels.append("Applies to")
            # `object_id` is already referenced with `applies_to`
            elif field_name != "object_id":
                label = str(form.fields.get(field_name).label)
                updated_labels.append(label)

        updated_labels = ", ".join(updated_labels)

        if instance.is_draft:
            msg = "Your request was updated as a draft and self-assigned to you."
        else:
            msg = (
                f"Your request was successfully edited as {instance} with "
                f"an email notification to the requester and the assignee."
            )
            extra = {"description": f"Updated: {updated_labels}."}
            send_request_notification(request, instance, created=False, extra=extra)

        request_instance.events.create(
            user=request.user,
            text=f"Request edited. Updated: {updated_labels}.",
            event_type=RequestEvent.EDIT,
            dataspace=request.user.dataspace,
        )

        msg += (
            f"\n"
            f'<a href="{request_template.get_absolute_url()}">'
            f'Add a new "{request_template.name}" Request'
            f"</a>"
        )

        messages.success(request, format_html(msg))
        return redirect(request_instance)

    elif not form.has_changed():
        messages.warning(request, "No fields changed.")
        return redirect(request_instance)

    return render(
        request, "workflow/request_form.html", {"form": form, "request_instance": request_instance}
    )


def get_productrelation_review_status_summary(product):
    """Return the count of Product relationships for each review_status as links."""
    product_url = product.get_absolute_url()
    tab = "inventory"

    querysets = {
        "catalog": product.productcomponents.catalogs(),
        "custom": product.productcomponents.customs(),
        "package": product.productpackages.all(),
    }

    status_summary = {}
    for object_type, queryset in querysets.items():
        links = []
        for data in group_by(queryset, field_name="review_status", values=["review_status__label"]):
            count, status_label = data["count"], data["review_status__label"]
            if count:
                link = (
                    f'<a href="{product_url}?{tab}-review_status={quote_plus(status_label)}'
                    f'&{tab}-object_type={object_type}#{tab}">'
                    f'  {status_label} ({data["count"]})'
                    f"</a>"
                )
                links.append(link)
        if links:
            status_summary[object_type] = links

    return status_summary


@login_required
def request_details_view(request, request_uuid):
    """
    Details view of an existing Request.
    A basic user can access his own Requests and public Requests.
    A superuser can access everything.
    """
    qs = Request.objects.for_details_view(user=request.user)
    request_instance = get_object_or_404(qs, uuid=request_uuid, dataspace=request.user.dataspace)

    if not request_instance.has_details_permission(request.user):
        raise Http404("No match for the given request.")

    closed_reason = request.POST.get("closed_reason")
    if closed_reason and request_instance.has_close_permission(request.user):
        request_instance.status = Request.Status.CLOSED
        request_instance.last_modified_by = request.user
        request_instance.save()
        event_instance = request_instance.events.create(
            user=request.user,
            text=closed_reason,
            event_type=RequestEvent.CLOSED,
            dataspace=request_instance.dataspace,
        )
        send_request_comment_notification(request, event_instance, closed=True)
        messages.success(request, f"Request {request_instance} closed")
        return redirect("workflow:request_list")

    delete_attachment_uuid = request.POST.get("delete_attachment_uuid")
    if delete_attachment_uuid:
        attachment = get_object_or_404(
            RequestAttachment, uuid=delete_attachment_uuid, dataspace=request.user.dataspace
        )
        if attachment.has_delete_permission(request.user):
            message = f'Attachment "{attachment.filename}" deleted'
            attachment.file.delete()  # Deletes the file from the filesystem
            attachment.delete()
            messages.success(request, message)
            return redirect(request_instance)

    comment_content = request.POST.get("comment_content")
    if comment_content:
        comment = request_instance.comments.create(
            user=request.user,
            text=comment_content,
            dataspace=request_instance.dataspace,
        )
        send_request_comment_notification(request, comment)
        messages.success(request, f"Comment for Request {request_instance} added.")
        return redirect(request_instance)

    delete_comment_uuid = request.POST.get("delete_comment_uuid")
    if delete_comment_uuid:
        comment = get_object_or_404(
            RequestComment, uuid=delete_comment_uuid, dataspace=request.user.dataspace
        )
        if comment.has_delete_permission(request.user):
            comment.delete()
            messages.success(request, "Comment deleted")
            return redirect(request_instance)

    if request.POST.get("submit") == RequestAttachmentForm.SUBMIT_VALUE:
        attachment_form = RequestAttachmentForm(
            request.POST, request.FILES, user=request.user, request_instance=request_instance
        )
        if attachment_form.is_valid():
            file_instance = attachment_form.save()
            request_instance.events.create(
                user=request.user,
                text=file_instance.filename,
                event_type=RequestEvent.ATTACHMENT,
                dataspace=request.user.dataspace,
            )
            messages.success(request, f'Attachment "{file_instance.filename}" added.')
            return redirect(request_instance)
        else:
            msg = "File upload error."
            file_error = "\n".join(attachment_form.errors.get("file"))
            if file_error:
                msg = f"{msg} {file_error}"
            messages.error(request, msg)
    else:
        attachment_form = RequestAttachmentForm(
            user=request.user, request_instance=request_instance
        )

    attachments = []
    for attachment in request_instance.attachments.all():
        if attachment.exists():
            attachment.can_delete = attachment.has_delete_permission(request.user)
            attachments.append(attachment)

    comments_and_events = []
    for comment in request_instance.comments.all():
        comment.can_delete = comment.has_delete_permission(request.user)
        comments_and_events.append(comment)
    comments_and_events.extend(request_instance.events.all())
    comments_and_events.sort(key=lambda x: x.created_date)

    context = {
        "attachment_form": attachment_form,
        "attachments": attachments,
        "comments_and_events": comments_and_events,
        "request_instance": request_instance,
        "opts": Request._meta,  # Required for the preserved_filters
        "preserved_filters": get_preserved_filters(request, Request),
        "has_change_permission": request.user.has_perm("workflow.change_request"),
        "has_edit_permission": request_instance.has_edit_permission(request.user),
        "has_close_permission": request_instance.has_close_permission(request.user),
        "has_change_productcomponent_permission": request.user.has_perm(
            "product_portfolio.change_productcomponent"
        ),
        "has_change_productpackage_permission": request.user.has_perm(
            "product_portfolio.change_productpackage"
        ),
    }

    content_object = request_instance.content_object
    if content_object and content_object._meta.model.__name__ == "Product":
        context["status_summary"] = get_productrelation_review_status_summary(content_object)

    request_instance.mark_all_notifications_as_read(request.user)

    return render(request, "workflow/request_details.html", context)


@login_required
def send_attachment_view(request, attachment_uuid):
    attachment = get_object_or_404(
        RequestAttachment,
        uuid=attachment_uuid,
        dataspace=request.user.dataspace,
    )

    error_conditions = [
        not attachment.request.has_details_permission(request.user),
        not attachment.exists(),
    ]

    if any(error_conditions):
        raise Http404

    return FileResponse(attachment.file.open("rb"), as_attachment=True)
