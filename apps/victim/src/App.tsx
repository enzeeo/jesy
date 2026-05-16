import { Route, Routes } from 'react-router-dom';

import Demo from './pages/Demo';
import Home from './pages/Home';
import Incident from './pages/Incident';
import ManualLocation from './pages/ManualLocation';
import Onboard from './pages/Onboard';
import Status from './pages/Status';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/onboard" element={<Onboard />} />
      <Route path="/incident" element={<Incident />} />
      <Route path="/manual-location" element={<ManualLocation />} />
      <Route path="/status/:id" element={<Status />} />
      <Route path="/demo" element={<Demo />} />
      <Route path="*" element={<Home />} />
    </Routes>
  );
}
