from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import EventoSeguridad, Usuario
from .security import registrar_evento, revocar_todas_las_sesiones


@receiver(pre_save, sender=Usuario)
def detectar_cambio_sensible(sender, instance, **kwargs):
    instance._password_cambio_detectado = False
    instance._cuenta_desactivada_detectada = False
    if not instance.pk:
        return
    anterior = sender.objects.filter(pk=instance.pk).values("password", "is_active").first()
    if anterior:
        instance._password_cambio_detectado = anterior["password"] != instance.password
        instance._cuenta_desactivada_detectada = anterior["is_active"] and not instance.is_active


@receiver(post_save, sender=Usuario)
def proteger_tras_cambio_sensible(sender, instance, created, **kwargs):
    if created:
        return
    if getattr(instance, "_password_cambio_detectado", False):
        cambio_confirmado = getattr(instance, "_cambio_clave_confirmado", False)
        if not cambio_confirmado:
            sender.objects.filter(pk=instance.pk).update(debe_cambiar_clave=True)
            instance.debe_cambiar_clave = True
        revocar_todas_las_sesiones(instance, motivo="cambio_clave")
        registrar_evento(EventoSeguridad.Tipo.CLAVE_CAMBIADA, usuario=instance)
    if getattr(instance, "_cuenta_desactivada_detectada", False):
        revocar_todas_las_sesiones(instance, motivo="cuenta_desactivada")
        registrar_evento(EventoSeguridad.Tipo.CUENTA_DESACTIVADA, usuario=instance)
