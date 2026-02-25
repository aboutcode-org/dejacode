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
API_TOKEN_MODEL = "app.APIToken"  # noqa: S105
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
