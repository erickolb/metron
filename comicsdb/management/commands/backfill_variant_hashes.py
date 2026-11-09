"""Explicit image reads belong in a resumable command, never a schema migration."""

from django.core.management.base import BaseCommand, CommandError

from comicsdb.models.issue import generate_cover_hash
from comicsdb.models.variant import Variant


class Command(BaseCommand):
    help = "Hash existing variant images for cover search (reads configured media storage)."

    def handle(self, *args, **options):
        completed = failed = 0
        rows = Variant.objects.filter(cover_hash="").exclude(image="").only("pk", "image")
        for variant in rows.iterator(chunk_size=200):
            cover_hash = generate_cover_hash(variant)
            if not cover_hash:
                failed += 1
                self.stderr.write(
                    f"Unable to hash variant {variant.pk}; rerun after repairing media."
                )
                continue
            Variant.objects.filter(pk=variant.pk, image=variant.image.name).update(
                cover_hash=cover_hash
            )
            completed += 1
        self.stdout.write(f"Hashed {completed} variants; {failed} unavailable images.")
        if failed:
            raise CommandError("Some variants remain unsearchable; completed hashes are retained.")
