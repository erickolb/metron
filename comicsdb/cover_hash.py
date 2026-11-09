"""Storage shared by the experimental 64-bit cover search."""

from django.db import models


def hash_integer_field():
    """PostgreSQL maintains a signed 64-bit representation, including bulk writes."""
    return models.GeneratedField(
        expression=models.Case(
            models.When(
                cover_hash__regex=r"^[0-9a-fA-F]{16}$",
                then=models.Func(
                    models.F("cover_hash"),
                    template="(('x' || %(expressions)s)::bit(64)::bigint)",
                    output_field=models.BigIntegerField(),
                ),
            ),
            default=None,
            output_field=models.BigIntegerField(),
        ),
        output_field=models.BigIntegerField(),
        db_persist=True,
        null=True,
    )
