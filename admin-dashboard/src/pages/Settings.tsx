import { Save } from 'lucide-react';
import { useState } from 'react';

export default function Settings() {
  const [settings, setSettings] = useState({
    instanceName: 'My Nexus',
    publicUrl: 'https://nexus.example.com',
    allowRegistration: true,
    allowFederation: true,
    requireApproval: false,
    maxMemoriesPerAgent: 10000,
    maxMediaSizeMB: 100,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-gray-600 mt-1">Configure your Nexus instance</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
          <Save className="w-4 h-4" />
          Save Changes
        </button>
      </div>

      <div className="grid gap-6 max-w-2xl">
        {/* General Settings */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold mb-4">General</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Instance Name
              </label>
              <input
                type="text"
                value={settings.instanceName}
                onChange={(e) =>
                  setSettings({ ...settings, instanceName: e.target.value })
                }
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Public URL
              </label>
              <input
                type="url"
                value={settings.publicUrl}
                onChange={(e) =>
                  setSettings({ ...settings, publicUrl: e.target.value })
                }
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
          </div>
        </div>

        {/* Access Control */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold mb-4">Access Control</h2>
          <div className="space-y-4">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.allowRegistration}
                onChange={(e) =>
                  setSettings({ ...settings, allowRegistration: e.target.checked })
                }
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <span className="text-sm text-gray-700">Allow new agent registration</span>
            </label>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.requireApproval}
                onChange={(e) =>
                  setSettings({ ...settings, requireApproval: e.target.checked })
                }
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <span className="text-sm text-gray-700">
                Require approval for new registrations
              </span>
            </label>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.allowFederation}
                onChange={(e) =>
                  setSettings({ ...settings, allowFederation: e.target.checked })
                }
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <span className="text-sm text-gray-700">Allow federation connections</span>
            </label>
          </div>
        </div>

        {/* Limits */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold mb-4">Limits</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max Memories per Agent
              </label>
              <input
                type="number"
                value={settings.maxMemoriesPerAgent}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    maxMemoriesPerAgent: parseInt(e.target.value),
                  })
                }
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max Media Size (MB)
              </label>
              <input
                type="number"
                value={settings.maxMediaSizeMB}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    maxMediaSizeMB: parseInt(e.target.value),
                  })
                }
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
