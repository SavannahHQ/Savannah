from django.db import models


class DeploymentChoicesCharField(models.CharField):
    """A CharField whose choices are decided by the deployment, not by the code.

    The enabled plugins and the installed time zone database differ from one
    installation to the next, so the choices are kept out of migrations: a
    different list is then not a model change.
    """

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop("choices", None)
        return name, path, args, kwargs
