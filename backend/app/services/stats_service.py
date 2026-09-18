"""统计看板业务逻辑。

看板内的所有指标（核心指标卡、分组分布、趋势、区域运行、公厕排行、最新记录）
共用同一套统计口径：按「区域 + 公厕等级」圈定公厕范围，巡查与问题均通过
所属公厕归入该范围，保证页面各区块数字口径一致、随筛选同步变化。
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    OPEN_ISSUE_STATUSES,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    RestroomStatus,
)
from app.models import Inspection, Issue, Restroom
from app.schemas.stats import (
    CategoryStat,
    DashboardStats,
    DistrictStat,
    NameValue,
    OverviewStats,
    RestroomRankItem,
    StatsScope,
    TrendPoint,
)
from app.services import inspection_service, issue_service


@dataclass(frozen=True)
class Scope:
    """统计口径：按公厕所属区域与等级过滤。"""

    district: str | None = None
    grade: str | None = None

    @property
    def active(self) -> bool:
        return bool(self.district or self.grade)


def _apply_scope(stmt, entity, scope: Scope):
    """把区域/等级条件挂到查询上；巡查、问题需关联公厕表。"""
    if not scope.active:
        return stmt
    if entity is not Restroom:
        stmt = stmt.join(Restroom, Restroom.id == entity.restroom_id)
    if scope.district:
        stmt = stmt.where(Restroom.district == scope.district)
    if scope.grade:
        stmt = stmt.where(Restroom.grade == scope.grade)
    return stmt


def _restroom_conditions(scope: Scope) -> list:
    conditions = []
    if scope.district:
        conditions.append(Restroom.district == scope.district)
    if scope.grade:
        conditions.append(Restroom.grade == scope.grade)
    return conditions


def build_scope(district: str | None, grade: str | None) -> StatsScope:
    """生成口径对象与页面展示用的口径说明。"""
    scope = Scope(district=district or None, grade=grade or None)
    parts = []
    if scope.district:
        parts.append(f"区域「{scope.district}」")
    if scope.grade:
        parts.append(f"公厕等级「{scope.grade}」")
    scope_text = "、".join(parts) if parts else "全市全部公厕"
    description = (
        f"统计范围：{scope_text}（巡查与问题均按所属公厕归入）。"
        "未闭环问题指状态为待整改、整改中、待验收；"
        "超期指当前时间已超过整改期限且仍未闭环；巡查均分按百分制计算。"
    )
    return StatsScope(district=scope.district, grade=scope.grade, description=description)


def _count(db: Session, model, scope: Scope, *conditions) -> int:
    stmt = _apply_scope(select(func.count()).select_from(model), model, scope)
    if conditions:
        stmt = stmt.where(*conditions)
    return db.scalar(stmt) or 0


def overview(db: Session, scope: Scope = Scope()) -> OverviewStats:
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    week_start = today_start - timedelta(days=6)
    month_start = datetime.combine(date(now.year, now.month, 1), time.min)

    issue_total = _count(db, Issue, scope)
    issue_open = _count(db, Issue, scope, Issue.status.in_(OPEN_ISSUE_STATUSES))
    issue_overdue = _count(
        db,
        Issue,
        scope,
        Issue.deadline.is_not(None),
        Issue.deadline < now,
        Issue.status.in_(OPEN_ISSUE_STATUSES),
    )
    done_count = _count(db, Issue, scope, Issue.status == IssueStatus.DONE.value)
    closed_count = _count(db, Issue, scope, Issue.status == IssueStatus.CLOSED.value)
    finished = done_count + closed_count

    avg_stmt = _apply_scope(select(func.avg(Inspection.score)), Inspection, scope).where(
        Inspection.inspect_time >= week_start
    )

    return OverviewStats(
        restroom_total=_count(db, Restroom, scope),
        restroom_open=_count(
            db, Restroom, scope, Restroom.status == RestroomStatus.NORMAL.value
        ),
        restroom_maintenance=_count(
            db, Restroom, scope, Restroom.status == RestroomStatus.MAINTENANCE.value
        ),
        inspection_total=_count(db, Inspection, scope),
        inspection_today=_count(db, Inspection, scope, Inspection.inspect_time >= today_start),
        inspection_week=_count(db, Inspection, scope, Inspection.inspect_time >= week_start),
        avg_score_week=round(float(db.scalar(avg_stmt) or 0.0), 1),
        issue_total=issue_total,
        issue_open=issue_open,
        issue_overdue=issue_overdue,
        issue_done_this_month=_count(
            db,
            Issue,
            scope,
            Issue.status == IssueStatus.DONE.value,
            Issue.updated_at >= month_start,
        ),
        rectification_rate=round(finished / issue_total * 100, 1) if issue_total else 0.0,
    )


def issue_by_status(db: Session, scope: Scope = Scope()) -> list[NameValue]:
    stmt = _apply_scope(select(Issue.status, func.count()), Issue, scope).group_by(Issue.status)
    rows = dict(db.execute(stmt).all())
    ordered = list(IssueStatus)
    return [NameValue(name=status.value, value=float(rows.get(status.value, 0))) for status in ordered]


def issue_by_severity(db: Session, scope: Scope = Scope()) -> list[NameValue]:
    stmt = _apply_scope(select(Issue.severity, func.count()), Issue, scope).group_by(
        Issue.severity
    )
    rows = dict(db.execute(stmt).all())
    return [
        NameValue(name=severity.value, value=float(rows.get(severity.value, 0)))
        for severity in IssueSeverity
    ]


def issue_by_category(db: Session, scope: Scope = Scope()) -> list[CategoryStat]:
    rows = db.execute(
        _apply_scope(select(Issue.category, func.count()), Issue, scope).group_by(Issue.category)
    ).all()
    totals = {category: int(count) for category, count in rows}
    open_rows = db.execute(
        _apply_scope(select(Issue.category, func.count()), Issue, scope)
        .where(Issue.status.in_(OPEN_ISSUE_STATUSES))
        .group_by(Issue.category)
    ).all()
    opens = {category: int(count) for category, count in open_rows}
    result: list[CategoryStat] = []
    for category in IssueCategory:
        total = totals.get(category.value, 0)
        open_count = opens.get(category.value, 0)
        result.append(
            CategoryStat(
                category=category.value, total=total, open=open_count, closed=total - open_count
            )
        )
    return result


def inspection_trend(db: Session, scope: Scope = Scope(), days: int = 14) -> list[TrendPoint]:
    days = max(3, min(days, 60))
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, time.min)

    inspection_rows = db.execute(
        _apply_scope(select(Inspection.inspect_time, Inspection.score), Inspection, scope).where(
            Inspection.inspect_time >= start_dt
        )
    ).all()
    issue_rows = db.execute(
        _apply_scope(select(Issue.report_time), Issue, scope).where(Issue.report_time >= start_dt)
    ).all()

    buckets: dict[str, dict[str, float]] = {}
    for offset in range(days):
        key = (start + timedelta(days=offset)).isoformat()
        buckets[key] = {"inspections": 0, "issues": 0, "score_sum": 0.0}
    for inspect_time, score in inspection_rows:
        key = inspect_time.date().isoformat()
        if key in buckets:
            buckets[key]["inspections"] += 1
            buckets[key]["score_sum"] += float(score or 0)
    for (report_time,) in issue_rows:
        key = report_time.date().isoformat()
        if key in buckets:
            buckets[key]["issues"] += 1

    points: list[TrendPoint] = []
    for key, bucket in buckets.items():
        count = int(bucket["inspections"])
        points.append(
            TrendPoint(
                date=key,
                inspections=count,
                issues=int(bucket["issues"]),
                avg_score=round(bucket["score_sum"] / count, 1) if count else 0.0,
            )
        )
    return points


def district_stats(db: Session, scope: Scope = Scope()) -> list[DistrictStat]:
    restroom_rows = db.execute(
        select(Restroom.district, func.count())
        .where(*_restroom_conditions(scope))
        .group_by(Restroom.district)
    ).all()
    counts = {district: int(count) for district, count in restroom_rows}
    open_stmt = (
        select(Restroom.district, func.count(Issue.id))
        .join(Issue, Issue.restroom_id == Restroom.id)
        .where(Issue.status.in_(OPEN_ISSUE_STATUSES), *_restroom_conditions(scope))
        .group_by(Restroom.district)
    )
    opens = {district: int(count) for district, count in db.execute(open_stmt).all()}
    score_stmt = (
        select(Restroom.district, func.avg(Inspection.score))
        .join(Inspection, Inspection.restroom_id == Restroom.id)
        .where(*_restroom_conditions(scope))
        .group_by(Restroom.district)
    )
    scores = {district: float(avg or 0) for district, avg in db.execute(score_stmt).all()}

    return sorted(
        [
            DistrictStat(
                district=district,
                restroom_count=count,
                issue_open=opens.get(district, 0),
                avg_score=round(scores.get(district, 0.0), 1),
            )
            for district, count in counts.items()
        ],
        key=lambda item: (item.issue_open, -item.avg_score),
        reverse=True,
    )


def restroom_ranking(db: Session, scope: Scope = Scope(), limit: int = 8) -> list[RestroomRankItem]:
    inspections = db.execute(
        _apply_scope(
            select(
                Inspection.restroom_id,
                func.count(Inspection.id),
                func.avg(Inspection.score),
            ),
            Inspection,
            scope,
        ).group_by(Inspection.restroom_id)
    ).all()
    stats = {
        rid: {"count": int(count), "avg": round(float(avg or 0), 1)} for rid, count, avg in inspections
    }
    open_rows = db.execute(
        _apply_scope(select(Issue.restroom_id, func.count()), Issue, scope)
        .where(Issue.status.in_(OPEN_ISSUE_STATUSES))
        .group_by(Issue.restroom_id)
    ).all()
    opens = {rid: int(count) for rid, count in open_rows}

    ranking: list[RestroomRankItem] = []
    restrooms = db.scalars(select(Restroom).where(*_restroom_conditions(scope)))
    for restroom in restrooms:
        stat = stats.get(restroom.id, {"count": 0, "avg": 0.0})
        ranking.append(
            RestroomRankItem(
                restroom_id=restroom.id,
                code=restroom.code,
                name=restroom.name,
                district=restroom.district,
                inspection_count=stat["count"],
                avg_score=stat["avg"],
                open_issues=opens.get(restroom.id, 0),
            )
        )
    ranking.sort(key=lambda item: (-item.open_issues, item.avg_score, -item.inspection_count))
    return ranking[:limit]


def dashboard(db: Session, scope: Scope, trend_days: int = 14) -> DashboardStats:
    recent_issues, _ = issue_service.list_issues(
        db,
        district=scope.district,
        grade=scope.grade,
        page=1,
        page_size=5,
        sort_by="report_time",
    )
    recent_inspections, _ = inspection_service.list_inspections(
        db,
        district=scope.district,
        grade=scope.grade,
        page=1,
        page_size=5,
        sort_by="inspect_time",
    )
    return DashboardStats(
        scope=build_scope(scope.district, scope.grade),
        overview=overview(db, scope),
        issue_by_status=issue_by_status(db, scope),
        issue_by_category=issue_by_category(db, scope),
        issue_by_severity=issue_by_severity(db, scope),
        inspection_trend=inspection_trend(db, scope, days=trend_days),
        districts=district_stats(db, scope),
        top_restrooms=restroom_ranking(db, scope),
        recent_issues=[issue_service.to_out(issue) for issue in recent_issues],
        recent_inspections=[inspection_service.to_out(item) for item in recent_inspections],
    )
