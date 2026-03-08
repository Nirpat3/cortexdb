/**
 * i18n Translation Types
 * All UI strings are defined here to decouple presentation from logic.
 */

export interface Translations {
  // Common / shared
  common: {
    save: string;
    cancel: string;
    create: string;
    delete: string;
    edit: string;
    refresh: string;
    loading: string;
    noData: string;
    error: string;
    success: string;
    close: string;
    search: string;
    filter: string;
    all: string;
    back: string;
    submit: string;
    confirm: string;
    yes: string;
    no: string;
    copy: string;
    actions: string;
    details: string;
    status: string;
    name: string;
    type: string;
    description: string;
    settings: string;
    view: string;
    add: string;
    remove: string;
    clear: string;
    reset: string;
    execute: string;
    start: string;
    stop: string;
    running: string;
    stopped: string;
    active: string;
    inactive: string;
    connected: string;
    disconnected: string;
    configured: string;
    notSet: string;
    enabled: string;
    disabled: string;
    approve: string;
    reject: string;
    pending: string;
    completed: string;
    failed: string;
    unknown: string;
    healthy: string;
    degraded: string;
    unhealthy: string;
    items: string;
    total: string;
    shown: string;
    agents: string;
    tasks: string;
    messages: string;
    unread: string;
    live: string;
    polling: string;
    autoOn: string;
    autoOff: string;
    model: string;
    none: string;
    days: string;
    hours: string;
  };

  // Navigation
  nav: {
    dashboard: string;
    orgChart: string;
    agents: string;
    skills: string;
    tasks: string;
    instructions: string;
    agentBus: string;
    executor: string;
    auditLog: string;
    registry: string;
    agentChat: string;
    collaboration: string;
    intelligence: string;
    llmCosts: string;
    workflows: string;
    ragPipeline: string;
    templates: string;
    scheduler: string;
    health: string;
    autonomy: string;
    reputation: string;
    liveFeed: string;
    metrics: string;
    alerts: string;
    replay: string;
    costOptimizer: string;
    reports: string;
    knowledge: string;
    simulations: string;
    marketplace: string;
    copilot: string;
    templatesMarket: string;
    graphql: string;
    integrations: string;
    voice: string;
    vault: string;
    zeroTrust: string;
    pipelineBuilder: string;
    customDashboards: string;
    edge: string;
    kubernetes: string;
    theming: string;
    multiRegion: string;
    sdks: string;
    versioning: string;
    llmConfig: string;
    backToDashboard: string;
    logout: string;
  };

  // Login / Auth
  login: {
    title: string;
    subtitle: string;
    passphraseLabel: string;
    passphrasePlaceholder: string;
    submit: string;
    authenticating: string;
    errorInvalid: string;
    footerProtected: string;
    footerLockout: string;
  };

  // Dashboard page
  dashboard: {
    title: string;
    subtitle: string;
    totalAgents: string;
    working: string;
    tasks: string;
    instructions: string;
    inProgress: string;
    taskExecutor: string;
    agentBus: string;
    persistence: string;
    autoSave: string;
    queue: string;
    active: string;
    llmProviders: string;
    departments: string;
    agentRoster: string;
  };

  // Agent Management
  agents: {
    title: string;
    subtitle: string;
    departmentFilter: string;
    responsibilities: string;
    skills: string;
    completed: string;
    failed: string;
    reportsTo: string;
    configureLlm: string;
    viewProfile: string;
    ollamaLocal: string;
    claudeAnthropic: string;
    openaiGpt: string;
    modelName: string;
  };

  // Tasks
  taskPage: {
    title: string;
    subtitle: string;
    newTask: string;
    createTask: string;
    taskTitle: string;
    taskTitlePlaceholder: string;
    descriptionPlaceholder: string;
    unassigned: string;
    microservice: string;
    microservicePlaceholder: string;
    autoExecute: string;
    noTasks: string;
    assigned: string;
    service: string;
    priorities: {
      critical: string;
      high: string;
      medium: string;
      low: string;
    };
    statuses: {
      pending: string;
      awaiting_approval: string;
      approved: string;
      in_progress: string;
      review: string;
      completed: string;
      failed: string;
      rejected: string;
    };
    categories: {
      bug: string;
      feature: string;
      enhancement: string;
      qa: string;
      docs: string;
      security: string;
      ops: string;
      general: string;
    };
  };

  // Chat
  chat: {
    title: string;
    selectAgent: string;
    startConversation: string;
    messagesStored: string;
    selectToStart: string;
    clearConversation: string;
    messagePlaceholder: string;
    noResponse: string;
    failedToSend: string;
  };

  // Health
  health: {
    title: string;
    subtitle: string;
    overallStatus: string;
    uptime: string;
    storageEngines: string;
    subsystems: string;
    noEngineData: string;
    noSubsystemData: string;
    rawHealthData: string;
  };

  // Autonomy
  autonomy: {
    title: string;
    subtitle: string;
    tabs: {
      delegation: string;
      goals: string;
      hiring: string;
      sprints: string;
      improvement: string;
    };
    delegation: {
      totalDelegations: string;
      successRate: string;
      autoDelegateTask: string;
      taskId: string;
      fromAgentId: string;
      delegate: string;
      delegationLog: string;
      noDelegations: string;
    };
    goals: {
      decomposeGoal: string;
      describeGoal: string;
      additionalContext: string;
      decompose: string;
      decompositionResult: string;
      decompositionHistory: string;
      noDecompositions: string;
      subTasksGenerated: string;
    };
    hiring: {
      detectedGaps: string;
      noGaps: string;
      severity: string;
      recommendations: string;
      noRecommendations: string;
      hire: string;
      hiringHistory: string;
      noHires: string;
    };
    sprints: {
      createSprint: string;
      sprintGoal: string;
      duration: string;
      sprints: string;
      noSprints: string;
      complete: string;
      activate: string;
      standup: string;
      sprintStandup: string;
    };
    improvement: {
      generateAll: string;
      proposals: string;
      noProposals: string;
      impact: string;
    };
  };

  // Live Feed
  liveFeed: {
    title: string;
    totalEvents: string;
    allTypes: string;
    noEvents: string;
  };

  // Audit Log
  audit: {
    title: string;
    subtitle: string;
  };

  // Bus
  bus: {
    title: string;
    subtitle: string;
  };

  // Executor
  executor: {
    title: string;
    subtitle: string;
  };

  // Instructions
  instructions: {
    title: string;
    subtitle: string;
  };

  // Registry
  registry: {
    title: string;
    subtitle: string;
  };

  // Org Chart
  orgChart: {
    title: string;
    subtitle: string;
  };

  // Collaboration
  collab: {
    title: string;
    subtitle: string;
  };

  // Intelligence
  intelligence: {
    title: string;
    subtitle: string;
  };

  // Costs / LLM Costs
  costs: {
    title: string;
    subtitle: string;
  };

  // Workflows
  workflows: {
    title: string;
    subtitle: string;
  };

  // RAG
  rag: {
    title: string;
    subtitle: string;
  };

  // Templates
  templates: {
    title: string;
    subtitle: string;
  };

  // Scheduler
  scheduler: {
    title: string;
    subtitle: string;
  };

  // Skills
  skillsPage: {
    title: string;
    subtitle: string;
  };

  // Reputation
  reputation: {
    title: string;
    subtitle: string;
  };

  // Metrics
  metricsPage: {
    title: string;
    subtitle: string;
  };

  // Alerts
  alerts: {
    title: string;
    subtitle: string;
  };

  // Replay
  replay: {
    title: string;
    subtitle: string;
  };

  // Cost Optimizer
  costOptimizer: {
    title: string;
    subtitle: string;
  };

  // Reports
  reports: {
    title: string;
    subtitle: string;
  };

  // Knowledge
  knowledge: {
    title: string;
    subtitle: string;
    graph: {
      title: string;
      subtitle: string;
    };
    experts: {
      title: string;
      subtitle: string;
    };
  };

  // Simulations
  simulations: {
    title: string;
    subtitle: string;
    tests: {
      title: string;
      subtitle: string;
    };
    abTests: {
      title: string;
      subtitle: string;
    };
  };

  // Versioning
  version: {
    title: string;
    subtitle: string;
  };

  // LLM Config
  llmConfig: {
    title: string;
    subtitle: string;
  };

  // Marketplace
  marketplace: {
    title: string;
    subtitle: string;
    totalCapabilities: string;
    comingSoon: string;
    searchPlaceholder: string;
    capabilityId: string;
    installed: string;
    config: string;
    noResults: string;
    enableSuccess: string;
    disableSuccess: string;
    dependencyError: string;
    dependentError: string;
  };
}

export type TranslationKey = string;

export const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English', nativeName: 'English', dir: 'ltr' },
  { code: 'zh', name: 'Chinese', nativeName: '中文', dir: 'ltr' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', dir: 'ltr' },
  { code: 'es', name: 'Spanish', nativeName: 'Español', dir: 'ltr' },
  { code: 'fr', name: 'French', nativeName: 'Français', dir: 'ltr' },
  { code: 'ar', name: 'Arabic', nativeName: 'العربية', dir: 'rtl' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', dir: 'ltr' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português', dir: 'ltr' },
  { code: 'ru', name: 'Russian', nativeName: 'Русский', dir: 'ltr' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語', dir: 'ltr' },
] as const;

export type LanguageCode = typeof SUPPORTED_LANGUAGES[number]['code'];
