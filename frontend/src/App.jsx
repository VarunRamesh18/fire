import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Pipeline from './pages/Pipeline'
import Dashboard from './pages/Dashboard'
import LiveMonitoring from './pages/LiveMonitoring'
import Analytics from './pages/Analytics'
import EventHistory from './pages/EventHistory'
import Settings from './pages/Settings'
import Presenter from './pages/Presenter'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Pipeline />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/live" element={<LiveMonitoring />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/history" element={<EventHistory />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/presenter" element={<Presenter />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
