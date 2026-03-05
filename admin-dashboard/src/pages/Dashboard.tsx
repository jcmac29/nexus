import { Bot, Brain, Users, Globe, Activity } from 'lucide-react';
import StatCard from '../components/StatCard';
import { useStats, useRecentActivity } from '../hooks/useApi';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

// Mock data for chart - would come from API in production
const chartData = [
  { time: '00:00', invocations: 120, messages: 45 },
  { time: '04:00', invocations: 80, messages: 30 },
  { time: '08:00', invocations: 200, messages: 90 },
  { time: '12:00', invocations: 350, messages: 150 },
  { time: '16:00', invocations: 280, messages: 120 },
  { time: '20:00', invocations: 180, messages: 70 },
];

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useStats();
  const { data: activity, isLoading: activityLoading } = useRecentActivity();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-1">Overview of your Nexus instance</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Active Agents"
          value={statsLoading ? '...' : stats?.active_agents ?? 0}
          change="+12% this week"
          changeType="positive"
          icon={Bot}
        />
        <StatCard
          title="Total Memories"
          value={statsLoading ? '...' : stats?.total_memories ?? 0}
          change="+156 today"
          changeType="positive"
          icon={Brain}
        />
        <StatCard
          title="Teams"
          value={statsLoading ? '...' : stats?.total_teams ?? 0}
          icon={Users}
        />
        <StatCard
          title="API Calls Today"
          value={statsLoading ? '...' : stats?.api_calls_today ?? 0}
          icon={Globe}
        />
      </div>

      {/* Charts and Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activity Chart */}
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold mb-4">Activity Overview</h2>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="invocations"
                  stroke="#4f46e5"
                  strokeWidth={2}
                  dot={false}
                  name="Invocations"
                />
                <Line
                  type="monotone"
                  dataKey="messages"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  name="Messages"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold mb-4">Recent Activity</h2>
          <div className="space-y-4">
            {activityLoading ? (
              <div className="animate-pulse space-y-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-12 bg-gray-100 rounded" />
                ))}
              </div>
            ) : (
              (activity ?? []).slice(0, 5).map((item) => (
                <div
                  key={item.id}
                  className="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-50"
                >
                  <div className="p-2 bg-indigo-50 rounded-lg">
                    <Activity className="w-4 h-4 text-indigo-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {item.type}
                    </p>
                    <p className="text-xs text-gray-500">{item.description}</p>
                  </div>
                  <span className="text-xs text-gray-400">
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))
            )}
            {!activityLoading && (!activity || activity.length === 0) && (
              <p className="text-center text-gray-500 py-4">No recent activity</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
