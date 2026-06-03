export const getTerminalPrompt = (namespace: string | undefined): string => {
  if (!namespace) return '$ '
  return `[${namespace.startsWith('user-') ? namespace.slice(0, 15) + '...' : namespace}]$ `
}
