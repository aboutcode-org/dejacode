# `aboutcode.api_auth`

Secured `APIToken` model and related `APITokenAuthentication` class.

### Install

```bash
pip install aboutcode.api_auth
```

### Define the APIToken model

In your main `models.py` module:

```python
from aboutcode.api_auth import AbstractAPIToken

class APIToken(AbstractAPIToken):
    class Meta:
        verbose_name = "API Token"
```

Generate and apply schema migration:

```bash
$ ./manage.py makemigrations
$ ./manage.py migrate
```

### Authenticator settings

Declare your `APIToken` model location in the `API_TOKEN_MODEL` setting:

```python
API_TOKEN_MODEL = "your_app.APIToken"  # noqa: S105
```

Declare the `APITokenAuthentication` authentication class as one of the 
`REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES`:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "aboutcode.api_auth.APITokenAuthentication",
    ),
}
```

### Views (optional)

Base views are provided for generating and revoking API keys.
They handle the token operations and redirect with a success message.

Subclass them in your app to add authentication requirements and configure
the success URL and message:

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy

from aboutcode.api_auth.views import BaseGenerateAPIKeyView
from aboutcode.api_auth.views import BaseRevokeAPIKeyView


class GenerateAPIKeyView(LoginRequiredMixin, BaseGenerateAPIKeyView):
    success_url = reverse_lazy("profile")
    success_message = (
        "Copy your API key now, it will not be shown again: <pre>{plain_key}</pre>"
    )


class RevokeAPIKeyView(LoginRequiredMixin, BaseRevokeAPIKeyView):
    success_url = reverse_lazy("profile")
    success_message = "API key revoked."
```

Wire them up in your `urls.py`:

```python
from your_app.views import GenerateAPIKeyView
from your_app.views import RevokeAPIKeyView

urlpatterns = [
    ...
    path("profile/api_key/generate/", GenerateAPIKeyView.as_view(), name="generate-api-key"),
    path("profile/api_key/revoke/", RevokeAPIKeyView.as_view(), name="revoke-api-key"),
]
```
