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
    apiKeyConfiguration: 'API Key Configuration',
    apiKey: 'API Key',
    apiKeyPlaceholder: 'Enter your API key',
    apiKeyOptional: 'Optional - Leave empty to use default',
    baseUrl: 'Base URL',
    baseUrlPlaceholder: 'Enter custom base URL',
    save: 'Save',
    cancel: 'Cancel',

    // Model Providers
    deepseek: 'DeepSeek',
    zhipu: 'Zhipu',
    qwen: 'Qwen',

    // Search modes
    agent: 'Agent',
    deepsearch: 'Deep Search',
    mcp: 'MCP',
    web: 'Web',

    // Empty state
    emptyStateTitle: 'Weaver AI',
    emptyStateSubtitle: 'Your deep research companion.',
    emptyStateDescription: 'Ask me anything to start a comprehensive investigation.',
    starterAnalyze: 'Analyze the current state of AI Agent frameworks in 2024',
    starterWrite: 'Write a Python script to visualize stock market data',
    starterSummarize: 'Summarize the key findings of the \'Attention Is All You Need\' paper',
    starterPlan: 'Plan a 3-day itinerary for a trip to Kyoto',
    useMode: 'Use',
    mode: 'mode',

    // Chat Input
    attachFiles: 'Attach files',
    sendMessage: 'Send message',
    stopGenerating: 'Stop generating',
    typeMessage: 'Type your message...',
    askAnything: 'Ask anything...',
    forCommands: 'for commands',
    aiCanMakeMistakes: 'AI can make mistakes.',
    dropFilesHere: 'Drop files here',

    // Commands
    commands: 'Commands',
    deepMode: 'Deep Mode',
    switchToDeepSearch: 'Switch to Deep Search',
    agentMode: 'Agent Mode',
    switchToAgent: 'Switch to Agent',
    webMode: 'Web Mode',
    switchToWebSearch: 'Switch to Web Search',
    clearChat: 'Clear Chat',
    resetConversation: 'Reset conversation',

    // MCP Options
    filesystem: 'Filesystem',
    github: 'GitHub',
    braveSearch: 'Brave Search',
    memory: 'Memory',

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
    apiKeyConfiguration: 'API 密钥配置',
    apiKey: 'API 密钥',
    apiKeyPlaceholder: '请输入您的 API 密钥',
    apiKeyOptional: '可选 - 留空使用默认配置',
    baseUrl: 'Base URL',
    baseUrlPlaceholder: '输入自定义 Base URL',
    save: '保存',
    cancel: '取消',

    // Model Providers
    deepseek: 'DeepSeek',
    zhipu: '智谱AI',
    qwen: '通义千问',

    // Search modes
    agent: '智能体',
    deepsearch: '深度搜索',
    mcp: 'MCP',
    web: '网络',

    // Empty state
    emptyStateTitle: 'Weaver AI',
    emptyStateSubtitle: '您的深度研究助手',
    emptyStateDescription: '提出任何问题，开始全面调查。',
    starterAnalyze: '分析 2024 年 AI Agent 框架的现状',
    starterWrite: '编写一个 Python 脚本来可视化股票市场数据',
    starterSummarize: '总结《Attention Is All You Need》论文的关键发现',
    starterPlan: '规划一次京都 3 日游行程',
    useMode: '使用',
    mode: '模式',

    // Chat Input
    attachFiles: '附加文件',
    sendMessage: '发送消息',
    stopGenerating: '停止生成',
    typeMessage: '输入您的消息...',
    askAnything: '询问任何问题...',
    forCommands: '输入命令',
    aiCanMakeMistakes: 'AI 可能会犯错。',
    dropFilesHere: '将文件拖放到此处',

    // Commands
    commands: '命令',
    deepMode: '深度模式',
    switchToDeepSearch: '切换到深度搜索',
    agentMode: '智能体模式',
    switchToAgent: '切换到智能体',
    webMode: '网络模式',
    switchToWebSearch: '切换到网络搜索',
    clearChat: '清除聊天',
    resetConversation: '重置对话',

    // MCP Options
    filesystem: '文件系统',
    github: 'GitHub',
    braveSearch: 'Brave 搜索',
    memory: '记忆',

    // Common
    loading: '加载中...',
    error: '错误',
  }
} as const

export type Language = keyof typeof translations
export type TranslationKey = keyof typeof translations.en
