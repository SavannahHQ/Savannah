from django.apps import AppConfig

class CormConfig(AppConfig):
    name = 'corm'
    verbose_name = "Community Resource Manager"

    def ready(self):
        from corm.plugins import install_plugins
        install_plugins()