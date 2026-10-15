"""Import only an explicitly bound immutable source snapshot."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from common.models import Org
from legacy.importer.contracts import ImportContext, set_org
from legacy.importer.reader import SnapshotReader
from legacy.importer.reports import write_report
from legacy.importer.runner import run_import
from legacy.models import LegacyImportBatch


class Command(BaseCommand):
    help = "Prepare, apply or resume the reviewed SuiteCRM snapshot migration"

    def add_arguments(self, parser):
        parser.add_argument("--snapshot", required=True)
        parser.add_argument("--org", required=True)
        parser.add_argument("--report")
        modes = parser.add_mutually_exclusive_group(required=True)
        for mode in ("prepare", "apply", "resume"):
            modes.add_argument(
                "--" + mode, action="store_const", dest="mode", const=mode
            )

    def handle(self, *args, **options):
        reader = None
        ctx = None
        report_path = options["report"] or str(
            Path(options["snapshot"]).parent
            / ("import-" + options["mode"] + "-report.json")
        )
        try:
            org = Org.objects.get(pk=options["org"])
            reader = SnapshotReader(options["snapshot"])
            ctx = ImportContext(org, reader)

            def phase_done(phase):
                self.stdout.write("Completed phase: " + phase)
                self.stdout.flush()

            report = run_import(ctx, options["mode"], on_phase=phase_done)
            write_report(report_path, report)
            self.stdout.write(
                "SuiteCRM "
                + options["mode"]
                + " complete; verified="
                + str(report.get("verified", False)).lower()
                + "; batch="
                + report["batch_id"]
            )
        except Exception as exc:
            report = {"verified": False, "error_type": type(exc).__name__}
            if ctx:
                set_org(ctx.org.pk)
                batch = LegacyImportBatch.objects.filter(
                    org=ctx.org, source=ctx.source
                ).first()
                if batch:
                    report.update(
                        batch.report,
                        batch_id=str(batch.pk),
                        checkpoint=batch.checkpoint,
                    )
                report["verified"] = False
            write_report(report_path, report)
            raise CommandError(
                "SuiteCRM import failed ("
                + type(exc).__name__
                + "); private report saved."
            ) from None
        finally:
            if reader:
                reader.close()
            set_org("")
