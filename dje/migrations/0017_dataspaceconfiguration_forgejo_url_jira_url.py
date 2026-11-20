from urllib.parse import urlparse

from django.db import migrations, models


def get_base_url(url):
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}"


def set_integration_urls_from_request_templates(apps, schema_editor):
    """
    Set the Forgejo and Jira URLs from the Request templates of each Dataspace,
    when all its templates use a single base URL for that integration.
    """
    DataspaceConfiguration = apps.get_model("dje", "DataspaceConfiguration")
    RequestTemplate = apps.get_model("workflow", "RequestTemplate")

    configurations = DataspaceConfiguration.objects.exclude(forgejo_token="", jira_token="")
    for configuration in configurations:
        issue_tracker_ids = (
            RequestTemplate.objects.filter(dataspace_id=configuration.dataspace_id)
            .exclude(issue_tracker_id="")
            .values_list("issue_tracker_id", flat=True)
        )
        base_urls = {get_base_url(issue_tracker_id) for issue_tracker_id in issue_tracker_ids}
        forgejo_urls = {url for url in base_urls if "forgejo" in urlparse(url).netloc}
        jira_urls = {url for url in base_urls if urlparse(url).netloc.endswith(".atlassian.net")}

        if configuration.forgejo_token and len(forgejo_urls) == 1:
            configuration.forgejo_url = forgejo_urls.pop()
        if configuration.jira_token and len(jira_urls) == 1:
            configuration.jira_url = jira_urls.pop()
        configuration.save(update_fields=["forgejo_url", "jira_url"])


class Migration(migrations.Migration):

    dependencies = [
        ("dje", "0016_dataspaceconfiguration_policy_rules_config"),
        ("workflow", "0003_externalissuelink_base_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataspaceconfiguration",
            name="forgejo_url",
            field=models.URLField(blank=True, help_text="Base URL of your Forgejo instance, such as https://forgejo.example.com. The Forgejo token is only sent to this URL.", verbose_name="Forgejo URL"),
        ),
        migrations.AddField(
            model_name="dataspaceconfiguration",
            name="jira_url",
            field=models.URLField(blank=True, help_text="Base URL of your Jira Cloud site, such as https://example.atlassian.net. The Jira credentials are only sent to this URL.", verbose_name="Jira URL"),
        ),
        migrations.RunPython(
            set_integration_urls_from_request_templates, reverse_code=migrations.RunPython.noop
        ),
    ]
