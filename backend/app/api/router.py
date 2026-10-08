from fastapi import APIRouter

from app.features.identity.router import router as identity_router
from app.features.taxonomy.router import router_cat as taxonomy_categories_router
from app.features.taxonomy.router import router_issue as taxonomy_issues_router
from app.features.bibliography.router import router_person as bib_person_router
from app.features.bibliography.router import router_ref as bib_ref_router
from app.features.discourses.router import router_disc as discourses_router
from app.features.discourses.router import router_anchor as anchors_router
from app.features.relations.router import router_rel as relations_router
from app.features.relations.router import router_kind as relation_kinds_router
from app.features.relations.router import router_dim as dimension_kinds_router
from app.features.relations.router import router_ann as annotations_router

from app.features.graph.router import router_graph as graph_router
from app.features.history.router import router_history as history_router
from app.features.search.router import router as search_router
from app.features.custom_fields.router import router as custom_fields_router

api_router = APIRouter()

api_router.include_router(identity_router, tags=["auth"])
api_router.include_router(taxonomy_categories_router, tags=["categories"])
api_router.include_router(taxonomy_issues_router, tags=["issues"])
api_router.include_router(bib_person_router, tags=["persons"])
api_router.include_router(bib_ref_router, tags=["references"])
api_router.include_router(discourses_router, tags=["discourses"])
api_router.include_router(anchors_router, tags=["anchors"])
api_router.include_router(relations_router, tags=["relations"])
api_router.include_router(relation_kinds_router, tags=["relation-kinds"])
api_router.include_router(dimension_kinds_router, tags=["dimension-kinds"])
api_router.include_router(annotations_router, tags=["annotations"])
api_router.include_router(graph_router, tags=["graph"])
api_router.include_router(history_router, tags=["history"])
api_router.include_router(search_router, tags=["search"])
api_router.include_router(custom_fields_router, tags=["field-definitions"])

# 各feature router将来在此include
