import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import jaJP from 'antd/locale/ja_JP';
import enUS from 'antd/locale/en_US';
import { useTranslation } from 'react-i18next';
import AppLayout from './components/Layout';
import Dashboard from './pages/Dashboard';
import RateList from './pages/RateList';
import RateUpload from './pages/RateUpload';
import RateCompare from './pages/RateCompare';
import CarrierList from './pages/CarrierList';
import EmailSearch from './pages/EmailSearch';
import PkgAutoFill from './pages/PkgAutoFill';
import './i18n';

export default function App() {
  const { i18n } = useTranslation();
  const antLocales = {
    zh: zhCN,
    ja: jaJP,
    en: enUS,
  };
  const routerBasename = import.meta.env.BASE_URL === '/' ? undefined : import.meta.env.BASE_URL;

  return (
    <ConfigProvider locale={antLocales[i18n.language as keyof typeof antLocales] ?? zhCN}>
      <BrowserRouter basename={routerBasename}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/pkg" element={<PkgAutoFill />} />
            <Route path="/rates" element={<RateList />} />
            <Route path="/upload" element={<RateUpload />} />
            <Route path="/compare" element={<RateCompare />} />
            <Route path="/carriers" element={<CarrierList />} />
            <Route path="/emails" element={<EmailSearch />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}
