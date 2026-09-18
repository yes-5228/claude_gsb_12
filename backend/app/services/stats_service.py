"""统计看板业务逻辑。

口径约定（巡查与问题保持一致）：

- 区域、公厕等级一律取所属公厕档案 Restroom 的**当前值**，不使用巡查记录自身
  的评分等级（优秀/良好等）；公厕等级仅指一类/二类/三类。
- 巡查、问题统计都通过 ``restroom_id`` 关联 Restroom 后再按区域、等级过滤，
  列表（inspection_service / issue_service 的 build_*_stmt）、分组统计、看板
  复用同一套过滤条件，确保筛选变化后三处数字同步。
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    OPEN_ISSUE_STATUSES,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    RestroomGrade,
    RestroomStatus,
)
from app.models import Inspection, Issue, Restroom
from app.schemas.stats import (
    CategoryStat,
    DashboardStats,
    DimensionStat,
    ListGroupSummary,
    NameValue,
    OverviewStats,
    RestroomRankItem,
    Scope,
    StatsMethodology,
    TrendPoint,
)
from app.services import inspection_service, issue_service

GRADE_ORDER = [grade.value for grade in RestroomGrade]


def _scope_conditions(district: str | None, grade: str | None) -> list:
    """区域 + 公厕等级的统一过滤条件，作用于 Restroom 列。"""
    conditions = []
    if district:
        conditions.append(Restroom.district == district)
    if grade:
        conditions.append(Restroom.grade == grade)
    return conditions


def _count(db: Session, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    if conditions:
        stmt = stmt.where(*conditions)
    return db.scalar(stmt) or 0


def methodology() -> StatsMethodology:
    return StatsMethodology(
        scope_basis="巡查与问题均通过所属公厕档案关联区域与公厕等级，按相同筛选条件统计。",
        region_basis="区域取公厕档案中的「所属区域」当前值，而非记录历史快照。",
        grade_basis="公厕等级取公厕档案中的一类/二类/三类；巡查列表中的优秀/良好等是评分等级，不作为本统计口径。",
        consistency_rule="列表、区域/等级分组与看板指标共用同一套区域、等级过滤条件，任一筛选变化后数字同步更新。",
        open_statuses=list(OPEN_ISSUE_STATUSES),
        overdue_rule="整改期限早于当前时间且状态仍为待整改/整改中/待验收的问题计为超期。",
        rectification_rule="整改闭环率 = （已完成 + 已关闭）/ 累计上报问题 × 100%。",
        score_rule="巡查均分按百分制得分在同一筛选范围内取算术平均。",
        dimensions=["区域", "公厕等级"],
        grade_options=list(GRADE_ORDER),
    )


def overview(db: Session, district: str | None = None, grade: str | None = None) -> OverviewStats:
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    week_start = today_start - timedelta(days=6)
    month_start = datetime.combine(date(now.year, now.month, 1), time.min)
    scope = _scope_conditions(district, grade)

    def issue_count(*extra) -> int:
        return db.scalar(
            select(func.count(Issue.id))
            .select_from(Issue)
            .join(Restroom, Restroom.id == Issue.restroom_id)
            .where(*scope, *extra)
        ) or 0

    def inspection_count(*extra) -> int:
        return db.scalar(
            select(func.count(Inspection.id))
            .select_from(Inspection)
            .join(Restroom, Restroom.id == Inspection.restroom_id)
            .where(*scope, *extra)
        ) or 0

    issue_total = issue_count()
    issue_open = issue_count(Issue.status.in_(OPEN_ISSUE_STATUSES))
    issue_overdue = issue_count(
        Issue.deadline.is_not(None),
        Issue.deadline < now,
        Issue.status.in_(OPEN_ISSUE_STATUSES),
    )
    done_count = issue_count(Issue.status == IssueStatus.DONE.value)
    closed_count = issue_count(Issue.status == IssueStatus.CLOSED.value)
    finished = done_count + closed_count

    inspection_total = inspection_count()
    inspection_today = inspection_count(Inspection.inspect_time >= today_start)
    inspection_week = inspection_count(Inspection.inspect_time >= week_start)
    avg_score_week = (
        db.scalar(
            select(func.avg(Inspection.score))
            .join(Restroom, Restroom.id == Inspection.restroom_id)
            .where(Inspection.inspect_time >= week_start, *scope)
        )
        or 0.0
    )

    return OverviewStats(
        restroom_total=_count(db, Restroom, *scope),
        restroom_open=_count(db, Restroom, Restroom.status == RestroomStatus.NORMAL.value, *scope),
        restroom_maintenance=_count(
            db, Restroom, Restroom.status == RestroomStatus.MAINTENANCE.value, *scope
        ),
        inspection_total=inspection_total,
        inspection_today=inspection_today,
        inspection_week=inspection_week,
        avg_score_week=round(float(avg_score_week), 1),
        issue_total=issue_total,
        issue_open=issue_open,
        issue_overdue=issue_overdue,
        issue_done_this_month=issue_count(
            Issue.status == IssueStatus.DONE.value, Issue.updated_at >= month_start
        ),
        rectification_rate=round(finished / issue_total * 100, 1) if issue_total else 0.0,
    )


def _issue_dimension_counts(db: Session, group_col, scope: list, *extra) -> dict[str, int]:
    rows = db.execute(
        select(group_col, func.count(Issue.id))
        .join(Issue, Issue.restroom_id == Restroom.id)
        .where(*scope, *extra)
        .group_by(group_col)
    ).all()
    return {key: int(count) for key, count in rows}


def dimension_stats(
    db: Session, group_col, district: str | None = None, grade: str | None = None
) -> list[DimensionStat]:
    """按指定维度（Restroom.district 或 Restroom.grade）聚合统一口径指标。"""
    scope = _scope_conditions(district, grade)

    restroom_rows = db.execute(
        select(group_col, func.count(Restroom.id)).where(*scope).group_by(group_col)
    ).all()
    restroom_counts = {key: int(count) for key, count in restroom_rows}

    inspection_rows = db.execute(
        select(group_col, func.count(Inspection.id), func.avg(Inspection.score))
        .join(Inspection, Inspection.restroom_id == Restroom.id)
        .where(*scope)
        .group_by(group_col)
    ).all()
    inspection_counts: dict[str, int] = {}
    avg_scores: dict[str, float] = {}
    for key, count, avg in inspection_rows:
        inspection_counts[key] = int(count)
        avg_scores[key] = float(avg or 0)

    issue_totals = _issue_dimension_counts(db, group_col, scope)
    issue_opens = _issue_dimension_counts(
        db, group_col, scope, Issue.status.in_(OPEN_ISSUE_STATUSES)
    )
    issue_overdues = _issue_dimension_counts(
        db,
        group_col,
        scope,
        Issue.deadline.is_not(None),
        Issue.deadline < datetime.now(),
        Issue.status.in_(OPEN_ISSUE_STATUSES),
    )

    items = [
        DimensionStat(
            name=name,
            restroom_count=restroom_counts.get(name, 0),
            inspection_count=inspection_counts.get(name, 0),
            issue_total=issue_totals.get(name, 0),
            issue_open=issue_opens.get(name, 0),
            issue_overdue=issue_overdues.get(name, 0),
            avg_score=round(avg_scores.get(name, 0.0), 1),
        )
        for name in restroom_counts
    ]
    items.sort(key=lambda item: (-item.issue_open, -item.restroom_count, item.name))
    return items


def issue_by_status(db: Session, district: str | None = None, grade: str | None = None) -> list[NameValue]:
    scope = _scope_conditions(district, grade)
    rows = dict(
        db.execute(
            select(Issue.status, func.count())
            .join(Restroom, Restroom.id == Issue.restroom_id)
            .where(*scope)
            .group_by(Issue.status)
        ).all()
    )
    ordered = list(IssueStatus)
    return [NameValue(name=status.value, value=float(rows.get(status.value, 0))) for status in ordered]


def issue_by_severity(db: Session, district: str | None = None, grade: str | None = None) -> list[NameValue]:
    scope = _scope_conditions(district, grade)
    rows = dict(
        db.execute(
            select(Issue.severity, func.count())
            .join(Restroom, Restroom.id == Issue.restroom_id)
            .where(*scope)
            .group_by(Issue.severity)
        ).all()
    )
    return [
        NameValue(name=severity.value, value=float(rows.get(severity.value, 0)))
        for severity in IssueSeverity
    ]


def issue_by_category(db: Session, district: str | None = None, grade: str | None = None) -> list[CategoryStat]:
    scope = _scope_conditions(district, grade)
    rows = db.execute(
        select(Issue.category, func.count())
        .join(Restroom, Restroom.id == Issue.restroom_id)
        .where(*scope)
        .group_by(Issue.category)
    ).all()
    totals = {category: int(count) for category, count in rows}
    open_rows = db.execute(
        select(Issue.category, func.count())
        .join(Restroom, Restroom.id == Issue.restroom_id)
        .where(*scope, Issue.status.in_(OPEN_ISSUE_STATUSES))
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


def inspection_trend(
    db: Session, days: int = 14, district: str | None = None, grade: str | None = None
) -> list[TrendPoint]:
    days = max(3, min(days, 60))
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, time.min)
    scope = _scope_conditions(district, grade)

    inspection_rows = db.execute(
        select(Inspection.inspect_time, Inspection.score)
        .join(Restroom, Restroom.id == Inspection.restroom_id)
        .where(Inspection.inspect_time >= start_dt, *scope)
    ).all()
    issue_rows = db.execute(
        select(Issue.report_time)
        .join(Restroom, Restroom.id == Issue.restroom_id)
        .where(Issue.report_time >= start_dt, *scope)
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


def restroom_ranking(
    db: Session, limit: int = 8, district: str | None = None, grade: str | None = None
) -> list[RestroomRankItem]:
    scope = _scope_conditions(district, grade)
    inspections = db.execute(
        select(
            Inspection.restroom_id,
            func.count(Inspection.id),
            func.avg(Inspection.score),
        )
        .join(Restroom, Restroom.id == Inspection.restroom_id)
        .where(*scope)
        .group_by(Inspection.restroom_id)
    ).all()
    stats = {
        rid: {"count": int(count), "avg": round(float(avg or 0), 1)} for rid, count, avg in inspections
    }
    open_rows = db.execute(
        select(Issue.restroom_id, func.count())
        .join(Restroom, Restroom.id == Issue.restroom_id)
        .where(*scope, Issue.status.in_(OPEN_ISSUE_STATUSES))
        .group_by(Issue.restroom_id)
    ).all()
    opens = {rid: int(count) for rid, count in open_rows}

    ranking: list[RestroomRankItem] = []
    for restroom in db.scalars(select(Restroom).where(*scope)):
        stat = stats.get(restroom.id, {"count": 0, "avg": 0.0})
        ranking.append(
            RestroomRankItem(
                restroom_id=restroom.id,
                code=restroom.code,
                name=restroom.name,
                district=restroom.district,
                grade=restroom.grade,
                inspection_count=stat["count"],
                avg_score=stat["avg"],
                open_issues=opens.get(restroom.id, 0),
            )
        )
    ranking.sort(key=lambda item: (-item.open_issues, item.avg_score, -item.inspection_count))
    return ranking[:limit]


def _fill_group(rows: dict[str, int], names: list[str]) -> list[NameValue]:
    return [NameValue(name=name, value=float(rows.get(name, 0))) for name in names]


def inspection_summary(db: Session, filters: dict) -> ListGroupSummary:
    """巡查列表随筛选联动的区域/等级分组汇总（与列表同一查询口径）。"""
    base = inspection_service.build_inspection_stmt(**filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    def grouped(column):
        stmt = (
            select(column, func.count(Inspection.id))
            .select_from(Inspection)
            .join(Restroom, Restroom.id == Inspection.restroom_id)
            .group_by(column)
        )
        if base.whereclause is not None:
            stmt = stmt.where(base.whereclause)
        return dict(db.execute(stmt).all())

    district_rows = grouped(Restroom.district)
    grade_rows = grouped(Restroom.grade)
    districts = list(db.scalars(select(Restroom.district).distinct().order_by(Restroom.district)))
    return ListGroupSummary(
        total=total,
        by_district=_fill_group(district_rows, districts),
        by_grade=_fill_group(grade_rows, GRADE_ORDER),
    )


def issue_summary(db: Session, filters: dict) -> ListGroupSummary:
    """问题列表随筛选联动的区域/等级分组汇总（与列表同一查询口径）。"""
    base = issue_service.build_issue_stmt(**filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    def grouped(column):
        stmt = (
            select(column, func.count(Issue.id))
            .select_from(Issue)
            .join(Restroom, Restroom.id == Issue.restroom_id)
            .group_by(column)
        )
        if base.whereclause is not None:
            stmt = stmt.where(base.whereclause)
        return dict(db.execute(stmt).all())

    district_rows = grouped(Restroom.district)
    grade_rows = grouped(Restroom.grade)
    districts = list(db.scalars(select(Restroom.district).distinct().order_by(Restroom.district)))
    return ListGroupSummary(
        total=total,
        by_district=_fill_group(district_rows, districts),
        by_grade=_fill_group(grade_rows, GRADE_ORDER),
    )


def dashboard(db: Session, trend_days: int = 14, district: str | None = None, grade: str | None = None) -> DashboardStats:
    recent_issues, _ = issue_service.list_issues(
        db, page=1, page_size=5, sort_by="report_time", district=district, grade=grade
    )
    recent_inspections, _ = inspection_service.list_inspections(
        db, page=1, page_size=5, sort_by="inspect_time", district=district, grade=grade
    )
    by_district = dimension_stats(db, Restroom.district, district, grade)
    by_grade_ordered = {
        item.name: item for item in dimension_stats(db, Restroom.grade, district, grade)
    }
    by_grade = [by_grade_ordered[name] for name in GRADE_ORDER if name in by_grade_ordered]
    return DashboardStats(
        scope=Scope(district=district or None, grade=grade or None),
        overview=overview(db, district, grade),
        issue_by_status=issue_by_status(db, district, grade),
        issue_by_category=issue_by_category(db, district, grade),
        issue_by_severity=issue_by_severity(db, district, grade),
        inspection_trend=inspection_trend(db, days=trend_days, district=district, grade=grade),
        by_district=by_district,
        by_grade=by_grade,
        districts=by_district,
        top_restrooms=restroom_ranking(db, district=district, grade=grade),
        recent_issues=[issue_service.to_out(issue) for issue in recent_issues],
        recent_inspections=[inspection_service.to_out(item) for item in recent_inspections],
        methodology=methodology(),
    )
