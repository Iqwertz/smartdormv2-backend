from django.core.management.base import BaseCommand

from smartdorm.utils.log_utils import cleanup_log_file


class Command(BaseCommand):
    help = "Removes log entries older than a configured number of days from smartdorm.log."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete log entries older than this many days (default: 30).",
        )

    def handle(self, *args, **options):
        days = max(1, options["days"])
        result = cleanup_log_file(days=days)

        self.stdout.write(
            self.style.SUCCESS(
                f"Log cleanup finished. Removed {result['removed']} entries, kept {result['kept']} of {result['total']} total entries."
            )
        )
