import datetime

import pytest
from django.utils import timezone


@pytest.fixture
def hoje(monkeypatch):
    """Fixa o "hoje" (timezone.localdate) em 20/11/2026 para testes com datas."""
    data = datetime.date(2026, 11, 20)
    original = timezone.localdate

    def localdate(value=None, timezone=None):
        if value is None and timezone is None:
            return data
        return original(value, timezone)

    monkeypatch.setattr("django.utils.timezone.localdate", localdate)
    return data
