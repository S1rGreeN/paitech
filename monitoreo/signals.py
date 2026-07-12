from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Acuicultor, Piscina

User = get_user_model()


@receiver(post_save, sender=User)
def crear_perfil_acuicultor(sender, instance, created, **kwargs):
    if not created:
        return

    nickname_base = instance.username or f"acuicultor-{instance.pk}"
    nickname = nickname_base
    contador = 1
    while Acuicultor.objects.filter(nickname=nickname).exists():
        contador += 1
        nickname = f"{nickname_base}-{contador}"

    perfil = Acuicultor.objects.create(user=instance, nickname=nickname)
    perfil.piscinas.set(Piscina.objects.filter(activa=True))


@receiver(post_save, sender=Piscina)
def compartir_piscina_con_acuicultores(sender, instance, created, **kwargs):
    if created and instance.activa:
        instance.acuicultores.set(Acuicultor.objects.all())
