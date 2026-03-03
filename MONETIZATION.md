# Nexus Monetization Strategy

## Executive Summary

Nexus uses a **usage-based SaaS model** with a generous free tier to drive adoption, tiered plans for growing users, and enterprise contracts for large organizations. Revenue comes from three streams: subscription plans, usage overage fees, and enterprise contracts.

---

## Pricing Philosophy

1. **Free tier that's actually useful** - Developers can build and test without paying
2. **Pay for what you use** - Usage-based pricing aligns cost with value
3. **Predictable bills** - Tiered plans with included quotas prevent bill shock
4. **Enterprise flexibility** - Custom pricing for large deployments

---

## Pricing Tiers

### Free - $0/month
*For hobbyists and testing*

| Resource | Limit |
|----------|-------|
| Agents | 3 |
| Memory operations | 10,000/month |
| Stored memories | 1,000 |
| Discovery queries | 1,000/month |
| API requests | 50,000/month |
| Retention | 30 days inactive deletion |

**Included:**
- Community support (Discord/GitHub)
- Shared infrastructure
- Basic analytics

---

### Starter - $29/month
*For individual developers and small projects*

| Resource | Limit |
|----------|-------|
| Agents | 10 |
| Memory operations | 100,000/month |
| Stored memories | 50,000 |
| Discovery queries | 10,000/month |
| API requests | 500,000/month |
| Retention | Unlimited |

**Included:**
- Email support
- Basic analytics dashboard
- Webhooks
- Custom namespaces

**Overage rates:**
- Memory ops: $0.50 per 10K
- API requests: $0.20 per 10K
- Storage: $0.10 per 10K memories

---

### Pro - $99/month
*For teams and production workloads*

| Resource | Limit |
|----------|-------|
| Agents | 50 |
| Memory operations | 1,000,000/month |
| Stored memories | 500,000 |
| Discovery queries | 100,000/month |
| API requests | 5,000,000/month |
| Retention | Unlimited |

**Included:**
- Priority email support
- Advanced analytics
- Webhooks + event streaming
- Team members (up to 5)
- API key management
- Usage alerts
- 99.9% SLA

**Overage rates:**
- Memory ops: $0.40 per 10K
- API requests: $0.15 per 10K
- Storage: $0.08 per 10K memories

---

### Business - $499/month
*For growing companies*

| Resource | Limit |
|----------|-------|
| Agents | 500 |
| Memory operations | 10,000,000/month |
| Stored memories | 5,000,000 |
| Discovery queries | 1,000,000/month |
| API requests | 50,000,000/month |
| Retention | Unlimited |

**Included:**
- Dedicated support channel
- Custom integrations assistance
- Team members (up to 20)
- SSO/SAML
- Audit logs
- Custom data retention policies
- 99.95% SLA

**Overage rates:**
- Memory ops: $0.30 per 10K
- API requests: $0.10 per 10K
- Storage: $0.05 per 10K memories

---

### Enterprise - Custom pricing
*For large organizations*

**Everything in Business, plus:**
- Unlimited agents
- Custom quotas
- Dedicated infrastructure option
- On-premise deployment option
- Custom SLA (up to 99.99%)
- Dedicated account manager
- 24/7 phone support
- Security review & compliance
- Custom contracts
- Volume discounts

**Starting at $2,000/month** - Contact sales

---

## Revenue Streams

### 1. Subscription Revenue (Primary)
Monthly/annual subscriptions across tiers.

**Projections (Year 1):**
| Tier | Users | MRR |
|------|-------|-----|
| Free | 5,000 | $0 |
| Starter | 200 | $5,800 |
| Pro | 50 | $4,950 |
| Business | 10 | $4,990 |
| Enterprise | 2 | $5,000 |
| **Total** | **5,262** | **$20,740** |

### 2. Usage Overage (Secondary)
Additional revenue when users exceed plan limits.

**Estimated:** 15-20% of subscription revenue

### 3. Enterprise Contracts (Growth)
Annual contracts with large organizations.

**Target:** 5 enterprise contracts by end of Year 1 at $30K+ ARR each

---

## Billing Infrastructure

### What We Need to Build

1. **Usage Tracking**
   - Track API calls per agent
   - Track memory operations (store, get, search, delete)
   - Track storage (memory count)
   - Track discovery queries

2. **Plan Management**
   - Plan definitions with limits
   - Plan assignment to accounts
   - Plan upgrades/downgrades

3. **Billing Integration**
   - Stripe for payments
   - Subscription management
   - Invoice generation
   - Overage billing

4. **Usage Dashboard**
   - Current usage vs limits
   - Usage history
   - Billing history
   - Upgrade prompts

5. **Enforcement**
   - Rate limiting by plan
   - Soft limits with warnings
   - Hard limits with blocks
   - Grace periods

---

## Implementation Phases

### Phase 1: Usage Tracking (Now)
- Add usage counters to database
- Track all billable operations
- Build usage API endpoints

### Phase 2: Plan System
- Plan definitions
- Account-plan associations
- Limit enforcement

### Phase 3: Stripe Integration
- Subscription creation
- Payment processing
- Webhook handling
- Customer portal

### Phase 4: Dashboard
- Usage visualization
- Billing management UI
- Upgrade flows

---

## Conversion Strategy

### Free → Starter
- Usage alerts at 70%, 90%, 100%
- Email sequences highlighting limits
- In-app upgrade prompts
- Feature gating (webhooks, analytics)

### Starter → Pro
- Team collaboration features
- SLA requirements
- Higher limits approaching
- Analytics depth

### Pro → Business/Enterprise
- Compliance requirements (SSO, audit logs)
- Volume needs
- Support requirements
- Custom integrations

---

## Metrics to Track

### North Star
- **MRR** (Monthly Recurring Revenue)
- **Active Agents** (agents with >100 ops/month)

### Growth
- New signups
- Free → Paid conversion rate
- Expansion revenue (upgrades + overage)
- Churn rate

### Usage
- Total API calls
- Memory operations
- Storage growth
- P95 latency

---

## Competitive Pricing Analysis

| Service | Free Tier | Starter | Pro |
|---------|-----------|---------|-----|
| **Nexus** | 10K ops | $29/100K ops | $99/1M ops |
| Mem0 | 10K memories | $19/50K | $249/500K |
| Pinecone | 100K vectors | $70/1M | Custom |
| Supabase | 500MB | $25/8GB | $599/custom |

**Our positioning:** More generous than Mem0 at similar price, unified platform (not just memory).

---

## Year 1 Financial Projections

| Month | Free Users | Paid Users | MRR | ARR Run Rate |
|-------|------------|------------|-----|--------------|
| 1 | 100 | 5 | $200 | $2,400 |
| 3 | 500 | 25 | $1,000 | $12,000 |
| 6 | 2,000 | 100 | $5,000 | $60,000 |
| 9 | 4,000 | 200 | $12,000 | $144,000 |
| 12 | 6,000 | 350 | $25,000 | $300,000 |

**Target:** $300K ARR by end of Year 1

---

## Key Decisions

1. **Monthly vs Annual billing?**
   - Offer both, 20% discount for annual
   - Helps with cash flow and reduces churn

2. **Credit card required for free tier?**
   - No - reduces friction
   - Convert later with usage-based prompts

3. **Overage behavior?**
   - Soft limit: Warn at 80%, 100%
   - Hard limit: Block at 120% with 24hr grace
   - No surprise bills over 150% of plan

4. **Refund policy?**
   - Pro-rated refunds for annual
   - No refunds for monthly (cancel anytime)

---

*Strategy created: March 2026*
