/**
 * Enterprise Management Dashboard.
 * Provides real-time visibility into reception operations.
 *
 * Sections:
 * - Stats overview (visitors today, active, registered, etc.)
 * - Live reception queue (active visits with duration)
 * - Host approval requests (pending/responded)
 * - Recent visitors feed
 * - Notification delivery status
 * - System health
 * - Role-aware: different sections visible based on user permissions
 */

import { useState, useEffect, useCallback } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth } from '../context/AuthContext'
import { apiFetch, authApi } from '../lib/api'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

// ============================================================
// Types
// ============================================================

interface DashboardStats {
  total_visitors_today: number
  new_visitors_today: number
  returning_visitors_today: number
  active_visitors: number
  total_registered: number
  total_employees: number
  active_conversations: number
}

interface RecentVisitor {
  visitor_id: string
  name: string
  company: string | null
  arrival_time: string
  status: string
  visit_type: string
}

interface SystemStatus {
  camera_active: boolean
  ai_service_active: boolean
  tts_active: boolean
  stt_active: boolean
  database_active: boolean
  vision_active: boolean
  websocket_active: boolean
  uptime_seconds: number
}

interface PendingApproval {
  request_id: string
  visitor_name: string
  employee_name: string
  purpose: string | null
  created_at: string
  expires_at: string
  status: string
}

interface ActiveVisit {
  visit_id: string
  visitor_id: string
  visitor_name: string
  arrival_time: string
  duration_minutes: number
  status: string
  employee_id: string | null
  purpose: string | null
}

// ============================================================
// Component
// ============================================================

function DashboardPage() {
  const { hasPermission, role } = useAuth()

  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [recentVisitors, setRecentVisitors] = useState<RecentVisitor[]>([])
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([])
  const [activeVisits, setActiveVisits] = useState<ActiveVisit[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())
  const [wsUrl, setWsUrl] = useState<string>('')
  const [activeTab, setActiveTab] = useState<'overview' | 'queue' | 'approvals' | 'system'>('overview')

  // Get WebSocket ticket
  useEffect(() => {
    let cancelled = false
    async function getTicket() {
      try {
        const { ticket } = await authApi.getWsTicket()
        if (!cancelled) {
          setWsUrl(`${WS_URL}/ws/dashboard?ticket=${ticket}`)
        }
      } catch (err) {
        console.error('Failed to get dashboard WS ticket:', err)
      }
    }
    getTicket()
    return () => { cancelled = true }
  }, [])

  // WebSocket for real-time updates
  const { isConnected } = useWebSocket(wsUrl, {
    onMessage: (data) => {
      if (data.type === 'new_session' || data.type === 'session_ended' || data.type === 'conversation_update') {
        fetchAll()
      }
    },
    autoConnect: !!wsUrl,
  })

  // Data fetchers
  const fetchStats = useCallback(async () => {
    try {
      const data = await apiFetch<DashboardStats>('/api/dashboard/stats')
      setStats(data)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }, [])

  const fetchRecentVisitors = useCallback(async () => {
    try {
      const data = await apiFetch<RecentVisitor[]>('/api/dashboard/recent-visitors')
      setRecentVisitors(data)
    } catch (error) {
      console.error('Failed to fetch visitors:', error)
    }
  }, [])

  const fetchSystemStatus = useCallback(async () => {
    try {
      const data = await apiFetch<SystemStatus>('/api/dashboard/system-status')
      setSystemStatus(data)
    } catch (error) {
      console.error('Failed to fetch system status:', error)
    }
  }, [])

  const fetchPendingApprovals = useCallback(async () => {
    try {
      const data = await apiFetch<{ pending_approvals: PendingApproval[] }>('/api/host-approval/pending')
      setPendingApprovals(data.pending_approvals || [])
    } catch (error) {
      console.error('Failed to fetch approvals:', error)
    }
  }, [])

  const fetchActiveVisits = useCallback(async () => {
    try {
      const data = await apiFetch<ActiveVisit[]>('/api/visits/active')
      setActiveVisits(data)
    } catch (error) {
      console.error('Failed to fetch active visits:', error)
    }
  }, [])

  const fetchAll = useCallback(async () => {
    await Promise.all([
      fetchStats(),
      fetchRecentVisitors(),
      fetchSystemStatus(),
      fetchPendingApprovals(),
      fetchActiveVisits(),
    ])
    setLastUpdate(new Date())
  }, [fetchStats, fetchRecentVisitors, fetchSystemStatus, fetchPendingApprovals, fetchActiveVisits])

  useEffect(() => {
    setLoading(true)
    fetchAll().finally(() => setLoading(false))
    const interval = setInterval(fetchAll, 30000)
    return () => clearInterval(interval)
  }, [fetchAll])

  const formatUptime = (seconds: number): string => {
    const hrs = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    return `${hrs}h ${mins}m`
  }

  const formatTime = (isoString: string): string => {
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  // ============================================================
  // Render
  // ============================================================

  return (
    <div className="min-h-screen pt-20 pb-6 px-4 lg:px-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Management Dashboard</h1>
            <p className="text-sm text-gray-400 mt-1">Real-time reception monitoring</p>
          </div>
          <div className="flex items-center gap-3">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-400">
              Updated: {lastUpdate.toLocaleTimeString()}
            </span>
          </div>
        </div>

        {/* Tab navigation */}
        <nav className="flex gap-1 mb-6 bg-gray-800/50 p-1 rounded-xl w-fit" role="tablist" aria-label="Dashboard sections">
          {(['overview', 'queue', 'approvals', 'system'] as const).map(tab => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-all ${
                activeTab === tab
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              {tab === 'approvals' && pendingApprovals.length > 0 && (
                <span className="inline-block w-5 h-5 mr-1 text-xs leading-5 text-center bg-red-500 rounded-full">
                  {pendingApprovals.length}
                </span>
              )}
              {tab}
            </button>
          ))}
        </nav>

        {/* Stats Cards (always visible) */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
            <StatCard label="Today" value={stats.total_visitors_today} color="blue" />
            <StatCard label="New" value={stats.new_visitors_today} color="green" />
            <StatCard label="Returning" value={stats.returning_visitors_today} color="purple" />
            <StatCard label="Active Now" value={stats.active_visitors} color="yellow" />
            <StatCard label="Registered" value={stats.total_registered} color="cyan" />
            <StatCard label="Employees" value={stats.total_employees} color="indigo" />
            <StatCard label="Conversations" value={stats.active_conversations} color="pink" />
          </div>
        )}

        {/* Tab content */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Recent Visitors */}
            <div className="glass-panel p-5">
              <h2 className="text-lg font-semibold text-white mb-4">Today's Visitors</h2>
              {recentVisitors.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">No visitors today yet</p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {recentVisitors.map(v => (
                    <div key={v.visitor_id} className="flex items-center justify-between p-3 bg-gray-800/40 rounded-lg">
                      <div>
                        <p className="text-sm text-white font-medium">{v.name}</p>
                        <p className="text-xs text-gray-400">{v.company || 'No company'} · {formatTime(v.arrival_time)}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          v.visit_type === 'new' ? 'bg-green-600/20 text-green-400' : 'bg-blue-600/20 text-blue-400'
                        }`}>
                          {v.visit_type}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          v.status === 'arrived' ? 'bg-yellow-600/20 text-yellow-400' : 'bg-gray-600/20 text-gray-400'
                        }`}>
                          {v.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pending Approvals */}
            <div className="glass-panel p-5">
              <h2 className="text-lg font-semibold text-white mb-4">
                Pending Approvals
                {pendingApprovals.length > 0 && (
                  <span className="ml-2 text-xs bg-red-500 text-white px-2 py-0.5 rounded-full">
                    {pendingApprovals.length}
                  </span>
                )}
              </h2>
              {pendingApprovals.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">No pending approvals</p>
              ) : (
                <div className="space-y-2">
                  {pendingApprovals.map(a => (
                    <div key={a.request_id} className="p-3 bg-yellow-900/20 border border-yellow-700/30 rounded-lg">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="text-sm text-white font-medium">{a.visitor_name}</p>
                          <p className="text-xs text-gray-400">Waiting for: {a.employee_name}</p>
                          {a.purpose && <p className="text-xs text-gray-500 mt-0.5">{a.purpose}</p>}
                        </div>
                        <span className="text-xs text-yellow-400 bg-yellow-900/40 px-2 py-0.5 rounded">
                          {a.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'queue' && (
          <div className="glass-panel p-5">
            <h2 className="text-lg font-semibold text-white mb-4">Live Reception Queue</h2>
            {activeVisits.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-8">No active visits</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full" role="table">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left py-2 px-3 text-xs font-medium text-gray-400">Visitor</th>
                      <th className="text-left py-2 px-3 text-xs font-medium text-gray-400">Arrival</th>
                      <th className="text-left py-2 px-3 text-xs font-medium text-gray-400">Duration</th>
                      <th className="text-left py-2 px-3 text-xs font-medium text-gray-400">Status</th>
                      <th className="text-left py-2 px-3 text-xs font-medium text-gray-400">Purpose</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeVisits.map(visit => (
                      <tr key={visit.visit_id} className="border-b border-gray-800 hover:bg-gray-800/40">
                        <td className="py-3 px-3 text-sm text-white font-medium">{visit.visitor_name}</td>
                        <td className="py-3 px-3 text-sm text-gray-400">{formatTime(visit.arrival_time)}</td>
                        <td className="py-3 px-3 text-sm text-gray-400">{visit.duration_minutes} min</td>
                        <td className="py-3 px-3">
                          <span className="text-xs px-2 py-0.5 rounded-full bg-green-600/20 text-green-400">
                            {visit.status}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-sm text-gray-500">{visit.purpose || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'approvals' && (
          <div className="glass-panel p-5">
            <h2 className="text-lg font-semibold text-white mb-4">Host Approval Requests</h2>
            {pendingApprovals.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-8">No pending approval requests</p>
            ) : (
              <div className="space-y-3">
                {pendingApprovals.map(a => (
                  <div key={a.request_id} className="p-4 bg-gray-800/60 border border-gray-700 rounded-lg">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h3 className="text-sm text-white font-semibold">{a.visitor_name}</h3>
                        <p className="text-xs text-gray-400">Requesting to meet: {a.employee_name}</p>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded ${
                        a.status === 'pending' ? 'bg-yellow-600/30 text-yellow-400' : 'bg-gray-600/30 text-gray-400'
                      }`}>
                        {a.status}
                      </span>
                    </div>
                    {a.purpose && <p className="text-xs text-gray-500">Purpose: {a.purpose}</p>}
                    <p className="text-xs text-gray-600 mt-1">
                      Created: {formatTime(a.created_at)} · Expires: {formatTime(a.expires_at)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'system' && systemStatus && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="glass-panel p-5">
              <h2 className="text-lg font-semibold text-white mb-4">Service Health</h2>
              <div className="space-y-3">
                <ServiceRow name="Database" active={systemStatus.database_active} />
                <ServiceRow name="AI (Bedrock)" active={systemStatus.ai_service_active} />
                <ServiceRow name="Text-to-Speech (Polly)" active={systemStatus.tts_active} />
                <ServiceRow name="Speech-to-Text" active={systemStatus.stt_active} />
                <ServiceRow name="Vision AI" active={systemStatus.vision_active} />
                <ServiceRow name="Camera" active={systemStatus.camera_active} />
                <ServiceRow name="WebSocket" active={isConnected} />
              </div>
              <div className="mt-4 pt-3 border-t border-gray-700">
                <p className="text-xs text-gray-400">Uptime: {formatUptime(systemStatus.uptime_seconds)}</p>
              </div>
            </div>

            <div className="glass-panel p-5">
              <h2 className="text-lg font-semibold text-white mb-4">System Info</h2>
              <div className="space-y-2 text-sm">
                <InfoRow label="Environment" value={import.meta.env.MODE} />
                <InfoRow label="API Endpoint" value={import.meta.env.VITE_API_URL || 'localhost:8000'} />
                <InfoRow label="WebSocket" value={isConnected ? 'Connected' : 'Disconnected'} />
                <InfoRow label="User Role" value={role || 'N/A'} />
                <InfoRow label="Refresh Rate" value="30 seconds" />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================
// Sub-components
// ============================================================

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, string> = {
    blue: 'from-blue-600/20 to-blue-900/10 border-blue-700/30',
    green: 'from-green-600/20 to-green-900/10 border-green-700/30',
    purple: 'from-purple-600/20 to-purple-900/10 border-purple-700/30',
    yellow: 'from-yellow-600/20 to-yellow-900/10 border-yellow-700/30',
    cyan: 'from-cyan-600/20 to-cyan-900/10 border-cyan-700/30',
    indigo: 'from-indigo-600/20 to-indigo-900/10 border-indigo-700/30',
    pink: 'from-pink-600/20 to-pink-900/10 border-pink-700/30',
  }
  return (
    <div className={`bg-gradient-to-br ${colorMap[color] || colorMap.blue} border rounded-xl p-3`}>
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-xs text-gray-400 mt-0.5">{label}</p>
    </div>
  )
}

function ServiceRow({ name, active }: { name: string; active: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-gray-300">{name}</span>
      <div className="flex items-center gap-1.5">
        <div className={`w-2 h-2 rounded-full ${active ? 'bg-green-500' : 'bg-red-500'}`} />
        <span className={`text-xs ${active ? 'text-green-400' : 'text-red-400'}`}>
          {active ? 'Online' : 'Offline'}
        </span>
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-gray-400">{label}</span>
      <span className="text-white font-mono text-xs">{value}</span>
    </div>
  )
}

export default DashboardPage
