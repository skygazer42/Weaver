export const translations = {
  en: {
    // Sidebar
    workspace: 'Workspace',
    dashboard: 'Dashboard',
    discover: 'Discover',
    library: 'Library',
    recentReports: 'Recent Reports',
    noRecentChats: 'No recent chats',
    newInvestigation: 'New Investigation',
    weaver: 'Weaver',

    // Header
    toggleTheme: 'Toggle theme',

    // Settings
    settings: 'Settings',
    language: 'Language',
    model: 'Model',
    modelConfiguration: 'Model Configuration',
    defaultModel: 'Default Model',
    save: 'Save',
    cancel: 'Cancel',

    // Search modes
    agent: 'Agent',
    deepsearch: 'Deep Search',

    // Empty state
    emptyStateTitle: 'What can I help you research today?',
    emptyStateSubtitle: 'Choose a mode and start investigating',

    // Common
    loading: 'Loading...',
    error: 'Error',
  },
  zh: {
    // Sidebar
    workspace: '工作区',
    dashboard: '仪表盘',
    discover: '发现',
    library: '资料库',
    recentReports: '最近报告',
    noRecentChats: '暂无最近聊天',
    newInvestigation: '新建调查',
    weaver: 'Weaver',

    // Header
    toggleTheme: '切换主题',

    // Settings
    settings: '设置',
    language: '语言',
    model: '模型',
    modelConfiguration: '模型配置',
    defaultModel: '默认模型',
    save: '保存',
    cancel: '取消',

    // Search modes
    agent: '智能体',
    deepsearch: '深度搜索',

    // Empty state
    emptyStateTitle: '今天我能帮你研究什么？',
    emptyStateSubtitle: '选择一个模式并开始调查',

    // Common
    loading: '加载中...',
    error: '错误',
  }
} as const

export type Language = keyof typeof translations
export type TranslationKey = keyof typeof translations.en
