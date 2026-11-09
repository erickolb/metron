"""TEMPORARY experiment recorder. MUST be removed before upstream submission."""

import json
import os
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

MAX_NOTE_BYTES = 64 * 1024


class BoundedJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        content = stream.read(MAX_NOTE_BYTES + 1)
        if len(content) > MAX_NOTE_BYTES:
            raise ParseError("Experiment notes may not exceed 64 KiB.")
        return super().parse(BytesIO(content), media_type, parser_context)


class NoteReceiptSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    received_at = serializers.DateTimeField()


class NoteStorageUnavailable(APIException):
    status_code = 503
    default_detail = "Experiment note storage is unavailable. Please retry."


class ExperimentalNotetaker(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [BoundedJSONParser]

    @extend_schema(
        request={"application/json": {"type": "object", "additionalProperties": True}},
        responses={201: NoteReceiptSerializer},
        description="TEMPORARY: save a JSON object to private experimental feedback storage.",
    )
    def post(self, request):
        if not getattr(settings, "COVER_EXPERIMENT_NOTETAKER_ENABLED", False):
            return Response({"detail": "Not found."}, status=404)
        payload = request.data
        if not isinstance(payload, dict):
            raise ParseError("An experiment note must be a JSON object.")
        ident = str(uuid.uuid4())
        received = datetime.now(UTC).isoformat()
        record = {
            "id": ident,
            "received_at": received,
            "user_id": request.user.pk,
            "payload": payload,
        }
        try:
            encoded = json.dumps(record, ensure_ascii=False, allow_nan=False)
        except ValueError as exc:
            raise ParseError("Experiment notes must contain finite JSON numbers.") from exc
        directory = Path(settings.COVER_EXPERIMENT_NOTES_DIR)
        temporary = directory / f".{ident}.tmp"
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Same-directory rename makes only complete records visible to consumers.
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(directory / f"{ident}.json")
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise NoteStorageUnavailable from exc
        return Response(
            {"id": ident, "received_at": received},
            status=201,
            headers={"Cache-Control": "no-store"},
        )
