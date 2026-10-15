"""Source labels stay distinct; unfamiliar deal kinds are never guessed."""

from leads.models import LeadPipeline, LeadStage
from opportunity.models import DealPipeline, DealStage

from .identity import stable_id

LEAD_STATUS = {
    "New": "assigned",
    "In Process": "in process",
    "Converted": "converted",
    "Remember": "recycled",
    "Incorrect": "closed",
    "Nontargeted": "closed",
}


def _owned_config(ctx, model, kind, key, **fields):
    pk = stable_id("configuration", kind + ":" + key)
    owned = ctx.source.metadata.setdefault("generated_objects", {})
    obj = model.objects.filter(pk=pk).first()
    if obj:
        if owned.get(str(pk)) != model._meta.label or obj.org_id != ctx.org.id:
            raise ValueError(
                "Generated configuration identity conflicts with existing target"
            )
        return obj
    obj = model(id=pk, org=ctx.org, **fields)
    model.objects.bulk_create([obj])
    owned[str(pk)] = model._meta.label
    type(ctx.source).objects.filter(pk=ctx.source.pk).update(
        metadata=ctx.source.metadata
    )
    return obj


def lead_stage(ctx, label):
    cache = getattr(ctx, "lead_stage_cache", None)
    if cache is None:
        ctx.lead_stage_cache = cache = {}
    if label in cache:
        return cache[label]
    if label not in LEAD_STATUS:
        raise ValueError(
            "Source lead status requires explicit classification: " + str(label)
        )
    pipeline = _owned_config(
        ctx,
        LeadPipeline,
        "lead_pipeline",
        "main",
        name="SuiteCRM",
        is_default=not LeadPipeline.objects.filter(
            org=ctx.org, is_default=True
        ).exists(),
    )
    stage = _owned_config(
        ctx,
        LeadStage,
        "lead_stage",
        label,
        pipeline=pipeline,
        name=label,
        order=list(LEAD_STATUS).index(label),
        maps_to_status=LEAD_STATUS[label],
        stage_type="won"
        if label == "Converted"
        else "lost"
        if LEAD_STATUS[label] in ("closed", "recycled")
        else "open",
    )
    cache[label] = stage
    return stage


def deal_stage(ctx, label):
    cache = getattr(ctx, "deal_stage_cache", None)
    if cache is None:
        ctx.deal_stage_cache = cache = {}
    if label in cache:
        return cache[label]
    pipeline = _owned_config(
        ctx,
        DealPipeline,
        "deal_pipeline",
        "main",
        name="SuiteCRM",
        is_default=not DealPipeline.objects.filter(
            org=ctx.org, is_default=True
        ).exists(),
    )
    code = "SUITE_" + str(stable_id("sales_stage", label)).replace("-", "").upper()[:32]
    kind = {"Closed Won": "won", "Closed Lost": "lost"}.get(label, "unknown")
    stage = _owned_config(
        ctx,
        DealStage,
        "deal_stage",
        label,
        pipeline=pipeline,
        code=code,
        label=label or "Unspecified",
        kind=kind,
        order=DealStage.objects.filter(pipeline=pipeline).count(),
    )
    # Keep a normal creation path even when the source has no classified open stage.
    for code2, label2, kind2 in [
        ("NEW", "New", "open"),
        ("WON", "Won", "won"),
        ("LOST", "Lost", "lost"),
    ]:
        if not DealStage.objects.filter(pipeline=pipeline, kind=kind2).exists():
            _owned_config(
                ctx,
                DealStage,
                "deal_seed",
                code2,
                pipeline=pipeline,
                code="SUITE_DEFAULT_" + code2,
                label=label2,
                kind=kind2,
                order=1000 + ["NEW", "WON", "LOST"].index(code2),
            )
    cache[label] = (pipeline, stage)
    return pipeline, stage
