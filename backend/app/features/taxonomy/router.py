from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from typing import Optional, Any, List, Dict
import uuid

from app.db.session import get_db
from app.features.identity.deps import get_current_actor, get_public_or_actor
from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.core.crud import get_or_404, archive_entity, restore_entity, apply_update
from app.features.taxonomy.models import Category, Issue, IssueCategory


router_cat = APIRouter(prefix="/categories", dependencies=[Depends(get_public_or_actor)])
router_issue = APIRouter(prefix="/issues", dependencies=[Depends(get_public_or_actor)])


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = ""
    parent_id: Optional[Any] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CategoryMove(BaseModel):
    new_parent_id: Optional[Any] = None


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    summary: Optional[str] = ""


def _ser_id(v):
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def _cat_detail(c):
    d: Dict[str, Any] = {
        "id": _ser_id(getattr(c, "id", None)),
        "name": getattr(c, "name", None),
        "description": getattr(c, "description", ""),
        "parent_id": _ser_id(getattr(c, "parent_id", None)),
    }
    if hasattr(c, "sort_key"):
        try:
            d["sort_key"] = getattr(c, "sort_key")
        except Exception:
            pass
    if hasattr(c, "revision"):
        try:
            d["revision"] = getattr(c, "revision")
        except Exception:
            pass
    if hasattr(c, "created_by"):
        try:
            d["created_by"] = _ser_id(getattr(c, "created_by"))
        except Exception:
            pass
    if hasattr(c, "updated_by"):
        try:
            d["updated_by"] = _ser_id(getattr(c, "updated_by"))
        except Exception:
            pass
    for k in ("created_at", "updated_at", "archived_at"):
        if hasattr(c, k):
            try:
                d[k] = getattr(c, k)
            except Exception:
                pass
    return d


def _issue_to_dict(o):
    d: Dict[str, Any] = {
        "id": _ser_id(getattr(o, "id", None)),
        "title": getattr(o, "title", None),
        "summary": getattr(o, "summary", ""),
    }
    if hasattr(o, "revision"):
        try:
            d["revision"] = getattr(o, "revision")
        except Exception:
            pass
    if hasattr(o, "created_by"):
        try:
            d["created_by"] = _ser_id(getattr(o, "created_by"))
        except Exception:
            pass
    if hasattr(o, "updated_by"):
        try:
            d["updated_by"] = _ser_id(getattr(o, "updated_by"))
        except Exception:
            pass
    for k in ("created_at", "updated_at", "archived_at"):
        if hasattr(o, k):
            try:
                d[k] = getattr(o, k)
            except Exception:
                pass
    return d


def _find_category(db: Session, cid):
    if cid is None:
        return None
    try:
        obj = db.query(Category).filter(Category.id == cid).first()
        if obj is not None:
            return obj
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    try:
        all_objs = db.query(Category).all()
        scid = str(cid)
        for o in all_objs:
            try:
                if str(getattr(o, "id", None)) == scid:
                    return o
            except Exception:
                continue
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return None


def _find_issue(db: Session, iid):
    if iid is None:
        return None
    try:
        obj = db.query(Issue).filter(Issue.id == iid).first()
        if obj is not None:
            return obj
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    try:
        all_objs = db.query(Issue).all()
        siid = str(iid)
        for o in all_objs:
            try:
                if str(getattr(o, "id", None)) == siid:
                    return o
            except Exception:
                continue
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return None


def _get_category_or_404(db: Session, cid):
    cat = _find_category(db, cid)
    if cat is None:
        raise ApiError("not_found", 404)
    try:
        if getattr(cat, "archived_at", None) is not None:
            raise ApiError("not_found", 404)
    except ApiError:
        raise
    except Exception:
        pass
    return cat


def _is_descendant(db: Session, ancestor_id, candidate_id):
    if candidate_id is None:
        return False
    try:
        all_cats = db.query(Category).all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False
    parent_map: Dict[str, Any] = {}
    for c in all_cats:
        try:
            parent_map[str(c.id)] = str(c.parent_id) if c.parent_id is not None else None
        except Exception:
            continue
    anc = str(ancestor_id)
    cur = str(candidate_id)
    seen = set()
    while cur is not None and cur not in seen:
        if cur == anc:
            return True
        seen.add(cur)
        if cur not in parent_map:
            break
        cur = parent_map[cur]
    return False


def _ensure_sort_key_default(obj):
    try:
        if hasattr(obj.__class__, "__table__") and "sort_key" in obj.__class__.__table__.columns:
            col = obj.__class__.__table__.columns["sort_key"]
            try:
                from sqlalchemy import Integer as _SAInt
                if isinstance(col.type, _SAInt):
                    setattr(obj, "sort_key", 0)
                else:
                    setattr(obj, "sort_key", "")
            except Exception:
                pass
    except Exception:
        pass


def _apply_audit_create(obj, actor):
    try:
        aid = getattr(actor, "id", None)
    except Exception:
        aid = None
    if hasattr(obj, "created_by"):
        try:
            setattr(obj, "created_by", aid)
        except Exception:
            pass
    if hasattr(obj, "updated_by"):
        try:
            setattr(obj, "updated_by", aid)
        except Exception:
            pass
    if hasattr(obj, "revision"):
        try:
            setattr(obj, "revision", 1)
        except Exception:
            pass


def _apply_audit_update(obj, actor):
    try:
        aid = getattr(actor, "id", None)
    except Exception:
        aid = None
    if hasattr(obj, "updated_by"):
        try:
            setattr(obj, "updated_by", aid)
        except Exception:
            pass
    if hasattr(obj, "revision"):
        try:
            cur = getattr(obj, "revision", None)
            if cur is None:
                setattr(obj, "revision", 1)
            else:
                setattr(obj, "revision", int(cur) + 1)
        except Exception:
            try:
                setattr(obj, "revision", 1)
            except Exception:
                pass


def _fetch_discourses(db: Session, issue_db_id):
    try:
        bind = None
        try:
            bind = db.get_bind()  # type: ignore
        except Exception:
            try:
                bind = db.bind  # type: ignore
            except Exception:
                bind = None
        if bind is not None:
            try:
                from sqlalchemy import inspect as _sa_inspect
                insp = _sa_inspect(bind)
                tables = insp.get_table_names()
                discourse_table = None
                for t in tables:
                    if t == "discourses":
                        discourse_table = t
                        break
                if discourse_table is None:
                    for t in tables:
                        lt = t.lower()
                        if lt in ("discourse", "discussions", "discussion"):
                            discourse_table = t
                            break
                if discourse_table is None:
                    for t in tables:
                        lt = t.lower()
                        if ("discourse" in lt or "discussion" in lt) and not lt.startswith("issue_"):
                            discourse_table = t
                            break
                link_table = None
                for t in tables:
                    if t == "issue_discourses":
                        link_table = t
                        break
                if link_table is None:
                    for t in tables:
                        lt = t.lower()
                        if lt in ("issue_discourse", "issues_discourses", "issue_discussions", "issue_discussion"):
                            link_table = t
                            break
                if link_table is None:
                    for t in tables:
                        lt = t.lower()
                        if lt.startswith("issue_") and ("discourse" in lt or "discussion" in lt):
                            link_table = t
                            break
                if discourse_table is not None and link_table is not None:
                    try:
                        d_cols = {c["name"]: c for c in insp.get_columns(discourse_table)}
                        j_cols = {c["name"]: c for c in insp.get_columns(link_table)}
                    except Exception:
                        d_cols = {}
                        j_cols = {}
                    title_col = None
                    if "title" in d_cols:
                        title_col = "title"
                    elif "name" in d_cols:
                        title_col = "name"
                    issue_col = None
                    for cand in ("issue_id", "issues_id"):
                        if cand in j_cols:
                            issue_col = cand
                            break
                    if issue_col is None:
                        for k in j_cols:
                            if "issue" in k.lower():
                                issue_col = k
                                break
                    disc_col = None
                    for cand in ("discourse_id", "discourses_id", "discussion_id", "discussions_id"):
                        if cand in j_cols:
                            disc_col = cand
                            break
                    if disc_col is None:
                        for k in j_cols:
                            lk = k.lower()
                            if ("discourse" in lk or "discussion" in lk) and k != issue_col:
                                disc_col = k
                                break
                    if title_col is not None and issue_col is not None and disc_col is not None:
                        d_arch = "archived_at" if "archived_at" in d_cols else None
                        j_arch = "archived_at" if "archived_at" in j_cols else None
                        sql = f'SELECT d.id as id, d."{title_col}" as title FROM "{discourse_table}" d JOIN "{link_table}" j ON j."{disc_col}" = d.id WHERE j."{issue_col}" = :iid'
                        if j_arch is not None:
                            sql += f' AND j."{j_arch}" IS NULL'
                        if d_arch is not None:
                            sql += f' AND d."{d_arch}" IS NULL'
                        try:
                            rows = db.execute(text(sql), {"iid": issue_db_id}).mappings().all()
                            return [{"id": _ser_id(r["id"]), "title": r["title"]} for r in rows]
                        except Exception:
                            try:
                                db.rollback()
                            except Exception:
                                pass
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    try:
        sql = "SELECT d.id as id, d.title as title FROM discourses d JOIN issue_discourses j ON j.discourse_id = d.id WHERE j.issue_id = :iid AND j.archived_at IS NULL AND d.archived_at IS NULL"
        rows = db.execute(text(sql), {"iid": issue_db_id}).mappings().all()
        return [{"id": _ser_id(r["id"]), "title": r["title"]} for r in rows]
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return []


@router_cat.get("/tree")
def get_category_tree(db: Session = Depends(get_db)):
    try:
        q = db.query(Category).filter(Category.archived_at.is_(None))
        if hasattr(Category, "sort_key"):
            try:
                q = q.order_by(Category.sort_key)
            except Exception:
                pass
        cats = q.all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        cats = []
    nodes: Dict[str, Dict[str, Any]] = {}
    for c in cats:
        try:
            nid = str(c.id)
            nodes[nid] = {
                "id": _ser_id(c.id),
                "name": getattr(c, "name", None),
                "description": getattr(c, "description", ""),
                "parent_id": _ser_id(getattr(c, "parent_id", None)),
                "children": [],
            }
        except Exception:
            continue
    roots: List[Dict[str, Any]] = []
    for c in cats:
        try:
            nid = str(c.id)
            node = nodes.get(nid)
            if node is None:
                continue
            pid = getattr(c, "parent_id", None)
            if pid is None:
                roots.append(node)
            else:
                pkey = str(pid)
                parent_node = nodes.get(pkey)
                if parent_node is None:
                    roots.append(node)
                else:
                    parent_node["children"].append(node)
        except Exception:
            continue
    return {"data": roots}


@router_cat.get("/tree-with-issues")
def get_category_tree_with_issues(db: Session = Depends(get_db)):
    """分类树，每个节点附带其直属词条（issues）。"""
    try:
        cats = db.query(Category).filter(Category.archived_at.is_(None)).order_by(Category.sort_key).all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        cats = []
    # 取所有 issue_category 映射
    try:
        mappings = db.query(IssueCategory).filter(IssueCategory.archived_at.is_(None)).all()
    except Exception:
        mappings = []
    # 取所有未归档词条
    try:
        issues = db.query(Issue).filter(Issue.archived_at.is_(None)).all()
    except Exception:
        issues = []
    issue_by_id = {str(i.id): _issue_to_dict(i) for i in issues}
    issues_by_cat: Dict[str, list] = {}
    for m in mappings:
        cid = str(m.category_id)
        iid = str(m.issue_id)
        if iid in issue_by_id:
            issues_by_cat.setdefault(cid, []).append(issue_by_id[iid])

    nodes: Dict[str, Dict[str, Any]] = {}
    for c in cats:
        nid = str(c.id)
        nodes[nid] = {
            "id": _ser_id(c.id),
            "name": getattr(c, "name", None),
            "description": getattr(c, "description", ""),
            "parent_id": _ser_id(getattr(c, "parent_id", None)),
            "issues": issues_by_cat.get(nid, []),
            "children": [],
        }
    roots: List[Dict[str, Any]] = []
    for c in cats:
        nid = str(c.id)
        node = nodes.get(nid)
        if node is None:
            continue
        pid = getattr(c, "parent_id", None)
        if pid is None:
            roots.append(node)
        else:
            parent_node = nodes.get(str(pid))
            if parent_node is None:
                roots.append(node)
            else:
                parent_node["children"].append(node)
    # 未挂靠任何分类的词条
    assigned = set()
    for lst in issues_by_cat.values():
        for it in lst:
            assigned.add(it["id"])
    orphans = [issue_by_id[k] for k in issue_by_id if k not in assigned]
    return {"data": roots, "orphans": orphans}


@router_cat.post("/")
@router_cat.post("")
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    if payload.parent_id is not None:
        parent = _find_category(db, payload.parent_id)
        if parent is None or getattr(parent, "archived_at", None) is not None:
            raise ApiError("validation_error", 422)
    cat = Category()
    cat.name = payload.name
    cat.description = payload.description if payload.description is not None else ""
    cat.parent_id = payload.parent_id
    _ensure_sort_key_default(cat)
    _apply_audit_create(cat, actor)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"data": _cat_detail(cat)}


@router_cat.get("/{category_id}")
def get_category(category_id: str, db: Session = Depends(get_db)):
    cat = _get_category_or_404(db, category_id)
    return {"data": _cat_detail(cat)}


@router_cat.patch("/{category_id}")
def update_category(category_id: str, payload: CategoryUpdate, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    cat = _get_category_or_404(db, category_id)
    if payload.name is not None:
        cat.name = payload.name
    if payload.description is not None:
        cat.description = payload.description
    _apply_audit_update(cat, actor)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"data": _cat_detail(cat)}


@router_cat.post("/{category_id}/move")
def move_category(category_id: str, payload: CategoryMove, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    cat = _get_category_or_404(db, category_id)
    new_parent_id = payload.new_parent_id
    if new_parent_id is not None and str(new_parent_id) == str(cat.id):
        raise ApiError("validation_error", 422)
    if new_parent_id is None:
        pass
    else:
        parent = _find_category(db, new_parent_id)
        if parent is None or getattr(parent, "archived_at", None) is not None:
            raise ApiError("validation_error", 422)
        if _is_descendant(db, cat.id, new_parent_id):
            raise ApiError("validation_error", 422)
    cat.parent_id = new_parent_id
    _apply_audit_update(cat, actor)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"data": _cat_detail(cat)}


@router_issue.get("/")
@router_issue.get("")
def list_issues(limit: int = 30, offset: int = 0, db: Session = Depends(get_db)):
    try:
        limit = int(limit)
    except Exception:
        limit = 30
    try:
        offset = int(offset)
    except Exception:
        offset = 0
    if limit < 1:
        limit = 30
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0
    q = db.query(Issue).filter(Issue.archived_at.is_(None))
    try:
        total = q.count()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        total = 0
    if hasattr(Issue, "created_at"):
        try:
            q = q.order_by(Issue.created_at.desc())
        except Exception:
            pass
    try:
        items_raw = q.offset(offset).limit(limit).all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        items_raw = []
    items = [_issue_to_dict(o) for o in items_raw]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router_issue.post("/")
@router_issue.post("")
def create_issue(payload: IssueCreate, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    iss = Issue()
    iss.title = payload.title
    iss.summary = payload.summary if payload.summary is not None else ""
    _apply_audit_create(iss, actor)
    db.add(iss)
    db.commit()
    db.refresh(iss)
    data = _issue_to_dict(iss)
    resp: Dict[str, Any] = {"data": data}
    for k, v in data.items():
        if k not in resp:
            resp[k] = v
    return resp


@router_issue.get("/{issue_id}/discourses")
def get_issue_discourses(issue_id: str, db: Session = Depends(get_db)):
    iss = _find_issue(db, issue_id)
    if iss is None or getattr(iss, "archived_at", None) is not None:
        raise ApiError("not_found", 404)
    try:
        db_id = getattr(iss, "id")
    except Exception:
        db_id = issue_id
    items = _fetch_discourses(db, db_id)
    return {"data": items}


@router_issue.get("/{issue_id}")
def get_issue(issue_id: str, db: Session = Depends(get_db)):
    iss = _find_issue(db, issue_id)
    if iss is None or getattr(iss, "archived_at", None) is not None:
        raise ApiError("not_found", 404)
    data = _issue_to_dict(iss)
    resp: Dict[str, Any] = {"data": data}
    for k, v in data.items():
        if k not in resp:
            resp[k] = v
    return resp


class IssueCategoryLink(BaseModel):
    category_id: str


@router_issue.get("/{issue_id}/categories")
def list_issue_categories(issue_id: str, db: Session = Depends(get_db)):
    """词条挂靠的分类列表。"""
    iss = _find_issue(db, issue_id)
    if iss is None or getattr(iss, "archived_at", None) is not None:
        raise ApiError("not_found", 404)
    links = (
        db.query(IssueCategory)
        .filter(IssueCategory.issue_id == iss.id, IssueCategory.archived_at.is_(None))
        .all()
    )
    out = []
    for lk in links:
        cat = _find_category(db, lk.category_id)
        if cat is None or getattr(cat, "archived_at", None) is not None:
            continue
        out.append({"id": _ser_id(cat.id), "name": getattr(cat, "name", "")})
    return {"data": out}


@router_issue.post("/{issue_id}/categories")
def link_issue_category(issue_id: str, payload: IssueCategoryLink, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """词条挂靠到分类。"""
    iss = _find_issue(db, issue_id)
    if iss is None or getattr(iss, "archived_at", None) is not None:
        raise ApiError("not_found", 404)
    cat = _find_category(db, payload.category_id)
    if cat is None or getattr(cat, "archived_at", None) is not None:
        raise ApiError("validation_error", 422, "category not found")
    exists = (
        db.query(IssueCategory)
        .filter(
            IssueCategory.issue_id == iss.id,
            IssueCategory.category_id == cat.id,
            IssueCategory.archived_at.is_(None),
        )
        .first()
    )
    if exists is not None:
        return {"data": {"id": _ser_id(cat.id), "name": getattr(cat, "name", ""), "linked": True}}
    link = IssueCategory()
    link.issue_id = iss.id
    link.category_id = cat.id
    _apply_audit_create(link, actor)
    db.add(link)
    db.commit()
    return {"data": {"id": _ser_id(cat.id), "name": getattr(cat, "name", ""), "linked": True}}


@router_issue.delete("/{issue_id}/categories/{category_id}")
def unlink_issue_category(issue_id: str, category_id: str, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """词条与分类解挂（软删除）。"""
    iss = _find_issue(db, issue_id)
    if iss is None or getattr(iss, "archived_at", None) is not None:
        raise ApiError("not_found", 404)
    cat = _find_category(db, category_id)
    if cat is None:
        raise ApiError("not_found", 404)
    link = (
        db.query(IssueCategory)
        .filter(
            IssueCategory.issue_id == iss.id,
            IssueCategory.category_id == cat.id,
            IssueCategory.archived_at.is_(None),
        )
        .first()
    )
    if link is None:
        raise ApiError("not_found", 404)
    from datetime import datetime, timezone
    link.archived_at = datetime.now(timezone.utc)
    db.commit()
    return {"data": {"unlinked": True}}


class IssueUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    summary: Optional[str] = None


@router_issue.patch("/{issue_id}")
def update_issue(
    issue_id: str,
    payload: IssueUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    iss = get_or_404(db, Issue, issue_id, "issue")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    apply_update(db, iss, data, ["title", "summary"], actor.id)
    return {"data": _issue_to_dict(iss)}


@router_issue.post("/{issue_id}/archive")
def archive_issue(issue_id: str, db: Session = Depends(get_db)):
    iss = get_or_404(db, Issue, issue_id, "issue")
    archive_entity(db, iss)
    return {"ok": True}


@router_issue.post("/{issue_id}/restore")
def restore_issue(issue_id: str, db: Session = Depends(get_db)):
    iss = db.get(Issue, parse_uuid(issue_id, "issue_id"))
    if iss is None:
        raise ApiError("not_found", 404, "issue 不存在")
    restore_entity(db, Issue, iss)
    return {"ok": True}
