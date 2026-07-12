from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from jinja2 import Environment


def url(view_name, *args, **kwargs):
    return reverse(
        view_name,
        args=args or None,
        kwargs=kwargs or None,
    )


def environment(**options):
    env = Environment(**options)
    env.globals.update(
        {
            "static": static,
            "url": url,
            "now": timezone.now,
        }
    )
    return env
