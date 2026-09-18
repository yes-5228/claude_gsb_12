import { useState } from 'react';

import Modal from './Modal.jsx';
import { useMethodology } from '../hooks/useMethodology.js';

function Row({ label, children }) {
  return (
    <div className="caliber-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** “统计口径”按钮 + 弹窗，巡查列表、问题列表与看板共用。 */
export default function MethodologyButton({ size = '', label = '统计口径' }) {
  const [open, setOpen] = useState(false);
  const { methodology } = useMethodology();

  return (
    <>
      <button
        type="button"
        className={`btn ${size}`.trim()}
        onClick={() => setOpen(true)}
        title="查看区域与公厕等级的统计口径说明"
      >
        ⓘ {label}
      </button>
      {open ? (
        <Modal title="统计口径说明" onClose={() => setOpen(false)} width={640}>
          {methodology ? (
            <dl className="caliber-list">
              <Row label="统计维度">{methodology.dimensions.join('、')}</Row>
              <Row label="统一口径">{methodology.scope_basis}</Row>
              <Row label="区域取数">{methodology.region_basis}</Row>
              <Row label="公厕等级取数">{methodology.grade_basis}</Row>
              <Row label="数字联动">{methodology.consistency_rule}</Row>
              <Row label="未闭环状态">{methodology.open_statuses.join('、')}</Row>
              <Row label="超期判定">{methodology.overdue_rule}</Row>
              <Row label="闭环率">{methodology.rectification_rule}</Row>
              <Row label="巡查均分">{methodology.score_rule}</Row>
              <Row label="公厕等级取值">{methodology.grade_options.join('、')}</Row>
            </dl>
          ) : (
            <div className="loading-block">口径说明加载中…</div>
          )}
        </Modal>
      ) : null}
    </>
  );
}
