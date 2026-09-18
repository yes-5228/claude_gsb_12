import Field from './Field.jsx';

/**
 * 区域 + 公厕等级两个统一口径筛选项。
 * 巡查、问题、看板共用，保证三处筛选维度一致。
 * value: { district: string, grade: string }，onChange(key, value)
 */
export default function ScopeFields({ districts = [], grades = [], value, onChange }) {
  return (
    <>
      <Field label="所属区域">
        <select value={value.district || ''} onChange={(e) => onChange('district', e.target.value)}>
          <option value="">全部区域</option>
          {districts.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </Field>
      <Field label="公厕等级" hint="按公厕档案等级（一类/二类/三类）">
        <select value={value.grade || ''} onChange={(e) => onChange('grade', e.target.value)}>
          <option value="">全部等级</option>
          {grades.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </Field>
    </>
  );
}
