from gunicorn.app.base import BaseApplication

from app.settings import Settings

settings = Settings()


class GunicornServer(BaseApplication):
    """
    This class should be used as the entry point to the app if youre packaging your app as a zipapp
    """
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items()
                  if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def run():
    options = {
        'bind': f'0.0.0.0:{settings.app_port}',
        'workers': 4,
        'worker_class': 'uvicorn.workers.UvicornWorker',
        'timeout': settings.worker_timeout,
    }
    GunicornServer('app.main:app', options).run()