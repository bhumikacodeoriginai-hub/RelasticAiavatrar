import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import ReceptionistPage from './pages/ReceptionistPage'
import DashboardPage from './pages/DashboardPage'
import Navbar from './components/Navbar'

function App() {
  return (
    <AuthProvider>
      <div className="min-h-screen bg-gray-900">
        <Routes>
          {/* Public route — Login */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protected routes — require authentication */}
          <Route
            path="/"
            element={
              <ProtectedRoute requiredRoles={['super_admin', 'it_admin', 'reception_manager', 'receptionist', 'kiosk_device']}>
                <>
                  <Navbar />
                  <ReceptionistPage />
                </>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute requiredRoles={['super_admin', 'it_admin', 'security_officer', 'reception_manager', 'receptionist', 'auditor', 'viewer']}>
                <>
                  <Navbar />
                  <DashboardPage />
                </>
              </ProtectedRoute>
            }
          />
        </Routes>
      </div>
    </AuthProvider>
  )
}

export default App
