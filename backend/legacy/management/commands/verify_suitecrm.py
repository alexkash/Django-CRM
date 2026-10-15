"""Verification exits nonzero for corruption or user changes; never repairs data."""

from django.core.management.base import BaseCommand, CommandError

from common.models import Org
from legacy.importer.contracts import ImportContext, set_org
from legacy.importer.reader import SnapshotReader
from legacy.importer.reconcile import reconcile
from legacy.importer.reports import write_report
from legacy.importer.runner import validate_inputs
from legacy.models import LegacyImportBatch


class Command(BaseCommand):
    help = "Verify source coverage and native projections without replaying any write"

    def add_arguments(self, parser):
        parser.add_argument("--batch", required=True)
        parser.add_argument(
            "--org", help="Explicit target org; recommended for unambiguous operation"
        )
        parser.add_argument("--report", required=True)

    def handle(self, *args, **options):
        reader = None
        try:
            org_ids = (
                [options["org"]]
                if options["org"]
                else Org.objects.values_list("pk", flat=True).iterator()
            )
            batch = None
            for org_id in org_ids:
                set_org(org_id)
                batch = (
                    LegacyImportBatch.objects.filter(org_id=org_id, pk=options["batch"])
                    .select_related("source", "org")
                    .first()
                )
                if batch:
                    break
            if batch is None:
                raise ValueError("No such batch")
            reader = SnapshotReader(batch.source.metadata["snapshot_path"])
            ctx = ImportContext(batch.org, reader)
            validate_inputs(ctx)
            report = reconcile(ctx)
            if batch.state != "APPLIED":
                report.update(verified=False, batch_state=batch.state)
            report["batch_id"] = str(batch.pk)
            write_report(options["report"], report)
            if not report["verified"]:
                raise CommandError(
                    "SuiteCRM verification found differences; private report saved."
                )
            self.stdout.write(
                "SuiteCRM verified; history_rows="
                + str(report["history_total"])
                + "; files="
                + str(report["files"]["verified"])
            )
        except CommandError:
            raise
        except Exception as exc:
            write_report(
                options["report"], {"verified": False, "error_type": type(exc).__name__}
            )
            raise CommandError(
                "SuiteCRM verification failed ("
                + type(exc).__name__
                + "); private report saved."
            ) from None
        finally:
            if reader:
                reader.close()
            set_org("")
