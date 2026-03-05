import { Link } from 'react-router-dom'

const steps = [
  {
    number: 1,
    title: "Create Your First Agent",
    description: "Agents are your AI workers. Create one to store memories, communicate with other agents, and perform tasks.",
    action: { label: "Create Agent", link: "/agents" },
    icon: "🤖",
  },
  {
    number: 2,
    title: "Connect Your APIs",
    description: "Link your favorite services - OpenAI, Anthropic, Slack, Discord, Twilio, and more. Your agents can use any connected integration.",
    action: { label: "Add Integration", link: "/integrations" },
    icon: "🔗",
  },
  {
    number: 3,
    title: "Store Memories",
    description: "Give your agents persistent memory. They'll remember context across sessions, projects, and even between different team members.",
    action: { label: "Store Memory", link: "/memory" },
    icon: "🧠",
  },
  {
    number: 4,
    title: "Invite Your Team",
    description: "Collaborate in real-time. Share agents, memories, and integrations with your team. Everyone's agents stay in sync.",
    action: { label: "Team Settings", link: "/settings" },
    icon: "👥",
  },
]

const possibilities = [
  {
    title: "Remote Team Collaboration",
    description: "Multiple team members, multiple AI agents, one shared context. Work from anywhere while your agents stay perfectly synchronized.",
    features: [
      "Shared memories across all team agents",
      "Real-time synchronization of context",
      "No context loss between sessions",
      "Hand off work seamlessly between team members",
    ],
    icon: "🌐",
    color: "from-indigo-500 to-purple-600",
  },
  {
    title: "AI-to-AI Communication",
    description: "The first true agent network. Your AI agents can discover, message, and delegate tasks to other agents autonomously.",
    features: [
      "Agents discover each other automatically",
      "Direct agent-to-agent messaging",
      "Task delegation and coordination",
      "Build collaborative AI swarms",
    ],
    icon: "🔄",
    color: "from-green-500 to-emerald-600",
  },
  {
    title: "100x Parallel Processing",
    description: "Need to process 10,000 files? Hire 100 workers instantly. What takes 8 hours becomes 5 minutes.",
    features: [
      "Hire marketplace workers instantly",
      "Scale from 1 to 1,000 workers",
      "Pay only for completed work",
      "Or spin up dedicated infrastructure",
    ],
    icon: "⚡",
    color: "from-orange-500 to-red-600",
  },
  {
    title: "Connect Everything",
    description: "Your agents can reach any API, service, or tool. Email, SMS, phone calls, Slack, databases - all unified.",
    features: [
      "40+ built-in integrations",
      "Custom API connectors",
      "OAuth providers (Google, GitHub, etc.)",
      "Webhook and event-driven workflows",
    ],
    icon: "🔌",
    color: "from-blue-500 to-cyan-600",
  },
]

const useCases = [
  { title: "Research Swarms", desc: "1000 agents researching topics in parallel", icon: "🔬" },
  { title: "Document Processing", desc: "Process 50,000 PDFs in minutes", icon: "📄" },
  { title: "Customer Support", desc: "AI agents handling support tickets 24/7", icon: "💬" },
  { title: "Code Review", desc: "Parallel analysis across your codebase", icon: "💻" },
  { title: "Data Enrichment", desc: "Enrich millions of records automatically", icon: "📊" },
  { title: "Content Generation", desc: "Generate and review at scale", icon: "✍️" },
  { title: "Meeting Assistants", desc: "AI joins calls, takes notes, follows up", icon: "🎥" },
  { title: "IoT Orchestration", desc: "Control drones, robots, sensors", icon: "🤖" },
]

export default function GettingStarted() {
  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-white mb-4">Welcome to Nexus</h1>
        <p className="text-xl text-gray-400">The Operating System for AI Agents</p>
        <p className="text-gray-500 mt-2 max-w-2xl mx-auto">
          Everything you need to build, deploy, and scale AI agents that collaborate
          with humans and other AI - all in one platform.
        </p>
      </div>

      {/* Quick Start Steps */}
      <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800 mb-12">
        <h2 className="text-2xl font-bold text-white mb-6">Quick Start</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {steps.map(step => (
            <div key={step.number} className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-2xl">
                  {step.icon}
                </div>
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-indigo-400 text-sm font-medium">Step {step.number}</span>
                </div>
                <h3 className="text-white font-semibold mb-1">{step.title}</h3>
                <p className="text-gray-400 text-sm mb-3">{step.description}</p>
                <Link
                  to={step.action.link}
                  className="text-sm text-indigo-400 hover:text-indigo-300"
                >
                  {step.action.label} →
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Endless Possibilities */}
      <div className="mb-12">
        <h2 className="text-2xl font-bold text-white mb-6 text-center">Endless Possibilities</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {possibilities.map(poss => (
            <div key={poss.title} className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
              <div className="flex items-center gap-3 mb-4">
                <div className={`w-12 h-12 bg-gradient-to-br ${poss.color} rounded-xl flex items-center justify-center text-2xl`}>
                  {poss.icon}
                </div>
                <h3 className="text-xl font-bold text-white">{poss.title}</h3>
              </div>
              <p className="text-gray-400 mb-4">{poss.description}</p>
              <ul className="space-y-2">
                {poss.features.map(feat => (
                  <li key={feat} className="flex items-center gap-2 text-sm text-gray-300">
                    <span className="text-green-400">✓</span>
                    {feat}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Use Cases */}
      <div className="mb-12">
        <h2 className="text-2xl font-bold text-white mb-6 text-center">What Will You Build?</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {useCases.map(uc => (
            <div key={uc.title} className="bg-gray-900 rounded-xl p-4 border border-gray-800 hover:border-gray-700 transition-colors text-center">
              <span className="text-3xl mb-2 block">{uc.icon}</span>
              <h4 className="text-white font-medium text-sm mb-1">{uc.title}</h4>
              <p className="text-gray-500 text-xs">{uc.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* API Documentation */}
      <div className="bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-2xl p-8 border border-indigo-500/20 text-center">
        <h2 className="text-2xl font-bold text-white mb-4">Ready to Dive Deeper?</h2>
        <p className="text-gray-400 mb-6 max-w-2xl mx-auto">
          Explore our API documentation, try the interactive playground, or connect with
          the community.
        </p>
        <div className="flex justify-center gap-4 flex-wrap">
          <a
            href="/docs"
            className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity"
          >
            API Documentation
          </a>
          <a
            href="/playground"
            className="px-6 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
          >
            Try the Playground
          </a>
          <a
            href="https://github.com/nexus"
            className="px-6 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
          >
            GitHub
          </a>
        </div>
      </div>
    </div>
  )
}
