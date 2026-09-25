from django.core.management.base import BaseCommand

from smartdorm.access_inventory import SNAPSHOT_PATH, render_access_table


class Command(BaseCommand):
    help = "Lists every API endpoint grouped by the access rule that guards it."

    def add_arguments(self, parser):
        parser.add_argument("--rule", help="Only show endpoints guarded by this rule, e.g. IsVerwaltung.")
        parser.add_argument(
            "--write-snapshot", action="store_true",
            help=f"Write the full table to {SNAPSHOT_PATH.name}, the reviewed record the tests compare against.",
        )

    def handle(self, *args, **options):
        if options["write_snapshot"]:
            SNAPSHOT_PATH.write_text(render_access_table())
            self.stdout.write(f"Wrote {SNAPSHOT_PATH}. Review the diff before committing it.")
            return

        self.stdout.write(render_access_table(options["rule"]) or "No matching endpoints.")
