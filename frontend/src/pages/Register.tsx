import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icon';
import type { IconName } from '../components/Icon';
import { useAuth } from '../contexts/AuthContext';

const FEATURES: { icon: IconName; key: 'parse' | 'pkg' | 'mail' }[] = [
  { icon: 'import', key: 'parse' },
  { icon: 'package', key: 'pkg' },
  { icon: 'mail', key: 'mail' },
];

export default function RegisterPage() {
  const { t, i18n } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('两次输入的密码不一致');
      return;
    }
    setSubmitting(true);
    try {
      await register(email, password, name);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
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
        </div>

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
            Create Account · Join the Control Tower
          </div>
          <h1>
            {t('auth.register.heroLead')}
            <span className="accent">{t('auth.register.heroAccent')}</span>
          </h1>
          <p className="lede">{t('auth.register.heroLede')}</p>
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
          <h2>{t('auth.register.title')}</h2>
          <div className="sub">{t('auth.register.subtitle')}</div>

          <div className="field-row">
            <label htmlFor="reg-name">{t('auth.field.name')}</label>
            <input
              id="reg-name"
              className="login-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('auth.field.namePlaceholder')}
            />
          </div>
          <div className="field-row">
            <label htmlFor="reg-email">{t('auth.field.email')}</label>
            <input
              id="reg-email"
              className="login-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@hankyu-hanshin.com"
            />
          </div>
          <div className="field-row">
            <label htmlFor="reg-password">{t('auth.field.password')}</label>
            <input
              id="reg-password"
              className="login-input"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 6 位"
            />
          </div>
          <div className="field-row">
            <label htmlFor="reg-confirm">{t('auth.field.confirm')}</label>
            <input
              id="reg-confirm"
              className="login-input"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="再输一次"
            />
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

          <button className="login-btn" type="submit" disabled={submitting} style={{ marginTop: 8 }}>
            {submitting ? t('auth.register.submitting') : t('auth.register.submit')}
          </button>

          <div
            style={{
              marginTop: 16,
              textAlign: 'center',
              fontSize: 12.5,
              color: '#6A7A90',
            }}
          >
            {t('auth.register.hasAccount')}{' '}
            <Link to="/login" style={{ color: '#4FAFB5', textDecoration: 'none' }}>
              {t('auth.register.toLogin')}
            </Link>
          </div>
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
