import { Link } from "react-router-dom";

interface Props {
  title: string;
  subtitle?: string;
}

/** 统一的内页页头：返回 + 标题 + 副标题 */
export default function PageHeader({ title, subtitle }: Props) {
  return (
    <div className="page-head">
      <div style={{ marginBottom: 12 }}>
        <Link to="/" className="btn-link">← 返回首页</Link>
      </div>
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </div>
  );
}
