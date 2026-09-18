"""统计看板接口。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import OPEN_ISSUE_STATUSES
from app.core.database import get_db
from app.schemas.stats import DashboardStats, ListGroupSummary, OverviewStats, StatsMethodology
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["统计看板"])

DistrictDep = Annotated[str | None, Query(description="按所属区域过滤，取公厕档案当前区域")]
GradeDep = Annotated[
    str | None, Query(description="按公厕等级过滤（一类/二类/三类，非巡查评分等级）")
]


@router.get("/methodology", response_model=StatsMethodology, summary="统计口径说明")
def get_methodology() -> StatsMethodology:
    return stats_service.methodology()


@router.get("/overview", response_model=OverviewStats, summary="核心指标")
def get_overview(db: Annotated[Session, Depends(get_db)], district: DistrictDep = None, grade: GradeDep = None) -> OverviewStats:
    return stats_service.overview(db, district=district, grade=grade)


@router.get("/dashboard", response_model=DashboardStats, summary="看板聚合数据")
def get_dashboard(
    db: Annotated[Session, Depends(get_db)],
    trend_days: Annotated[int, Query(ge=3, le=60, description="趋势天数")] = 14,
    district: DistrictDep = None,
    grade: GradeDep = None,
) -> DashboardStats:
    return stats_service.dashboard(db, trend_days=trend_days, district=district, grade=grade)


@router.get(
    "/inspections/summary",
    response_model=ListGroupSummary,
    summary="巡查列表分组汇总（区域/公厕等级）",
)
def inspection_summary(
    db: Annotated[Session, Depends(get_db)],
    restroom_id: Annotated[int | None, Query(description="按公厕过滤")] = None,
    district: DistrictDep = None,
    grade: GradeDep = None,
    inspector: Annotated[str | None, Query(description="巡查人")] = None,
    shift: Annotated[str | None, Query(description="班次")] = None,
    result: Annotated[str | None, Query(description="巡查结论")] = None,
    keyword: Annotated[str | None, Query(description="公厕名称/备注模糊搜索")] = None,
    date_from: Annotated[date | None, Query(description="开始日期")] = None,
    date_to: Annotated[date | None, Query(description="结束日期")] = None,
) -> ListGroupSummary:
    filters = {
        "restroom_id": restroom_id,
        "district": district,
        "grade": grade,
        "inspector": inspector,
        "shift": shift,
        "result": result,
        "keyword": keyword,
        "date_from": date_from,
        "date_to": date_to,
    }
    return stats_service.inspection_summary(db, filters)


@router.get(
    "/issues/summary",
    response_model=ListGroupSummary,
    summary="问题列表分组汇总（区域/公厕等级）",
)
def issue_summary(
    db: Annotated[Session, Depends(get_db)],
    restroom_id: Annotated[int | None, Query(description="按公厕过滤")] = None,
    inspection_id: Annotated[int | None, Query(description="按巡查记录过滤")] = None,
    district: DistrictDep = None,
    grade: GradeDep = None,
    status: Annotated[str | None, Query(description="整改状态")] = None,
    category: Annotated[str | None, Query(description="问题分类")] = None,
    severity: Annotated[str | None, Query(description="严重程度")] = None,
    keyword: Annotated[str | None, Query(description="标题/描述/编号模糊搜索")] = None,
    overdue: Annotated[bool | None, Query(description="是否超期")] = None,
    open_only: Annotated[bool, Query(description="仅看未闭环问题")] = False,
    date_from: Annotated[date | None, Query(description="上报开始日期")] = None,
    date_to: Annotated[date | None, Query(description="上报结束日期")] = None,
) -> ListGroupSummary:
    filters = {
        "restroom_id": restroom_id,
        "inspection_id": inspection_id,
        "district": district,
        "grade": grade,
        "status": status,
        "statuses": list(OPEN_ISSUE_STATUSES) if open_only else None,
        "category": category,
        "severity": severity,
        "keyword": keyword,
        "overdue": overdue,
        "date_from": date_from,
        "date_to": date_to,
    }
    return stats_service.issue_summary(db, filters)
