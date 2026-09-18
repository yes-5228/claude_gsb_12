import BarList from './BarList.jsx';

/**
 * 列表页分组汇总：在当前筛选条件下，按区域、公厕等级分别统计数量。
 * summary 由 /stats/{inspections|issues}/summary 返回，与列表共用同一查询口径，
 * 因此筛选变化后这里的分组数字与列表总数保持一致。
 */
export default function GroupSummaryCard({ title = '分组统计', loading, summary }) {
  return (
    <section className="card">
      <div className="card-title">
        <h3>{title}</h3>
        <span className="hint">
          共 <strong>{summary?.total ?? 0}</strong> 条 · 按区域与公厕等级同一口径
        </span>
      </div>
      {loading && !summary ? (
        <div className="loading-block">统计中…</div>
      ) : (
        <div className="grid-2">
          <div>
            <div className="sub-title">按区域</div>
            <BarList
              items={(summary?.by_district || []).map((item) => ({ name: item.name, value: item.value }))}
              emptyText="暂无区域数据"
            />
          </div>
          <div>
            <div className="sub-title">按公厕等级</div>
            <BarList
              items={(summary?.by_grade || []).map((item) => ({
                name: item.name,
                value: item.value,
                color: item.name === '一类' ? '#0f766e' : item.name === '二类' ? '#2563eb' : '#64748b',
              }))}
              tone="custom"
              emptyText="暂无等级数据"
            />
          </div>
        </div>
      )}
    </section>
  );
}
