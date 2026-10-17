export function isMusicSpaceShortcutAllowed(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return true
  return !(
    target.isContentEditable
    || ['INPUT', 'BUTTON', 'SELECT', 'TEXTAREA', 'AUDIO', 'A'].includes(target.tagName)
  )
}
