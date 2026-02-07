export function getCommandTemplate(commandId: string): string | null {
  switch (commandId) {
    case 'fix':
      return 'Please fix the following code:\n\n'
    case 'explain':
      return 'Please explain this concept:\n\n'
    case 'refactor':
      return 'Please refactor this code to be more efficient:\n\n'
    case 'test':
      return 'Please generate unit tests for:\n\n'
    default:
      return null
  }
}
