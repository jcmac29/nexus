import { Save, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useSettings, useUpdateSettings } from '../hooks/useApi';

export default function Settings() {
  const { data: serverSettings, isLoading, error, refetch } = useSettings();
  const updateSettings = useUpdateSettings();

  const [settings, setSettings] = useState({
    instance_name: '',
    allow_registration: true,
    require_email_verification: false,
    default_rate_limit: 100,
    features: {} as Record<string, boolean>,
  });

  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  // Sync server settings to local state
  useEffect(() => {
    if (serverSettings) {
      setSettings({
        instance_name: serverSettings.instance_name,
        allow_registration: serverSettings.allow_registration,
        require_email_verification: serverSettings.require_email_verification,
        default_rate_limit: serverSettings.default_rate_limit,
        features: serverSettings.features,
      });
    }
  }, [serverSettings]);

  const handleSave = async () => {
    setSaveStatus('saving');
    try {
      await updateSettings.mutateAsync(settings);
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    }
  };

  const toggleFeature = (feature: string) => {
    setSettings({
      ...settings,
      features: {
        ...settings.features,
        [feature]: !settings.features[feature],
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="w-12 h-12 mx-auto text-red-500 mb-4" />
        <p className="text-red-500">Failed to load settings</p>
        <button
          onClick={() => refetch()}
          className="mt-4 px-4 py-2 border rounded-lg hover:bg-gray-50"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-gray-600 mt-1">Configure your Nexus instance</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            onClick={handleSave}
            disabled={saveStatus === 'saving'}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            {saveStatus === 'saving' ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : saveStatus === 'saved' ? (
              <CheckCircle className="w-4 h-4" />
            ) : saveStatus === 'error' ? (
              <AlertCircle className="w-4 h-4" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved!' : saveStatus === 'error' ? 'Error' : 'Save Changes'}
          </button>
        </div>
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
                value={settings.instance_name}
                onChange={(e) =>
                  setSettings({ ...settings, instance_name: e.target.value })
                }
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Default Rate Limit (requests/minute)
              </label>
              <input
                type="number"
                value={settings.default_rate_limit}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    default_rate_limit: parseInt(e.target.value) || 100,
                  })
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
                checked={settings.allow_registration}
                onChange={(e) =>
                  setSettings({ ...settings, allow_registration: e.target.checked })
                }
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <span className="text-sm text-gray-700">Allow new agent registration</span>
            </label>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.require_email_verification}
                onChange={(e) =>
                  setSettings({ ...settings, require_email_verification: e.target.checked })
                }
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <span className="text-sm text-gray-700">
                Require email verification
              </span>
            </label>
          </div>
        </div>

        {/* Feature Flags */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold mb-4">Feature Flags</h2>
          <div className="space-y-4">
            {Object.entries(settings.features).map(([feature, enabled]) => (
              <label key={feature} className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={() => toggleFeature(feature)}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <span className="text-sm text-gray-700">
                  {feature.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
