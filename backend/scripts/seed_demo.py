#!/usr/bin/env python3
"""Seed fictional demo data for the LingDebate Wiki MVP slice.

All persons, records and texts are FICTIONAL, created only for demo.
Run:  ../.venv/bin/python scripts/seed_demo.py
Requires DATABASE_URL env (default: local lingdebate db).
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.features.identity.models as _idm  # noqa: F401  (register)
import app.features.taxonomy.models as _txm  # noqa: F401
import app.features.custom_fields.models  # noqa: F401
import app.features.bibliography.models as _bm  # noqa: F401
import app.features.discourses.models as _dm  # noqa: F401
import app.features.relations.models as _rm  # noqa: F401
from app.features.identity.models import Actor
from app.features.identity.security import hash_password
from app.features.taxonomy.models import Category, Issue, IssueCategory
from app.features.bibliography.models import (
    BibliographicContributor,
    BibliographicRecord,
    Person,
)
from app.features.discourses.models import Anchor, Discourse, IssueDiscourse, Paragraph
from app.features.relations.models import DimensionKind, Relation, RelationKind

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://lingdebate:lingdebate@localhost:5432/lingdebate"
)

FICT = ""

engine = create_engine(DATABASE_URL)


def main():
    with Session(engine) as db:
        if db.query(Category).count() > 0:
            print("demo data already seeded, skipping")
            return
        # owner
        owner = Actor(
            kind="owner",
            display_name="demo-owner",
            password_hash=hash_password("demo1234"),
            active=True,
        )
        db.add(owner)
        db.flush()
        aid = owner.id
        print("owner: demo-owner / demo1234  (演示专用，生产环境请更换)")

        def audit(obj):
            obj.created_by = aid
            obj.updated_by = aid
            return obj

        # categories
        root = audit(Category(name=FICT + "语言学理论", description="演示用分类根"))
        db.add(root)
        db.flush()
        gen = audit(Category(name=FICT + "生成语法", parent_id=root.id, description="演示"))
        fun = audit(Category(name=FICT + "功能语言学", parent_id=root.id, description="演示"))
        db.add_all([gen, fun])
        db.flush()

        # issue
        issue = audit(Issue(title=FICT + "虚构语 X 中“把”字句的句法地位", summary="演示用争议问题"))
        db.add(issue)
        db.flush()
        db.add(audit(IssueCategory(issue_id=issue.id, category_id=gen.id)))
        db.add(audit(IssueCategory(issue_id=issue.id, category_id=fun.id)))

        # persons (fictional)
        p1 = audit(Person(primary_name=FICT + "林虚构", note="演示人物"))
        p2 = audit(Person(primary_name=FICT + "陈假设", note="演示人物"))
        db.add_all([p1, p2])
        db.flush()

        # records (fictional)
        r1 = audit(
            BibliographicRecord(
                record_type="journal",
                title=FICT + "虚构语 X 把字句的生成句法分析",
                year=2024,
                language="zh",
                publication={"journal_title": FICT + "虚构语言学刊", "volume": "12", "pages": "1-20"},
            )
        )
        r2 = audit(
            BibliographicRecord(
                record_type="journal",
                title=FICT + "从功能视角重审虚构语 X 的把字句",
                year=2025,
                language="zh",
                publication={"journal_title": FICT + "虚构语言学刊", "volume": "13", "pages": "55-78"},
            )
        )
        db.add_all([r1, r2])
        db.flush()
        db.add(audit(BibliographicContributor(record_id=r1.id, person_id=p1.id, literal_name="林虚构", role="author", ordinal=1)))
        db.add(audit(BibliographicContributor(record_id=r2.id, person_id=p2.id, literal_name="陈假设", role="author", ordinal=1)))

        # discourses: 9 paragraphs (spec merge-case shape), then a 4-paragraph one
        paras1 = [
            "虚构语 X 是一种仅存在于演示数据中的语言，其“把”字句长期存在句法地位争议。",
            "林虚构（2024）认为，把字句中的“把”是轻动词 v 的显性实现，宾语经由内合并进入 Spec-vP。",
            "证据一：在把字句中，宾语不能再受“很”修饰，说明其已离开原位进入论元位置。",
            "证据二：把字句允许与处置义副词共现，而普通 SVO 句则受限，显示结构差异。",
            "证据三：方言比较显示，邻近虚构语 Y 缺少把标记，其宾语前置需借助焦点移位。",
            "然而，把字句的宾语仍保留部分话题属性，这与纯粹的论元分析存在张力。",
            "林虚构回应称，话题属性是语用层面的残留，不影响句法推导的核心结论。",
            "本文进一步提出，把标记的出现与事件的有界性相关，可由体貌投射统一解释。",
            "综上，把字句应分析为轻动词结构，而非话题化或焦点化的变体。",
        ]
        d1 = audit(
            Discourse(
                title=FICT + "虚构语 X 把字句的生成句法分析（全文）",
                bibliographic_record_id=r1.id,
                attribution_note="演示用完整论述",
            )
        )
        db.add(d1)
        db.flush()
        par_objs1 = []
        for i, t in enumerate(paras1, start=1):
            p = audit(Paragraph(discourse_id=d1.id, text=FICT + t, current_order=i))
            db.add(p)
            par_objs1.append(p)
        db.flush()

        paras2 = [
            "陈假设（2025）从功能视角出发，认为把字句的本质是处置义构式，而非轻动词结构。",
            "处置义要求施事对受事产生可观察的影响，这是把字句成立的语义条件。",
            "生成分析无法解释为何无影响动词不能进入把字句，而构式分析可以直接由语义模板推导。",
            "因此，把字句更宜视为形义配对固定的构式，其句法表现是语义要求的投射。",
        ]
        d2 = audit(
            Discourse(
                title=FICT + "从功能视角重审虚构语 X 的把字句（全文）",
                bibliographic_record_id=r2.id,
                attribution_note="演示用完整论述",
            )
        )
        db.add(d2)
        db.flush()
        par_objs2 = []
        for i, t in enumerate(paras2, start=1):
            p = audit(Paragraph(discourse_id=d2.id, text=FICT + t, current_order=i))
            db.add(p)
            par_objs2.append(p)
        db.flush()

        db.add(audit(IssueDiscourse(issue_id=issue.id, discourse_id=d1.id)))
        db.add(audit(IssueDiscourse(issue_id=issue.id, discourse_id=d2.id)))

        # anchors: d1 paragraphs 2-5 (spec user case shape)
        a1 = audit(
            Anchor(
                discourse_id=d1.id,
                start_paragraph_id=par_objs1[1].id,
                end_paragraph_id=par_objs1[4].id,
                title=FICT + "轻动词分析的三项证据",
            )
        )
        a2 = audit(
            Anchor(
                discourse_id=d2.id,
                start_paragraph_id=par_objs2[1].id,
                end_paragraph_id=par_objs2[2].id,
                title=FICT + "处置义语义条件",
            )
        )
        db.add_all([a1, a2])
        db.flush()

        # dictionaries
        kinds = [
            ("supports", "支持", "前者支持后者"),
            ("refutes", "反驳", "前者反驳后者"),
            ("extends", "接续", "前者接续后者"),
            ("reinterprets", "重释", "前者重释后者"),
        ]
        for i, (code, name_cn, desc) in enumerate(kinds):
            db.add(audit(RelationKind(code=code, name_cn=name_cn, description=desc, sort_order=i)))
        dims = [
            ("counterexample", "反例", "以反例质疑"),
            ("inconsistent_criterion", "标准不一", "评判标准不一致"),
            ("logical_issue", "逻辑问题", "推理存在逻辑问题"),
            ("paradigm_conflict", "范式冲突", "理论范式层面的冲突"),
        ]
        for i, (code, name_cn, desc) in enumerate(dims):
            db.add(audit(DimensionKind(code=code, name_cn=name_cn, description=desc, sort_order=i)))
        db.flush()

        # relation: a2 refutes a1, analyst_inferred
        rel = audit(
            Relation(
                issue_id=issue.id,
                source_anchor_id=a2.id,
                target_anchor_id=a1.id,
                relation_kind_id=db.query(RelationKind).filter_by(code="refutes").one().id,
                basis="analyst_inferred",
                reason=FICT + "处置义语义条件与轻动词结构分析存在解释张力",
                source_anchor_revision_at_creation=a2.revision,
                target_anchor_revision_at_creation=a1.revision,
            )
        )
        db.add(rel)
        db.commit()
        print("seeded: 1 issue, 2 discourses (9+4 paragraphs), 2 anchors, 1 relation")


if __name__ == "__main__":
    main()
