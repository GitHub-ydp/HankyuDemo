import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icon';
import type { IconName } from '../components/Icon';
import { useAuth } from '../contexts/AuthContext';

const PORTS: Array<[number, number, string]> = [
  [120, 520, 'SHA'],
  [520, 380, 'LAX'],
  [700, 260, 'RTM'],
  [160, 620, 'HKG'],
  [720, 460, 'NYC'],
  [450, 500, 'HAM'],
  [100, 440, 'TYO'],
];

const PINGS = [
  { top: '30%', left: '22%' },
  { top: '58%', left: '40%' },
  { top: '42%', left: '62%' },
  { top: '70%', left: '28%' },
  { top: '24%', left: '50%' },
];

const FEATURES: { icon: IconName; key: 'parse' | 'pkg' | 'mail' }[] = [
  { icon: 'import', key: 'parse' },
  { icon: 'package', key: 'pkg' },
  { icon: 'mail', key: 'mail' },
];

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-root">
      <div className="login-brand-side">
        <div className="radar">
          <div className="radar-ring" />
          <div className="radar-ring r2" />
          <div className="radar-ring r3" />
          <div className="radar-ring r4" />
          <div className="radar-sweep" />
          {PINGS.map((p, i) => (
            <div
              key={i}
              className="ping"
              style={{ top: p.top, left: p.left, animationDelay: `${i * 0.5}s` }}
            />
          ))}
        </div>

        <svg className="route-map" viewBox="0 0 800 900" preserveAspectRatio="xMidYMid slice">
          <defs>
            <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
              <path d="M 60 0 L 0 0 0 60" fill="none" stroke="rgba(79,175,181,.06)" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="800" height="900" fill="url(#grid)" />
          <path d="M 120 520 Q 300 300 520 380 T 700 260" fill="none" stroke="rgba(79,175,181,.35)" strokeWidth="1" strokeDasharray="3 4" />
          <path d="M 160 620 Q 350 550 580 580 T 720 460" fill="none" stroke="rgba(79,175,181,.22)" strokeWidth="1" strokeDasharray="2 4" />
          <path d="M 100 440 Q 280 420 450 500 T 680 600" fill="none" stroke="rgba(79,175,181,.28)" strokeWidth="1" strokeDasharray="3 4" />
          {PORTS.map(([x, y, code]) => (
            <g key={code}>
              <circle cx={x} cy={y} r="3" fill="#4FAFB5" />
              <circle cx={x} cy={y} r="8" fill="none" stroke="rgba(79,175,181,.4)" strokeWidth="0.5" />
              <text x={x + 10} y={y + 4} fill="#4FAFB5" fontSize="9" fontFamily="Space Grotesk" letterSpacing="1.5">
                {code}
              </text>
            </g>
          ))}
        </svg>

        <div className="login-logo">
          <div className="mark">
            <Icon name="ship" size={22} color="#fff" />
          </div>
          <div>
            <div className="zh">{t('auth.brand.zh')}</div>
            <div className="en">{t('auth.brand.en')}</div>
          </div>
        </div>

        <div className="login-hero">
          <div className="eyebrow">
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#4FAFB5' }} />
            Ocean Freight · Global Control Tower
          </div>
          <h1>
            {t('auth.hero.titleLead')}
            <span className="accent">{t('auth.hero.titleAccent')}</span>，
            <br />
            {t('auth.hero.titleTail')}
          </h1>
          <p className="lede">
            {t('auth.hero.ledeLead')}
            <b style={{ color: '#B8C3D1' }}>{t('auth.hero.slow')}</b>
            {t('auth.hero.ledeBridge')}
            <b style={{ color: '#4FAFB5' }}>{t('auth.hero.fast')}</b>
            {t('auth.hero.ledeTail')}
          </p>
        </div>

        <div className="login-stats">
          {FEATURES.map((f) => (
            <div className="login-feat" key={f.key}>
              <div className="ic">
                <Icon name={f.icon} size={14} />
              </div>
              <div className="t">{t(`auth.features.${f.key}.title`)}</div>
              <div className="d">{t(`auth.features.${f.key}.desc`)}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="login-form-side">
        <div className="top-right">
          <div className="env-switch">
            <span className="env-dot" />
            <span>{(import.meta.env.MODE || 'development').toUpperCase()}</span>
          </div>
          <div className="login-lang">
            <button type="button" className={i18n.language === 'zh' ? 'on' : ''} onClick={() => i18n.changeLanguage('zh')}>
              中
            </button>
            <button type="button" className={i18n.language === 'en' ? 'on' : ''} onClick={() => i18n.changeLanguage('en')}>
              EN
            </button>
            <button type="button" className={i18n.language === 'ja' ? 'on' : ''} onClick={() => i18n.changeLanguage('ja')}>
              日
            </button>
          </div>
        </div>

        <form className="login-form" onSubmit={submit}>
          <h2>{t('auth.login.title')}</h2>
          <div className="sub">{t('auth.login.subtitle')}</div>

          <div className="field-row">
            <label htmlFor="login-email">{t('auth.field.email')}</label>
            <input
              id="login-email"
              className="login-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@hankyu-hanshin.com"
            />
          </div>
          <div className="field-row">
            <label htmlFor="login-password">{t('auth.field.password')}</label>
            <input
              id="login-password"
              className="login-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          <div className="login-row">
            <label className="login-check" onClick={() => setRemember(!remember)}>
              <span className={`check${remember ? ' on' : ''}`}>
                {remember && <Icon name="check" size={10} color="#fff" />}
              </span>
              {t('auth.login.remember')}
            </label>
            <Link to="/register">{t('auth.login.toRegister')}</Link>
          </div>

          {error && (
            <div
              style={{
                color: '#FF8A82',
                fontSize: 12.5,
                marginBottom: 14,
                padding: '8px 12px',
                background: 'rgba(240,68,56,.08)',
                border: '1px solid rgba(240,68,56,.25)',
                borderRadius: 6,
              }}
            >
              {error}
            </div>
          )}

          <button className="login-btn" type="submit" disabled={submitting}>
            {submitting ? t('auth.login.submitting') : t('auth.login.submit')}
          </button>
        </form>

        <div className="login-foot">
          <div>© 2026 HANKYU HANSHIN EXPRESS</div>
          <div>
            <a href="#status">Status</a>
            <a href="#docs">Docs</a>
            <a href="#support">Support</a>
          </div>
        </div>
      </div>
    </div>
  );
}
