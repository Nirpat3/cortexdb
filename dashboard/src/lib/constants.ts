import {
  Database, Brain, Shield, Scale, Grid3X3, HeartPulse,
  Cpu, Terminal, Gauge, Users, Settings, Layers,
  MemoryStick, Waypoints, Radio, Clock, BookLock,
  Monitor, HardDrive, DollarSign, Boxes, Bell,
  BookOpen, LifeBuoy, Code2, ArrowUpDown, Lock, AlertTriangle,
  LayoutDashboard, ServerCrash, Bot,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface AppDefinition {
  id: string;
  name: string;
  icon: LucideIcon;
  route: string;
  color: string;
  description: string;
}

export const APPS: AppDefinition[] = [
  // Row 1 — Core
  { id: 'overview',    name: 'Dashboard',      icon: LayoutDashboard, route: '/overview',    color: '#60A5FA', description: 'High-level executive overview' },
  { id: 'engines',     name: 'Engines',        icon: Database,    route: '/engines',     color: '#3B82F6', description: '7 unified storage engines' },
  { id: 'cortexgraph', name: 'CortexGraph',    icon: Brain,       route: '/cortexgraph', color: '#8B5CF6', description: 'Customer intelligence' },
  { id: 'query',       name: 'Query Console',  icon: Terminal,    route: '/query',       color: '#6366F1', description: 'CortexQL editor' },

  // Row 2 — Monitoring
  { id: 'monitoring',  name: 'Monitoring',     icon: Monitor,     route: '/monitoring',  color: '#22D3EE', description: 'System-wide monitoring' },
  { id: 'hardware',    name: 'Hardware',       icon: HardDrive,   route: '/hardware',    color: '#A78BFA', description: 'CPU, RAM, disk, network' },
  { id: 'db-monitor',  name: 'DB Monitor',     icon: Database,    route: '/db-monitor',  color: '#2DD4BF', description: 'Database health & queries' },
  { id: 'services',    name: 'Services',       icon: Boxes,       route: '/services',    color: '#FB923C', description: 'Microservices monitoring' },

  // Row 3 — Compliance & Security
  { id: 'compliance',  name: 'Compliance',     icon: Shield,      route: '/compliance',  color: '#10B981', description: 'FedRAMP, SOC2, HIPAA, PCI' },
  { id: 'security',    name: 'Security',       icon: Lock,        route: '/security',    color: '#F43F5E', description: 'Threat detection & audit' },
  { id: 'errors',      name: 'Errors',         icon: AlertTriangle, route: '/errors',    color: '#EF4444', description: 'Error tracking & logs' },
  { id: 'notifications', name: 'Notifications', icon: Bell,       route: '/notifications', color: '#FBBF24', description: 'Real-time alerts' },

  // Row 4 — Infrastructure
  { id: 'scale',       name: 'Scale',          icon: Scale,       route: '/scale',       color: '#F59E0B', description: 'Horizontal & vertical scaling' },
  { id: 'grid',        name: 'Grid',           icon: Grid3X3,     route: '/grid',        color: '#EF4444', description: 'Self-healing infrastructure' },
  { id: 'heartbeat',   name: 'Heartbeat',      icon: HeartPulse,  route: '/heartbeat',   color: '#EC4899', description: 'Health monitoring' },
  { id: 'budgeting',   name: 'Budgeting',      icon: DollarSign,  route: '/budgeting',   color: '#34D399', description: 'Cost & resource budgets' },

  // Row 5 — Tools & Docs
  { id: 'mcp',         name: 'MCP Tools',      icon: Cpu,         route: '/mcp',         color: '#06B6D4', description: 'AI agent tools' },
  { id: 'benchmark',   name: 'Benchmark',      icon: Gauge,       route: '/benchmark',   color: '#F97316', description: 'Performance testing' },
  { id: 'api-docs',    name: 'API Docs',       icon: Code2,       route: '/api-docs',    color: '#818CF8', description: 'Interactive API reference' },
  { id: 'install',     name: 'Installation',   icon: BookOpen,    route: '/install',     color: '#4ADE80', description: 'Setup & deployment guide' },

  // Row 6 — Admin
  { id: 'support',     name: 'Support',        icon: LifeBuoy,    route: '/support',     color: '#FB7185', description: 'FAQ & troubleshooting' },
  { id: 'tenants',     name: 'Tenants',        icon: Users,       route: '/tenants',     color: '#14B8A6', description: 'Multi-tenancy management' },
  { id: 'agents',      name: 'Agents',         icon: Bot,         route: '/agents',      color: '#22D3EE', description: 'AI agent registry & status' },
  { id: 'settings',    name: 'Settings',       icon: Settings,    route: '/settings',    color: '#6B7280', description: 'Dashboard configuration' },
];

export const DEFAULT_DOCK_IDS = ['overview', 'monitoring', 'compliance', 'notifications', 'settings'];

export const ENGINE_META: Record<string, { name: string; icon: LucideIcon; color: string; replaces: string }> = {
  relational: { name: 'RelationalCore', icon: Database,   color: '#3B82F6', replaces: 'PostgreSQL' },
  memory:     { name: 'MemoryCore',     icon: MemoryStick, color: '#F59E0B', replaces: 'Redis' },
  vector:     { name: 'VectorCore',     icon: Waypoints,  color: '#8B5CF6', replaces: 'Pinecone' },
  graph:      { name: 'GraphCore',      icon: Brain,      color: '#EC4899', replaces: 'Neo4j' },
  temporal:   { name: 'TemporalCore',   icon: Clock,      color: '#06B6D4', replaces: 'TimescaleDB' },
  stream:     { name: 'StreamCore',     icon: Radio,      color: '#10B981', replaces: 'Kafka' },
  immutable:  { name: 'ImmutableCore',  icon: BookLock,   color: '#EF4444', replaces: 'Hyperledger' },
};

export const COMPLIANCE_FRAMEWORKS = [
  { id: 'fedramp',  name: 'FedRAMP',   level: 'Moderate',  color: '#10B981' },
  { id: 'soc2',     name: 'SOC 2',     level: 'Type II',   color: '#3B82F6' },
  { id: 'hipaa',    name: 'HIPAA',     level: 'Compliant', color: '#8B5CF6' },
  { id: 'pci_dss',  name: 'PCI DSS',   level: 'v4.0',     color: '#F59E0B' },
  { id: 'pa_dss',   name: 'PA-DSS',    level: 'PCI SSF',  color: '#EF4444' },
];
