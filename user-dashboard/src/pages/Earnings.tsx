import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface SellerAccount {
  id: string
  stripe_onboarding_complete: boolean
  stripe_payouts_enabled: boolean
  total_sales: number
  total_fees_paid: number
  total_payouts: number
  pending_balance: number
  payout_schedule: string
  minimum_payout: number
}

interface Payout {
  id: string
  status: string
  gross_amount: number
  platform_fees: number
  net_amount: number
  period_start: string
  period_end: string
  processed_at: string | null
  destination_last4: string | null
}

interface Earning {
  id: string
  amount: number
  description: string
  buyer_name: string
  status: string
  created_at: string
}

export default function Earnings() {
  const api = useApi<any>()
  const [sellerAccount, setSellerAccount] = useState<SellerAccount | null>(null)
  const [payouts, setPayouts] = useState<Payout[]>([])
  const [earnings, setEarnings] = useState<Earning[]>([])
  const [showWithdraw, setShowWithdraw] = useState(false)
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [accountData, payoutsData, earningsData] = await Promise.all([
        api.get('/api/v1/billing/seller-account').catch(() => null),
        api.get('/api/v1/billing/payouts?limit=10').catch(() => ({ items: [] })),
        api.get('/api/v1/credits/transactions?type=earning&limit=20').catch(() => ({ items: [] }))
      ])
      if (accountData) setSellerAccount(accountData)
      if (payoutsData?.items) setPayouts(payoutsData.items)
      if (earningsData?.items) setEarnings(earningsData.items)
    } catch {}
  }

  async function handleSetupPayout() {
    setLoading(true)
    try {
      const data = await api.post('/api/v1/billing/seller-account/onboard', {})
      if (data.onboarding_url) {
        window.location.href = data.onboarding_url
      }
    } catch {}
    setLoading(false)
  }

  async function handleWithdraw() {
    const amount = parseFloat(withdrawAmount)
    if (isNaN(amount) || amount < (sellerAccount?.minimum_payout || 10)) {
      alert(`Minimum withdrawal is $${sellerAccount?.minimum_payout || 10}`)
      return
    }
    if (amount > (sellerAccount?.pending_balance || 0)) {
      alert('Amount exceeds available balance')
      return
    }
    setLoading(true)
    try {
      await api.post('/api/v1/billing/payouts/request', {
        amount_cents: amount * 100
      })
      setShowWithdraw(false)
      setWithdrawAmount('')
      loadData()
    } catch {}
    setLoading(false)
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-400 bg-green-500/10'
      case 'pending': return 'text-yellow-400 bg-yellow-500/10'
      case 'processing': return 'text-blue-400 bg-blue-500/10'
      case 'failed': return 'text-red-400 bg-red-500/10'
      default: return 'text-gray-400 bg-gray-500/10'
    }
  }

  if (!sellerAccount?.stripe_onboarding_complete) {
    return (
      <div className="p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">Earnings</h1>
          <p className="text-gray-400 mt-1">Earn money by providing AI services</p>
        </div>

        <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center max-w-xl mx-auto">
          <span className="text-6xl mb-6 block">💰</span>
          <h2 className="text-2xl font-bold text-white mb-4">Start Earning with Nexus</h2>
          <p className="text-gray-400 mb-6">
            Set up your payout account to receive earnings from completing jobs,
            selling AI services, and marketplace transactions.
          </p>
          <ul className="text-left space-y-3 mb-8">
            <li className="flex items-center gap-3 text-gray-300">
              <span className="text-green-400">✓</span>
              Instant payouts to your bank account
            </li>
            <li className="flex items-center gap-3 text-gray-300">
              <span className="text-green-400">✓</span>
              Secure processing via Stripe
            </li>
            <li className="flex items-center gap-3 text-gray-300">
              <span className="text-green-400">✓</span>
              Track all your earnings in real-time
            </li>
            <li className="flex items-center gap-3 text-gray-300">
              <span className="text-green-400">✓</span>
              Withdraw anytime (minimum $10)
            </li>
          </ul>
          <button
            onClick={handleSetupPayout}
            disabled={loading}
            className="px-8 py-4 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Set Up Payout Account'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Earnings</h1>
          <p className="text-gray-400 mt-1">Track your earnings and request withdrawals</p>
        </div>
        <button
          onClick={() => setShowWithdraw(true)}
          disabled={!sellerAccount?.stripe_payouts_enabled || (sellerAccount?.pending_balance || 0) < (sellerAccount?.minimum_payout || 10)}
          className="px-6 py-3 bg-gradient-to-r from-green-500 to-emerald-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Withdraw Funds
        </button>
      </div>

      {/* Balance Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Available to Withdraw</p>
          <p className="text-3xl font-bold text-green-400">${(sellerAccount?.pending_balance || 0).toFixed(2)}</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Total Earned</p>
          <p className="text-3xl font-bold text-white">${(sellerAccount?.total_sales || 0).toFixed(2)}</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Platform Fees Paid</p>
          <p className="text-3xl font-bold text-gray-400">${(sellerAccount?.total_fees_paid || 0).toFixed(2)}</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Total Withdrawn</p>
          <p className="text-3xl font-bold text-blue-400">${(sellerAccount?.total_payouts || 0).toFixed(2)}</p>
        </div>
      </div>

      {/* Payout Settings */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <h2 className="text-lg font-semibold text-white mb-4">Payout Settings</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-gray-800 rounded-lg">
            <p className="text-gray-400 text-sm">Schedule</p>
            <p className="text-white font-medium capitalize">{sellerAccount?.payout_schedule || 'Weekly'}</p>
          </div>
          <div className="p-4 bg-gray-800 rounded-lg">
            <p className="text-gray-400 text-sm">Minimum Payout</p>
            <p className="text-white font-medium">${sellerAccount?.minimum_payout || 10}</p>
          </div>
          <div className="p-4 bg-gray-800 rounded-lg">
            <p className="text-gray-400 text-sm">Status</p>
            <p className={`font-medium ${sellerAccount?.stripe_payouts_enabled ? 'text-green-400' : 'text-yellow-400'}`}>
              {sellerAccount?.stripe_payouts_enabled ? 'Active' : 'Setup Required'}
            </p>
          </div>
        </div>
        <button className="mt-4 text-indigo-400 hover:text-indigo-300 text-sm">
          Manage Payout Account →
        </button>
      </div>

      {/* Recent Earnings */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <h2 className="text-lg font-semibold text-white mb-4">Recent Earnings</h2>
        {earnings.length === 0 ? (
          <div className="text-center py-8">
            <span className="text-4xl mb-4 block">🎯</span>
            <p className="text-gray-400">No earnings yet</p>
            <p className="text-gray-500 text-sm">Complete jobs or sell services to start earning</p>
          </div>
        ) : (
          <div className="space-y-3">
            {earnings.map(earning => (
              <div key={earning.id} className="flex items-center justify-between p-4 bg-gray-800 rounded-lg">
                <div className="flex items-center gap-4">
                  <span className="text-2xl">💰</span>
                  <div>
                    <p className="text-white font-medium">{earning.description || 'Service Payment'}</p>
                    <p className="text-gray-400 text-sm">From {earning.buyer_name || 'Anonymous'}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-green-400 font-bold">+${earning.amount.toFixed(2)}</p>
                  <p className="text-gray-500 text-xs">
                    {new Date(earning.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Payout History */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h2 className="text-lg font-semibold text-white mb-4">Payout History</h2>
        {payouts.length === 0 ? (
          <p className="text-gray-400 text-center py-8">No payouts yet</p>
        ) : (
          <div className="space-y-3">
            {payouts.map(payout => (
              <div key={payout.id} className="flex items-center justify-between p-4 bg-gray-800 rounded-lg">
                <div className="flex items-center gap-4">
                  <span className="text-2xl">🏦</span>
                  <div>
                    <p className="text-white font-medium">
                      Payout to ****{payout.destination_last4 || '****'}
                    </p>
                    <p className="text-gray-400 text-sm">
                      {new Date(payout.period_start).toLocaleDateString()} - {new Date(payout.period_end).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-white font-bold">${payout.net_amount.toFixed(2)}</p>
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(payout.status)}`}>
                    {payout.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Withdraw Modal */}
      {showWithdraw && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">Withdraw Funds</h2>
            <p className="text-gray-400 mb-6">
              Available balance: <span className="text-green-400 font-bold">${(sellerAccount?.pending_balance || 0).toFixed(2)}</span>
            </p>

            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-300 mb-2">Amount to Withdraw</label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                <input
                  type="number"
                  value={withdrawAmount}
                  onChange={e => setWithdrawAmount(e.target.value)}
                  min={sellerAccount?.minimum_payout || 10}
                  max={sellerAccount?.pending_balance || 0}
                  step="0.01"
                  className="w-full pl-8 pr-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder={`Min. $${sellerAccount?.minimum_payout || 10}`}
                />
              </div>
              <button
                onClick={() => setWithdrawAmount((sellerAccount?.pending_balance || 0).toString())}
                className="mt-2 text-green-400 hover:text-green-300 text-sm"
              >
                Withdraw All
              </button>
            </div>

            <div className="p-4 bg-gray-800 rounded-lg mb-4">
              <p className="text-gray-400 text-sm">Funds will be sent to your connected bank account. Processing typically takes 1-2 business days.</p>
            </div>

            <div className="p-4 bg-purple-500/10 border border-purple-500/20 rounded-lg mb-6">
              <p className="text-purple-300 text-sm font-medium">Note about promotional credits</p>
              <p className="text-purple-400/70 text-xs mt-1">
                Promotional credits (signup bonus, referral rewards, etc.) cannot be withdrawn.
                They can only be used for platform services like hiring AI workers.
              </p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowWithdraw(false)
                  setWithdrawAmount('')
                }}
                className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleWithdraw}
                disabled={loading || !withdrawAmount}
                className="flex-1 py-3 bg-gradient-to-r from-green-500 to-emerald-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {loading ? 'Processing...' : 'Withdraw'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
