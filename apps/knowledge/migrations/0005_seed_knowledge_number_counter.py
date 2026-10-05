"""为现有知识文章初始化全局 KB 编号计数器。"""

import re

from django.db import migrations

KB_NO_PATTERN = re.compile(r"KB-(\d{6})\Z")


def seed_knowledge_number_counter(apps, schema_editor):
    """从既有合法 KB 编号推导下一个可分配数字。"""
    Article = apps.get_model("knowledge", "Article")
    KnowledgeNumberCounter = apps.get_model("knowledge", "KnowledgeNumberCounter")

    highest_value = 0
    for kb_no in Article.objects.values_list("kb_no", flat=True).iterator():
        match = KB_NO_PATTERN.fullmatch(kb_no)
        if match is None:
            raise RuntimeError(
                f"Cannot seed knowledge number counter: invalid legacy kb_no {kb_no!r}."
            )
        highest_value = max(highest_value, int(match.group(1)))

    next_value = highest_value + 1
    counter, created = KnowledgeNumberCounter.objects.get_or_create(
        id=1,
        defaults={"next_value": next_value},
    )
    if not created and counter.next_value != next_value:
        raise RuntimeError(
            "Cannot seed knowledge number counter: existing singleton does not match "
            f"the deterministic value {next_value}."
        )


def unseed_knowledge_number_counter(apps, schema_editor):
    """Task 12B 尚无编号分配服务，回滚时仅删除本迁移初始化的单例。"""
    KnowledgeNumberCounter = apps.get_model("knowledge", "KnowledgeNumberCounter")
    KnowledgeNumberCounter.objects.filter(id=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0004_task12_authoring_schema"),
    ]

    operations = [
        migrations.RunPython(
            seed_knowledge_number_counter,
            unseed_knowledge_number_counter,
        ),
    ]
