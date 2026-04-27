import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
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

const routerBasename = import.meta.env.BASE_URL === '/' ? undefined : import.meta.env.BASE_URL;

const router = createBrowserRouter(
  [
    { path: '/login', element: <LoginPage /> },
    { path: '/register', element: <RegisterPage /> },
    {
      element: <ProtectedRoute />,
      children: [
        {
          element: <AppLayout />,
          children: [
            { path: '/', element: <Dashboard /> },
            { path: '/pkg', element: <PkgAutoFill /> },
            { path: '/rates', element: <RateList /> },
            { path: '/batches', element: <Navigate to="/upload" replace /> },
            { path: '/upload', element: <RateUpload /> },
            { path: '/compare', element: <RateCompare /> },
            { path: '/carriers', element: <CarrierList /> },
            { path: '/emails', element: <EmailSearch /> },
            { path: '/settings', element: <Settings /> },
          ],
        },
      ],
    },
    { path: '*', element: <Navigate to="/" replace /> },
  ],
  { basename: routerBasename },
);

export default function App() {
  const { i18n } = useTranslation();

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
        <RouterProvider router={router} />
      </AuthProvider>
    </ConfigProvider>
  );
}
