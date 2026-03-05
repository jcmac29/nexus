import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface CreditBalance {
  available_balance: number
  pending_balance: number
  reserved_balance: number
  promotional_balance: number
  spendable_balance: number
  withdrawable_balance: number
  total_earned: number
  total_spent: number
  currency: string
}

interface Transaction {
  id: string
  type: string
  amount: number
  balance_after: number
  description: string
  status: string
  created_at: string
}

interface CreditPackage {
  id: string
  name: string
  description: string
  credit_amount: number
  bonus_credits: number
  price: number
  currency: string
}

const DEFAULT_PACKAGES: CreditPackage[] = [
  { id: '1', name: 'Starter', description: 'Great for trying out', credit_amount: 10, bonus_credits: 0, price: 10, currency: 'USD' },
  { id: '2', name: 'Basic', description: 'For regular use', credit_amount: 50, bonus_credits: 5, price: 45, currency: 'USD' },
  { id: '3', name: 'Pro', description: 'Best value', credit_amount: 100, bonus_credits: 20, price: 80, currency: 'USD' },
  { id: '4', name: 'Business', description: 'For heavy usage', credit_amount: 500, bonus_credits: 150, price: 350, currency: 'USD' },
]

export default function Credits() {
  const api = useApi<any>()
  const [balance, setBalance] = useState<CreditBalance | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [packages, setPackages] = useState<CreditPackage[]>(DEFAULT_PACKAGES)
  const [showPurchase, setShowPurchase] = useState(false)
  const [selectedPackage, setSelectedPackage] = useState<CreditPackage | null>(null)
  const [customAmount, setCustomAmount] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [balanceData, txData, pkgData] = await Promise.all([
        api.get('/api/v1/credits/balance').catch(() => null),
        api.get('/api/v1/credits/transactions?limit=20').catch(() => ({ items: [] })),
        api.get('/api/v1/credits/packages').catch(() => ({ items: DEFAULT_PACKAGES }))
      ])
      if (balanceData) setBalance(balanceData)
      if (txData?.items) setTransactions(txData.items)
      if (pkgData?.items) setPackages(pkgData.items)
    } catch {}
  }

  async function handlePurchase(pkg: CreditPackage) {
    setLoading(true)
    try {
      const data = await api.post('/api/v1/credits/purchase', {
        package_id: pkg.id,
        amount: pkg.price * 100 // cents
      })
      if (data.checkout_url) {
        window.location.href = data.checkout_url
      }
    } catch {}
    setLoading(false)
  }

  async function handleCustomPurchase() {
    const amount = parseFloat(customAmount)
    if (isNaN(amount) || amount < 5) {
      alert('Minimum purchase is $5')
      return
    }
    setLoading(true)
    try {
      const data = await api.post('/api/v1/credits/purchase', {
        amount: amount * 100 // cents
      })
      if (data.checkout_url) {
        window.location.href = data.checkout_url
      }
    } catch {}
    setLoading(false)
  }

  const formatAmount = (amount: number) => {
    const sign = amount >= 0 ? '+' : ''
    return `${sign}$${Math.abs(amount).toFixed(2)}`
  }

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'purchase': return '💳'
      case 'usage': return '⚡'
      case 'earning': return '💰'
      case 'payout': return '🏦'
      case 'bonus': return '🎁'
      case 'refund': return '↩️'
      default: return '📝'
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Credits</h1>
          <p className="text-gray-400 mt-1">Purchase credits to hire AI workers and use APIs</p>
        </div>
        <button
          onClick={() => setShowPurchase(true)}
          className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity"
        >
          + Add Credits
        </button>
      </div>

      {/* Balance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Spendable Balance</p>
          <p className="text-3xl font-bold text-white">${balance?.spendable_balance?.toFixed(2) || '0.00'}</p>
          <p className="text-gray-500 text-sm mt-1">Ready to use on platform</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Withdrawable</p>
          <p className="text-3xl font-bold text-green-400">${balance?.withdrawable_balance?.toFixed(2) || '0.00'}</p>
          <p className="text-gray-500 text-sm mt-1">Can be withdrawn</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Promotional Credits</p>
          <p className="text-3xl font-bold text-purple-400">${balance?.promotional_balance?.toFixed(2) || '0.00'}</p>
          <p className="text-gray-500 text-sm mt-1">Platform use only</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <p className="text-gray-400 text-sm mb-1">Reserved</p>
          <p className="text-3xl font-bold text-blue-400">${balance?.reserved_balance?.toFixed(2) || '0.00'}</p>
          <p className="text-gray-500 text-sm mt-1">Held for active jobs</p>
        </div>
      </div>

      {/* Promotional Credit Notice */}
      {(balance?.promotional_balance || 0) > 0 && (
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl p-4 mb-8 flex items-start gap-4">
          <span className="text-2xl">🎁</span>
          <div>
            <p className="text-purple-300 font-medium">You have ${balance?.promotional_balance?.toFixed(2)} in promotional credits!</p>
            <p className="text-purple-400/70 text-sm mt-1">
              These credits can be used to hire AI workers, access APIs, and use platform services.
              Promotional credits cannot be withdrawn but are automatically applied when you make purchases.
            </p>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <p className="text-2xl font-bold text-green-400">${balance?.total_earned?.toFixed(2) || '0.00'}</p>
          <p className="text-gray-400 text-sm">Total Earned</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <p className="text-2xl font-bold text-red-400">${balance?.total_spent?.toFixed(2) || '0.00'}</p>
          <p className="text-gray-400 text-sm">Total Spent</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <p className="text-2xl font-bold text-white">{transactions.filter(t => t.type === 'usage').length}</p>
          <p className="text-gray-400 text-sm">Jobs Hired</p>
        </div>
        <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <p className="text-2xl font-bold text-white">{transactions.filter(t => t.type === 'earning').length}</p>
          <p className="text-gray-400 text-sm">Jobs Completed</p>
        </div>
      </div>

      {/* Quick Buy */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <h2 className="text-lg font-semibold text-white mb-4">Quick Buy</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {packages.map(pkg => (
            <button
              key={pkg.id}
              onClick={() => handlePurchase(pkg)}
              disabled={loading}
              className="p-4 bg-gray-800 rounded-xl hover:bg-gray-700 transition-colors text-left border border-gray-700 hover:border-indigo-500"
            >
              <p className="text-white font-bold">{pkg.name}</p>
              <p className="text-2xl font-bold text-indigo-400">${pkg.credit_amount}</p>
              {pkg.bonus_credits > 0 && (
                <p className="text-green-400 text-sm">+${pkg.bonus_credits} bonus</p>
              )}
              <p className="text-gray-400 text-sm mt-2">Pay ${pkg.price}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Transaction History */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h2 className="text-lg font-semibold text-white mb-4">Transaction History</h2>
        {transactions.length === 0 ? (
          <p className="text-gray-400 text-center py-8">No transactions yet</p>
        ) : (
          <div className="space-y-3">
            {transactions.map(tx => (
              <div key={tx.id} className="flex items-center justify-between p-4 bg-gray-800 rounded-lg">
                <div className="flex items-center gap-4">
                  <span className="text-2xl">{getTypeIcon(tx.type)}</span>
                  <div>
                    <p className="text-white font-medium capitalize">{tx.type.replace('_', ' ')}</p>
                    <p className="text-gray-400 text-sm">{tx.description || 'Transaction'}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`font-bold ${tx.amount >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatAmount(tx.amount)}
                  </p>
                  <p className="text-gray-500 text-xs">
                    {new Date(tx.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Purchase Modal */}
      {showPurchase && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-lg border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-6">Add Credits</h2>

            <div className="space-y-4 mb-6">
              {packages.map(pkg => (
                <button
                  key={pkg.id}
                  onClick={() => setSelectedPackage(pkg)}
                  className={`w-full p-4 rounded-xl border transition-colors text-left flex items-center justify-between ${
                    selectedPackage?.id === pkg.id
                      ? 'border-indigo-500 bg-indigo-500/10'
                      : 'border-gray-700 bg-gray-800 hover:border-gray-600'
                  }`}
                >
                  <div>
                    <p className="text-white font-medium">{pkg.name}</p>
                    <p className="text-gray-400 text-sm">{pkg.description}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-white font-bold">${pkg.credit_amount}</p>
                    {pkg.bonus_credits > 0 && (
                      <p className="text-green-400 text-xs">+${pkg.bonus_credits} bonus</p>
                    )}
                    <p className="text-gray-400 text-sm">${pkg.price}</p>
                  </div>
                </button>
              ))}
            </div>

            <div className="border-t border-gray-800 pt-4 mb-6">
              <p className="text-gray-400 text-sm mb-2">Or enter custom amount</p>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                  <input
                    type="number"
                    value={customAmount}
                    onChange={e => {
                      setCustomAmount(e.target.value)
                      setSelectedPackage(null)
                    }}
                    min="5"
                    className="w-full pl-8 pr-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Min. $5"
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowPurchase(false)
                  setSelectedPackage(null)
                  setCustomAmount('')
                }}
                className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (selectedPackage) {
                    handlePurchase(selectedPackage)
                  } else if (customAmount) {
                    handleCustomPurchase()
                  }
                }}
                disabled={loading || (!selectedPackage && !customAmount)}
                className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {loading ? 'Processing...' : 'Purchase Credits'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
