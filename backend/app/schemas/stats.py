"""统计看板数据结构。"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.inspection import InspectionOut
from app.schemas.issue import IssueOut


class NameValue(BaseModel):
    name: str
    value: float


class Scope(BaseModel):
    """当前统计口径对应的筛选条件（空值表示不限）。"""

    district: str | None = None
    grade: str | None = None


class OverviewStats(BaseModel):
    restroom_total: int = 0
    restroom_open: int = 0
    restroom_maintenance: int = 0
    inspection_total: int = 0
    inspection_today: int = 0
    inspection_week: int = 0
    avg_score_week: float = 0.0
    issue_total: int = 0
    issue_open: int = 0
    issue_overdue: int = 0
    issue_done_this_month: int = 0
    rectification_rate: float = Field(default=0.0, description="整改完成率（百分比）")


class TrendPoint(BaseModel):
    date: str
    inspections: int = 0
    issues: int = 0
    avg_score: float = 0.0


class CategoryStat(BaseModel):
    category: str
    total: int = 0
    open: int = 0
    closed: int = 0


class RestroomRankItem(BaseModel):
    restroom_id: int
    code: str
    name: str
    district: str
    grade: str = ""
    inspection_count: int = 0
    avg_score: float = 0.0
    open_issues: int = 0


class DimensionStat(BaseModel):
    """按区域或公厕等级分组的统一切片，两类记录共用同一口径。"""

    name: str
    restroom_count: int = 0
    inspection_count: int = 0
    issue_total: int = 0
    issue_open: int = 0
    issue_overdue: int = 0
    avg_score: float = 0.0


class ListGroupSummary(BaseModel):
    """列表页随筛选联动的分组汇总，区域与等级两个维度同一口径。"""

    total: int = 0
    by_district: list[NameValue] = Field(default_factory=list)
    by_grade: list[NameValue] = Field(default_factory=list)


class StatsMethodology(BaseModel):
    """页面上可查看的统计口径说明。"""

    scope_basis: str
    region_basis: str
    grade_basis: str
    consistency_rule: str
    open_statuses: list[str]
    overdue_rule: str
    rectification_rule: str
    score_rule: str
    dimensions: list[str]
    grade_options: list[str]


class DashboardStats(BaseModel):
    """看板一次拉取所需的全部指标。"""

    scope: Scope = Field(default_factory=Scope)
    overview: OverviewStats
    issue_by_status: list[NameValue] = Field(default_factory=list)
    issue_by_category: list[CategoryStat] = Field(default_factory=list)
    issue_by_severity: list[NameValue] = Field(default_factory=list)
    inspection_trend: list[TrendPoint] = Field(default_factory=list)
    by_district: list[DimensionStat] = Field(default_factory=list)
    by_grade: list[DimensionStat] = Field(default_factory=list)
    districts: list[DimensionStat] = Field(default_factory=list, description="兼容旧字段，等同 by_district")
    top_restrooms: list[RestroomRankItem] = Field(default_factory=list)
    recent_issues: list[IssueOut] = Field(default_factory=list)
    recent_inspections: list[InspectionOut] = Field(default_factory=list)
    methodology: StatsMethodology


Dimension = Literal["district", "grade"]
