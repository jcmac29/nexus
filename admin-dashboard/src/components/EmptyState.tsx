import { ReactNode } from 'react';
import { Inbox, Search, Users, Bot, Brain, Settings } from 'lucide-react';

interface EmptyStateProps {
  icon?: 'inbox' | 'search' | 'users' | 'bot' | 'brain' | 'settings';
  title: string;
  description?: string;
  action?: ReactNode;
}

const icons = {
  inbox: Inbox,
  search: Search,
  users: Users,
  bot: Bot,
  brain: Brain,
  settings: Settings,
};

export default function EmptyState({
  icon = 'inbox',
  title,
  description,
  action,
}: EmptyStateProps) {
  const Icon = icons[icon];

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-gray-400" />
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-1">{title}</h3>
      {description && <p className="text-gray-500 mb-4 max-w-sm">{description}</p>}
      {action}
    </div>
  );
}
