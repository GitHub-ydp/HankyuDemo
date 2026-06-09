import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

// 嵌套在 ProtectedRoute 之内：loading 与未登录已由上层兜住，
// 这里只需判管理员身份（非管理员重定向回首页）
export default function AdminRoute() {
  const { user } = useAuth();
  if (!user?.isAdmin) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
