// 真实可从 API 驱动的 Dashboard 静态元数据 — 标签、快捷操作路由。
// 不含假数字、假 ticker、假 tasks — 那些已移除。
import type { IconName } from '../components/Icon';

// KPI 卡片的静态元数据（label / 单位），值由 rateApi.stats() 动态填充
export interface KpiMeta {
  key: 'total' | 'active' | 'draft' | 'lanes' | 'carriers';
  labelZh: string;
  labelEn: string;
  unit: string;
}

export const KPI_METAS: KpiMeta[] = [
  { key: 'total', labelZh: '运价总数', labelEn: 'Total Rates', unit: '条' },
  { key: 'active', labelZh: '生效运价', labelEn: 'Active', unit: '条' },
  { key: 'draft', labelZh: '草稿', labelEn: 'Draft', unit: '条' },
  { key: 'lanes', labelZh: '航线数', labelEn: 'Lanes', unit: '条' },
  { key: 'carriers', labelZh: '承运商', labelEn: 'Carriers', unit: '家' },
];

export interface QuickAction {
  icon: IconName;
  titleZh: string;
  desc: string;
  to: string;
}

export const QUICK_ACTIONS: QuickAction[] = [
  { icon: 'import', titleZh: '运价导入', desc: 'Excel / 邮件 / 图片解析', to: '/upload' },
  { icon: 'package', titleZh: 'PKG 自动填充', desc: '上传投标包即时匹配', to: '/pkg' },
  { icon: 'compare', titleZh: '运价对比', desc: '多承运商报价一览', to: '/compare' },
  { icon: 'mail', titleZh: '邮件分析', desc: '从邮件中提取运价洞察', to: '/emails' },
];
