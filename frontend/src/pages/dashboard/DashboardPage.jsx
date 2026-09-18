import { useState } from 'react';

import { restroomApi } from '../../api/restrooms.js';
import { statsApi } from '../../api/stats.js';
import BarList from '../../components/BarList.jsx';
import Field from '../../components/Field.jsx';
import MethodologyButton from '../../components/MethodologyButton.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import ScopeFields from '../../components/ScopeFields.jsx';
import StatCard from '../../components/StatCard.jsx';
import TrendChart from '../../components/TrendChart.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import {
  CategoryPanel,
  DistrictPanel,
  GradePanel,
  IssueStatusPanel,
  RankingPanel,
  RecentInspectionsPanel,
  RecentIssuesPanel,
} from './DashboardPanels.jsx';

const RANGE_OPTIONS = [7, 14, 30];

export default function DashboardPage() {
  const { dictionaries } = useDictionaries();
  const [trendDays, setTrendDays] = useState(14);
  const [district, setDistrict] = useState('');
  const [grade, setGrade] = useState('');
  const { data, loading, error } = useAsync(
    () => statsApi.dashboard({ trendDays, district, grade }),
    [trendDays, district, grade],
  );
  const { data: districts } = useAsync(() => restroomApi.districts(), []);

  const overview = data?.overview;
  const scopeText = `当前口径：${data?.scope?.district || '全部区域'} · ${data?.scope?.grade || '全部等级'}`;

  return (
    <>
      <PageHeader
        title="总览看板"
        description="公厕保洁巡查与问题整改的整体运行情况，区域与公厕等级统计口径一致"
        actions={
          <div className="field" style={{ minWidth: 130 }}>
            <label>统计区间</label>
            <select value={trendDays} onChange={(event) => setTrendDays(Number(event.target.value))}>
              {RANGE_OPTIONS.map((days) => (
                <option key={days} value={days}>
                  近 {days} 天
                </option>
              ))}
            </select>
          </div>
        }
      />
      <div className="content">
        <section className="card">
          <div className="filter-bar">
            <ScopeFields
              districts={districts || []}
              grades={dictionaries?.restroom_grade || []}
              value={{ district, grade }}
              onChange={(key, value) => (key === 'district' ? setDistrict(value) : setGrade(value))}
            />
            <button
              type="button"
              className="btn"
              onClick={() => {
                setDistrict('');
                setGrade('');
              }}
            >
              重置
            </button>
            <MethodologyButton />
          </div>
          <div className="caliber-banner">
            <span className="tag tag-info">{scopeText}</span>
            <span className="hint">区域、等级取公厕档案当前值；筛选变化后下方指标同步更新</span>
          </div>
        </section>

        {error ? <div className="alert alert-error">{error.message}</div> : null}
        {loading && !data ? <div className="loading-block">看板数据加载中…</div> : null}

        {overview ? (
          <>
            <div className="stat-grid">
              <StatCard
                label="在册公厕"
                value={overview.restroom_total}
                unit="座"
                foot={`正常开放 ${overview.restroom_open} 座 · 维修 ${overview.restroom_maintenance} 座`}
              />
              <StatCard
                label="巡查记录总数"
                value={overview.inspection_total}
                unit="条"
                tone="info"
                foot={`今日 ${overview.inspection_today} 条 · 近 7 日 ${overview.inspection_week} 条`}
              />
              <StatCard
                label="近 7 日均分"
                value={overview.avg_score_week.toFixed(1)}
                unit="分"
                tone={overview.avg_score_week >= 85 ? 'primary' : 'warning'}
                foot="按百分制折算"
              />
              <StatCard
                label="未闭环问题"
                value={overview.issue_open}
                unit="条"
                tone={overview.issue_open > 0 ? 'danger' : 'primary'}
                foot={`累计上报 ${overview.issue_total} 条`}
              />
              <StatCard
                label="超期未整改"
                value={overview.issue_overdue}
                unit="条"
                tone={overview.issue_overdue > 0 ? 'danger' : 'primary'}
                foot="超过整改期限仍未闭环"
              />
              <StatCard
                label="整改闭环率"
                value={overview.rectification_rate.toFixed(1)}
                unit="%"
                tone="info"
                foot={`本月完成 ${overview.issue_done_this_month} 条`}
              />
            </div>

            <div className="grid-2">
              <section className="card">
                <div className="card-title">
                  <h3>巡查与问题趋势</h3>
                  <span className="hint">近 {trendDays} 天</span>
                </div>
                <TrendChart points={data.inspection_trend} />
              </section>
              <IssueStatusPanel items={data.issue_by_status} />
            </div>

            <div className="grid-2">
              <CategoryPanel items={data.issue_by_category} />
              <section className="card">
                <div className="card-title">
                  <h3>问题严重程度分布</h3>
                </div>
                <BarList
                  items={data.issue_by_severity.map((item) => ({
                    name: item.name,
                    value: item.value,
                    color: item.name === '紧急' ? '#dc2626' : item.name === '严重' ? '#d97706' : '#64748b',
                  }))}
                />
              </section>
            </div>

            <div className="grid-2">
              <DistrictPanel items={data.by_district} />
              <GradePanel items={data.by_grade} />
            </div>

            <RankingPanel items={data.top_restrooms} />

            <div className="grid-2">
              <RecentIssuesPanel items={data.recent_issues} />
              <RecentInspectionsPanel items={data.recent_inspections} />
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}
