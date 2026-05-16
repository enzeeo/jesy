import { Navigate, Route, Routes } from 'react-router-dom';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/demo" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/demo" element={<Dashboard />} />
      <Route path="*" element={<Navigate to="/demo" replace />} />
    </Routes>
  );
}
