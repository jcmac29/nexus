import { Save, RefreshCw, AlertCircle, CheckCircle, Info } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useSettings, useUpdateSettings } from '../hooks/useApi';
import { useToast } from '../components/Toast';

const featureDescriptions: Record<string, string> = {
  graph_memory: 'Enable graph-based memory storage for semantic relationships',
  webhooks: 'Allow agents to receive webhook notifications for events',
  federation: 'Enable federation with other Nexus instances',
  marketplace: 'Access the capability marketplace for sharing agent skills',
};

function getFeatureDescription(feature: string): string {
  return featureDescriptions[feature] || `Enable the ${feature.replace(/_/g, ' ')} feature`;
}

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
  const { showToast } = useToast();

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
      showToast('success', 'Settings saved successfully');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (error) {
      setSaveStatus('error');
      showToast('error', error instanceof Error ? error.message : 'Failed to save settings');
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
          <p className="text-sm text-gray-500 mb-4">
            Enable or disable platform features. Changes take effect immediately.
          </p>
          <div className="space-y-4">
            {Object.entries(settings.features).map(([feature, enabled]) => (
              <div key={feature} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={() => toggleFeature(feature)}
                  className="w-4 h-4 mt-0.5 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-700 block">
                    {feature.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </span>
                  <span className="text-xs text-gray-500">
                    {getFeatureDescription(feature)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Info Box */}
        <div className="flex items-start gap-3 p-4 bg-blue-50 rounded-lg border border-blue-200">
          <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-800">
            <p className="font-medium">Settings Persistence</p>
            <p className="mt-1 text-blue-600">
              Some settings may require a service restart to take full effect.
              Feature flags are applied immediately for new requests.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
