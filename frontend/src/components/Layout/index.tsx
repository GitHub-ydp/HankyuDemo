import { useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { message, Modal } from 'antd';
import Icon from '../Icon';
import type { IconName } from '../Icon';
import { adminApi } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

interface NavEntry {
  to: string;
  icon: IconName;
  labelKey: string;
  badge?: number;
}

const OPS_NAV: NavEntry[] = [
  { to: '/', icon: 'dashboard', labelKey: 'menu.dashboard' },
  { to: '/rates', icon: 'rates', labelKey: 'menu.rates' },
  { to: '/upload', icon: 'import', labelKey: 'menu.upload' },
  { to: '/compare', icon: 'compare', labelKey: 'menu.compare' },
  { to: '/pkg', icon: 'package', labelKey: 'menu.pkg' },
];

const DATA_NAV: NavEntry[] = [{ to: '/carriers', icon: 'carriers', labelKey: 'menu.carriers' }];

const BREADCRUMBS: Record<string, string[]> = {
  '/': ['breadcrumb.dashboard'],
  '/rates': ['breadcrumb.rateGroup', 'breadcrumb.rates'],
  '/batches': ['breadcrumb.rateGroup', 'breadcrumb.batches'],
  '/upload': ['breadcrumb.rateGroup', 'breadcrumb.upload'],
  '/compare': ['breadcrumb.rateGroup', 'breadcrumb.compare'],
  '/pkg': ['breadcrumb.pkg'],
  '/emails': ['breadcrumb.emails'],
  '/carriers': ['breadcrumb.dataGroup', 'breadcrumb.carriers'],
  '/settings': ['breadcrumb.settings'],
};

export default function AppLayout() {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [resetting, setResetting] = useState(false);

  const crumbs = useMemo(() => {
    const raw = BREADCRUMBS[location.pathname];
    if (raw) return raw.map((k) => t(k));
    return [t('breadcrumb.dashboard')];
  }, [location.pathname, t]);

  const handleReset = () => {
    Modal.confirm({
      title: t('admin.resetTitle'),
      content: t('admin.resetDesc'),
      okText: t('admin.resetOk'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        setResetting(true);
        try {
          const res = await adminApi.resetRates();
          const d = (res?.data || {}) as {
            rates_deleted?: number;
            carriers_deleted?: number;
            carriers_kept_dict?: number;
            upload_logs_deleted?: number;
          };
          message.success(
            t('admin.resetSuccess', {
              rates: d.rates_deleted ?? 0,
              carriers: d.carriers_deleted ?? 0,
              kept: d.carriers_kept_dict ?? 0,
              logs: d.upload_logs_deleted ?? 0,
            })
          );
          setTimeout(() => window.location.reload(), 600);
        } catch (e) {
          message.error(
            t('admin.resetFailed') + (e instanceof Error ? e.message : String(e))
          );
        } finally {
          setResetting(false);
        }
      },
    });
  };

  const renderNav = (entry: NavEntry) => (
    <NavLink
      key={entry.to}
      to={entry.to}
      end={entry.to === '/'}
      className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
    >
      <Icon name={entry.icon} size={16} className="nav-icon" />
      <span>{t(entry.labelKey)}</span>
      {entry.badge ? <span className="nav-badge">{entry.badge}</span> : null}
    </NavLink>
  );

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">
            <Icon name="ship" size={18} color="#fff" />
          </div>
          <div className="brand-text">
            <div className="brand-zh">{t('auth.brand.zh')}</div>
            <div className="brand-en">Rate Hub</div>
          </div>
        </div>

        <div className="nav-section">{t('nav.operations')}</div>
        {OPS_NAV.map(renderNav)}

        <div className="nav-section">{t('nav.data')}</div>
        {DATA_NAV.map(renderNav)}

        <div className="sidebar-foot">
          <div className="avatar">{user?.initial || 'HH'}</div>
          <div className="user-meta">
            <div className="name">{user?.name || '—'}</div>
            <div className="role">{user?.role || 'GUEST'}</div>
          </div>
          <button
            type="button"
            className="icon-btn"
            style={{ color: '#6A7A90' }}
            onClick={handleLogout}
            title={t('auth.logout')}
          >
            <Icon name="logout" size={14} />
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div className="breadcrumb">
            <span>{t('auth.brand.zh')}</span>
            <span className="sep">/</span>
            {crumbs.map((label, i) => (
              <span key={i}>
                {i > 0 && <span className="sep">/</span>}
                <span className={i === crumbs.length - 1 ? 'cur' : ''}>{label}</span>
              </span>
            ))}
          </div>
          <div className="topbar-right">
            <div className="lang-switch">
              {(['zh', 'en', 'ja'] as const).map((code) => (
                <button
                  type="button"
                  key={code}
                  className={i18n.language === code ? 'on' : ''}
                  onClick={() => i18n.changeLanguage(code)}
                >
                  {code === 'zh' ? '中' : code === 'ja' ? '日' : 'EN'}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="icon-btn"
              title={t('admin.resetBtn')}
              onClick={handleReset}
              disabled={resetting}
              style={{ color: 'var(--danger)' }}
            >
              <Icon name="trash" size={16} />
            </button>
            <button
              type="button"
              className="icon-btn"
              title={t('settings.menu.settings')}
              onClick={() => navigate('/settings')}
            >
              <Icon name="settings" size={16} />
            </button>
            <button type="button" className="icon-btn" title={t('topbar.help')}>
              <Icon name="help" size={16} />
            </button>
            <button type="button" className="icon-btn" title={t('topbar.notifications')}>
              <Icon name="bell" size={16} />
            </button>
          </div>
        </div>

        <Outlet />
      </div>
    </div>
  );
}
