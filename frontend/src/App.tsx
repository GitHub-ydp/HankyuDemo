import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import jaJP from 'antd/locale/ja_JP';
import enUS from 'antd/locale/en_US';
import { useTranslation } from 'react-i18next';
import AppLayout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider } from './contexts/AuthContext';
import Dashboard from './pages/Dashboard';
import RateList from './pages/RateList';
import RateUpload from './pages/RateUpload';
import RateCompare from './pages/RateCompare';
import CarrierList from './pages/CarrierList';
import EmailSearch from './pages/EmailSearch';
import PkgAutoFill from './pages/PkgAutoFill';
import Settings from './pages/Settings';
import LoginPage from './pages/Login';
import RegisterPage from './pages/Register';
import './i18n';

const antLocales = {
  zh: zhCN,
  ja: jaJP,
  en: enUS,
} as const;

export default function App() {
  const { i18n } = useTranslation();
  const routerBasename = import.meta.env.BASE_URL === '/' ? undefined : import.meta.env.BASE_URL;

  return (
    <ConfigProvider
      locale={antLocales[i18n.language as keyof typeof antLocales] ?? zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1E6B74',
          colorInfo: '#2E90FA',
          colorSuccess: '#12B76A',
          colorWarning: '#F79009',
          colorError: '#F04438',
          borderRadius: 6,
          fontFamily:
            "'Noto Sans SC', 'Space Grotesk', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif",
        },
      }}
    >
      <AuthProvider>
        <BrowserRouter basename={routerBasename}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/pkg" element={<PkgAutoFill />} />
                <Route path="/rates" element={<RateList />} />
                <Route path="/batches" element={<Navigate to="/upload" replace />} />
                <Route path="/upload" element={<RateUpload />} />
                <Route path="/compare" element={<RateCompare />} />
                <Route path="/carriers" element={<CarrierList />} />
                <Route path="/emails" element={<EmailSearch />} />
                <Route path="/settings" element={<Settings />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ConfigProvider>
  );
}
