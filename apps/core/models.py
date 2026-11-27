import uuid

from django.db import models


class ModeloBase(models.Model):
    """Base abstrata de todos os models do projeto: UUID como PK e timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-criado_em"]
