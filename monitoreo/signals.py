from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Acuicultor, Comunidad

Usuario = get_user_model()


@receiver(post_save, sender=Usuario)
def crear_perfil_acuicultor(sender, instance, created, **kwargs):
    if not created:
        return

    comunidad, _ = Comunidad.objects.get_or_create(
        codigo="paipayales",
        defaults={"nombre": "Paipayales"},
    )
    nombre = instance.get_full_name().strip() or instance.email.split("@", 1)[0]
    nickname = nombre
    contador = 1
    while Acuicultor.objects.filter(comunidad=comunidad, nickname=nickname).exists():
        contador += 1
        nickname = f"{nombre}-{contador}"

    Acuicultor.objects.create(
        user=instance,
        comunidad=comunidad,
        nickname=nickname,
        rol=(
            Acuicultor.Rol.ADMINISTRADOR
            if instance.is_superuser
            else Acuicultor.Rol.ACUICULTOR
        ),
    )
