import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface Plan {
  type: string
  name: string
  description: string
  monthly_price: number
  annual_price: number
  features: string[]
  limits: {
    agents: number
    memory_ops_per_month: number
    stored_memories: number
    api_requests_per_month: number
    team_members: number
  }
}

interface Subscription {
  id: string
  plan_type: string
  status: string
  current_period_end: string
  cancel_at_period_end: boolean
  is_annual: boolean
}

const PLANS: Plan[] = [
  {
    type: 'free',
    name: 'Free',
    description: 'For hobbyists and testing',
    monthly_price: 0,
    annual_price: 0,
    features: ['3 agents', '10K memory ops/month', '1K stored memories', 'Community support'],
    limits: { agents: 3, memory_ops_per_month: 10000, stored_memories: 1000, api_requests_per_month: 50000, team_members: 1 }
  },
  {
    type: 'starter',
    name: 'Starter',
    description: 'For individual developers',
    monthly_price: 29,
    annual_price: 278.40,
    features: ['10 agents', '100K memory ops/month', '50K stored memories', 'Email support', 'Webhooks'],
    limits: { agents: 10, memory_ops_per_month: 100000, stored_memories: 50000, api_requests_per_month: 500000, team_members: 1 }
  },
  {
    type: 'pro',
    name: 'Pro',
    description: 'For teams and production',
    monthly_price: 99,
    annual_price: 950.40,
    features: ['50 agents', '1M memory ops/month', '500K stored memories', '5 team members', '99.9% SLA'],
    limits: { agents: 50, memory_ops_per_month: 1000000, stored_memories: 500000, api_requests_per_month: 5000000, team_members: 5 }
  },
  {
    type: 'business',
    name: 'Business',
    description: 'For growing companies',
    monthly_price: 499,
    annual_price: 4790.40,
    features: ['500 agents', '10M memory ops/month', '5M stored memories', '20 team members', 'SSO/SAML', '99.95% SLA'],
    limits: { agents: 500, memory_ops_per_month: 10000000, stored_memories: 5000000, api_requests_per_month: 50000000, team_members: 20 }
  },
]

export default function Billing() {
  const api = useApi<any>()
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [billingAnnual, setBillingAnnual] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadSubscription()
  }, [])

  async function loadSubscription() {
    try {
      const data = await api.get('/api/v1/billing/subscription')
      setSubscription(data)
    } catch {}
  }

  async function handleUpgrade(planType: string) {
    setLoading(true)
    try {
      const data = await api.post('/api/v1/billing/checkout', {
        plan_type: planType,
        is_annual: billingAnnual
      })
      // Redirect to Stripe Checkout
      if (data.checkout_url) {
        window.location.href = data.checkout_url
      }
    } catch {}
    setLoading(false)
  }

  async function handleCancel() {
    if (!confirm('Are you sure you want to cancel your subscription? You will retain access until the end of your billing period.')) return
    setLoading(true)
    try {
      await api.post('/api/v1/billing/cancel', {})
      loadSubscription()
    } catch {}
    setLoading(false)
  }

  const currentPlan = subscription?.plan_type || 'free'

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Billing & Plans</h1>
        <p className="text-gray-400 mt-1">Manage your subscription and billing</p>
      </div>

      {/* Current Subscription */}
      {subscription && subscription.plan_type !== 'free' && (
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Current Subscription</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold text-white capitalize">{subscription.plan_type} Plan</p>
              <p className="text-gray-400">
                {subscription.is_annual ? 'Annual' : 'Monthly'} billing •{' '}
                {subscription.cancel_at_period_end ? (
                  <span className="text-yellow-400">Cancels {new Date(subscription.current_period_end).toLocaleDateString()}</span>
                ) : (
                  <span>Renews {new Date(subscription.current_period_end).toLocaleDateString()}</span>
                )}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={async () => {
                  try {
                    const data = await api.post('/api/v1/billing/portal', {})
                    if (data.portal_url) window.location.href = data.portal_url
                  } catch {
                    alert('Unable to open billing portal. Please try again.')
                  }
                }}
                className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700 transition-colors"
              >
                Manage Payment
              </button>
              {!subscription.cancel_at_period_end && (
                <button
                  onClick={handleCancel}
                  className="px-4 py-2 bg-red-600/20 text-red-400 rounded-lg hover:bg-red-600/30 transition-colors"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Billing Toggle */}
      <div className="flex items-center justify-center gap-4 mb-8">
        <span className={billingAnnual ? 'text-gray-400' : 'text-white font-medium'}>Monthly</span>
        <button
          onClick={() => setBillingAnnual(!billingAnnual)}
          className={`relative w-14 h-7 rounded-full transition-colors ${billingAnnual ? 'bg-indigo-600' : 'bg-gray-700'}`}
        >
          <span className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-transform ${billingAnnual ? 'left-8' : 'left-1'}`}></span>
        </button>
        <span className={billingAnnual ? 'text-white font-medium' : 'text-gray-400'}>
          Annual <span className="text-green-400 text-sm">Save 20%</span>
        </span>
      </div>

      {/* Plans Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {PLANS.map(plan => {
          const isCurrent = plan.type === currentPlan
          const price = billingAnnual ? plan.annual_price / 12 : plan.monthly_price

          return (
            <div
              key={plan.type}
              className={`bg-gray-900 rounded-xl p-6 border ${
                isCurrent ? 'border-indigo-500' : 'border-gray-800'
              } relative`}
            >
              {isCurrent && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-indigo-600 text-white text-xs font-medium rounded-full">
                  Current Plan
                </span>
              )}

              <h3 className="text-xl font-bold text-white mb-1">{plan.name}</h3>
              <p className="text-gray-400 text-sm mb-4">{plan.description}</p>

              <div className="mb-6">
                <span className="text-4xl font-bold text-white">${price.toFixed(0)}</span>
                <span className="text-gray-400">/mo</span>
                {billingAnnual && plan.monthly_price > 0 && (
                  <p className="text-green-400 text-sm">Billed ${plan.annual_price.toFixed(0)}/year</p>
                )}
              </div>

              <ul className="space-y-2 mb-6">
                {plan.features.map(feat => (
                  <li key={feat} className="flex items-center gap-2 text-sm text-gray-300">
                    <span className="text-green-400">✓</span>
                    {feat}
                  </li>
                ))}
              </ul>

              {isCurrent ? (
                <button
                  disabled
                  className="w-full py-3 bg-gray-800 text-gray-500 font-medium rounded-lg cursor-not-allowed"
                >
                  Current Plan
                </button>
              ) : plan.type === 'free' ? (
                <button
                  disabled
                  className="w-full py-3 bg-gray-800 text-gray-400 font-medium rounded-lg cursor-not-allowed"
                >
                  Free Forever
                </button>
              ) : (
                <button
                  onClick={() => handleUpgrade(plan.type)}
                  disabled={loading}
                  className="w-full py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {loading ? 'Loading...' : currentPlan === 'free' ? 'Upgrade' : 'Switch Plan'}
                </button>
              )}
            </div>
          )
        })}
      </div>

      {/* Enterprise CTA */}
      <div className="mt-8 bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-xl p-8 border border-indigo-500/20 text-center">
        <h2 className="text-2xl font-bold text-white mb-2">Need Enterprise?</h2>
        <p className="text-gray-400 mb-4">
          Unlimited resources, dedicated infrastructure, custom SLA, and 24/7 support.
        </p>
        <a
          href="mailto:sales@nexus.ai?subject=Enterprise%20Inquiry"
          className="inline-block px-8 py-3 bg-white text-gray-900 font-medium rounded-lg hover:bg-gray-100 transition-colors"
        >
          Contact Sales
        </a>
      </div>
    </div>
  )
}
