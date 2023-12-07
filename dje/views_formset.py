#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/nexB/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseRedirect
from django.views.generic import View
from django.views.generic.base import ContextMixin
from django.views.generic.base import TemplateResponseMixin


class FormSetMixin(ContextMixin):
    """
    Provide a way to show and handle a formset in a request.
    This code is based on django.views.generic.edit.FormMixin
    """

    initial = {}
    formset_class = None
    form_class = None
    success_url = None

    def get_initial(self):
        """Return the initial data to use for formsets on this view."""
        return self.initial.copy()

    def get_formset_class(self):
        """Return the formset class to use."""
        return self.formset_class

    def get_formset(self, formset_class=None):
        """Return an instance of the formset to be used in this view."""
        if formset_class is None:
            formset_class = self.get_formset_class()
        return formset_class(**self.get_formset_kwargs())

    def get_formset_kwargs(self):
        """Return the keyword arguments for instantiating the formset."""
        kwargs = {
            "initial": self.get_initial(),
        }

        if self.request.method in ("POST", "PUT"):
            kwargs.update(
                {
                    "data": self.request.POST,
                    "files": self.request.FILES,
                }
            )
        return kwargs

    def get_success_url(self):
        """Return the URL to redirect to after processing a valid formset."""
        if not self.success_url:
            raise ImproperlyConfigured("No URL to redirect to. Provide a success_url.")
        return str(self.success_url)  # success_url may be lazy

    def formset_valid(self, formset):
        """If the formset is valid, redirect to the supplied URL."""
        return HttpResponseRedirect(self.get_success_url())

    def formset_invalid(self, formset):
        """If the formset is invalid, render the invalid formset."""
        return self.render_to_response(self.get_context_data(formset=formset))

    def get_context_data(self, **kwargs):
        """Insert the formset into the context dict."""
        if "formset" not in kwargs:
            kwargs["formset"] = self.get_formset()
        return super().get_context_data(**kwargs)


class ProcessFormSetView(View):
    """
    Render a formset on GET and processes it on POST.
    This code is based on django.views.generic.edit.ProcessFormView
    """

    def get(self, request, *args, **kwargs):
        """Handle GET requests: instantiate a blank version of the formset."""
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a formset instance with the passed
        POST variables and then check if it's valid.
        """
        formset = self.get_formset()
        if formset.is_valid():
            return self.formset_valid(formset)
        else:
            return self.formset_invalid(formset)

    # PUT is a valid HTTP verb for creating (with a known URL) or editing an
    # object, note that browsers only support POST for now.
    def put(self, *args, **kwargs):
        return self.post(*args, **kwargs)


class BaseFormSetView(FormSetMixin, ProcessFormSetView):
    """A base view for displaying a formset."""


class FormSetView(TemplateResponseMixin, BaseFormSetView):
    """A view for displaying a formset and rendering a template response."""
